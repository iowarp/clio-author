"""The reviewer expert: AgentReview-style peer review of a paper.

:class:`ReviewerExpert` builds a persona-conditioned system prompt, asks the LLM
to review a paper, and parses the response into a structured
:class:`~clio_author.experts.review_models.PaperReview`. The prompt structure and
rubric are re-typed from the AgentReview prompt in PaperOrchestra
``autoraters/agent_review.py``:

    https://github.com/google-deepmind/paper-orchestra  (Apache-2.0)
    Copyright 2026 Google LLC; licensed under the Apache License, Version 2.0.

No source code is copied; only the prompt content and field structure are adapted.

Like the other experts (:class:`~clio_author.experts.paper_qa.PaperQAExpert`),
this expert never raises: missing inputs or any failure produce an error-flagged
:class:`AgentOutput` (appended once to the session), and an LLM response that does
not contain parseable JSON produces a ``parse_error``-flagged output rather than
an exception. It defaults to :class:`EchoLLMClient` so the harness runs offline
(the echo path naturally exercises the ``parse_error`` branch).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from clio_author.experts.review_models import PaperReview, PersonaSpec
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.ingest.blocks import MemoryBlocks
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.llm.vision import VisionClient
from clio_author.retrieval.scholar import S2Record, ScholarClient

# How many related-work records to retrieve and inject when grounding is on.
_GROUNDING_TOP_K = 5
# Max characters of each related-work abstract injected into the prompt.
_GROUNDING_ABSTRACT_CHARS = 200

_GROUNDING_INSTRUCTION = (
    "Where a weakness or question relates to the prior work below, reference it by "
    "title/year; do not invent references."
)

# Rubric text adapted from AgentReview (PaperOrchestra, Apache-2.0); re-typed.
_RUBRIC = (
    "## Rubric for the Overall Rating (1-10)\n"
    "* 10: Among the top 2% of all papers; thorough and field-changing; fight to accept.\n"
    "* 8: Among the top 10%; sufficient support for all claims; highly original.\n"
    "* 6: Sufficient support for major claims; moderately original; minor points need detail.\n"
    "* 5: Some main claims under-supported; major technical/methodological problems; leaning reject.\n"
    "* 3: Marginal contribution.\n"
    "* 1: Not yet thorough enough to warrant publication, or not relevant.\n"
)

_INSTRUCTIONS = (
    "Respond with a brief THOUGHT, then the review as a fenced JSON block.\n\n"
    "THOUGHT:\n<your concise, paper-specific reasoning>\n\n"
    "REVIEW JSON:\n```json\n<json>\n```\n\n"
    "The JSON object must contain these fields: "
    '"Summary" (string), "Strengths" (list), "Weaknesses" (list), '
    '"Questions" (list), "Limitations" (list), "Ethical Concerns" (boolean), '
    '"Originality"/"Quality"/"Clarity"/"Significance"/"Soundness"/'
    '"Presentation"/"Contribution" (1-4), "Overall" (1-10), '
    '"Confidence" (1-5), and "Decision" (exactly "Accept" or "Reject").\n'
    "Do not use Weak/Borderline/Strong variants for Decision. "
    "The JSON is parsed automatically, so keep the format precise."
)

_PROSE_INSTRUCTIONS = (
    "Write a concise peer review in plain prose (no JSON, no code fences):\n"
    "- a short summary of the paper,\n"
    "- Strengths,\n"
    "- Weaknesses,\n"
    "- Questions for the authors,\n"
    "- and a final line: 'Decision: Accept' or 'Decision: Reject' with an overall rating out of 10."
)


def build_reviewer_system_prompt(persona: PersonaSpec) -> str:
    """Build the persona-conditioned reviewer system prompt.

    Re-typed from AgentReview's ``get_agentreview_system_prompt`` (PaperOrchestra,
    Apache-2.0): a reviewer bio plus the three persona dimensions
    (knowledgeable / responsible / benign) and the overall-rating rubric.
    """
    bio = (
        "You are a reviewer. You write peer reviews of academic papers by "
        "evaluating their technical quality, originality, and clarity.\n\n"
    )

    if persona.knowledgeable:
        bio += (
            "Knowledgeability: You are knowledgeable, with a strong background and "
            "a PhD in the subject areas related to this paper, and the expertise to "
            "scrutinize it and provide insightful feedback.\n\n"
        )
    else:
        bio += (
            "Knowledgeability: You are not knowledgeable and lack a strong background "
            "in the subject areas related to this paper.\n\n"
        )

    if persona.responsible:
        bio += (
            "Responsibility: As a responsible reviewer, you meticulously assess "
            "technical accuracy, innovation, and relevance, reading thoroughly and "
            "analyzing the methodology critically.\n\n"
        )
    else:
        bio += (
            "Responsibility: As a lazy reviewer, your reviews tend to be superficial "
            "and hastily done, overlooking critical details.\n\n"
        )

    if persona.benign:
        bio += (
            "Intention: As a benign reviewer, you aim to help authors improve their "
            "work with detailed, constructive feedback while remaining critical of "
            "technical flaws.\n\n"
        )
    else:
        bio += (
            "Intention: As a mean reviewer, your style is harsh and overly critical, "
            "focusing excessively on faults and overlooking merits.\n\n"
        )

    return bio + _RUBRIC


class ReviewerExpert(BaseAgent):
    """Expert that produces a structured peer review of a paper."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        persona: PersonaSpec | None = None,
        scholar_client: ScholarClient | None = None,
        vision: VisionClient | None = None,
    ) -> None:
        """Build a reviewer expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            persona: Reviewer persona; defaults to the knowledgeable / responsible
                / benign "best case" reviewer.
            scholar_client: Optional scholar client (the network seam) used only
                when a review requests grounding (``payload["ground"]`` truthy).
                ``None`` (default) leaves the review behaviour exactly as before.
            vision: Optional :class:`VisionClient` (e.g. Gemini). When set *and* the
                review payload carries figures, the reviewer looks at the real
                figure images and folds their descriptions into the paper text it
                reviews; ``None`` (default) keeps the text-only review path.
        """
        self.persona = persona or PersonaSpec()
        self._scholar = scholar_client
        self._vision = vision
        super().__init__(
            role="reviewer",
            system_prompt=build_reviewer_system_prompt(self.persona),
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _coerce_paper(raw: Any) -> str:
        """Render ``raw`` paper input into review-ready Markdown text.

        Accepts a Markdown ``str`` directly, or a
        :class:`~clio_author.ingest.blocks.MemoryBlocks` (or its ``model_dump``
        dict), rendering the latter at ``detail="full"``.
        """
        if isinstance(raw, str):
            return raw
        blocks = raw if isinstance(raw, MemoryBlocks) else MemoryBlocks.model_validate(raw)
        return "\n\n".join(blocks.select(detail="full"))

    @staticmethod
    def _coerce_figures(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Resolve a list of figure dicts (``image_path`` / ``caption`` / id) from ``payload``.

        Prefers an explicit ``payload["figures"]`` (a list of
        ``{figure_id?, image_path, caption?}``); else pulls ``figures`` out of a
        ``payload["blocks"]`` MemoryBlocks dump. Returns ``[]`` when neither is
        present or usable.
        """
        figures_raw = payload.get("figures")
        if isinstance(figures_raw, (list, tuple)):
            return [dict(fig) for fig in figures_raw if isinstance(fig, dict)]

        blocks_raw = payload.get("blocks")
        if blocks_raw is not None:
            try:
                blocks = (
                    blocks_raw
                    if isinstance(blocks_raw, MemoryBlocks)
                    else MemoryBlocks.model_validate(blocks_raw)
                )
            except Exception:  # noqa: BLE001 - bad blocks just mean no figures
                return []
            return [fig.model_dump() for fig in blocks.figures]
        return []

    @staticmethod
    def _images_dir(payload: dict[str, Any]) -> Path | None:
        """Resolve a base directory for figure images from ``payload``."""
        for key in ("images_dir", "out_dir"):
            raw = payload.get(key)
            if raw:
                return Path(str(raw))
        return None

    @staticmethod
    def _resolve_image(image_path: str, images_dir: Path | None) -> Path | None:
        """Resolve ``image_path`` to a readable file, or ``None`` if not found."""
        if not image_path:
            return None
        candidate = Path(image_path)
        if candidate.is_file():
            return candidate
        if images_dir is not None:
            joined = images_dir / image_path
            if joined.is_file():
                return joined
        return None

    def _describe_figures(self, payload: dict[str, Any]) -> list[str]:
        """Look at each payload figure with vision; return readable descriptions.

        Per figure: resolve its ``image_path`` (against ``images_dir``/``out_dir``
        or an absolute/existing path) and call :meth:`VisionClient.describe_image`.
        Wraps each call in try/except so a missing image or a vision failure simply
        skips that figure and continues. Returns ``[]`` when no figures describe.
        """
        assert self._vision is not None  # guarded by the caller
        figures = self._coerce_figures(payload)
        if not figures:
            return []
        images_dir = self._images_dir(payload)
        descriptions: list[str] = []
        for figure in figures:
            image = self._resolve_image(str(figure.get("image_path", "")), images_dir)
            if image is None:
                continue
            figure_id = figure.get("figure_id")
            caption = str(figure.get("caption", "")).strip()
            prompt_parts = ["Describe this figure for a peer reviewer of the paper."]
            if caption:
                prompt_parts.append(f"Caption:\n{caption}")
            prompt_parts.append("State concisely and factually what the image actually shows.")
            try:
                described = self._vision.describe_image(
                    str(image), "\n\n".join(prompt_parts)
                ).strip()
            except Exception:  # noqa: BLE001 - VisionError/any failure -> skip this figure
                continue
            if described:
                label = f"Figure {figure_id}: " if figure_id is not None else ""
                descriptions.append(f"{label}{described}")
        return descriptions

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Review the paper in ``task`` and return a structured :class:`PaperReview`.

        Reads the paper from ``payload["paper"]`` / ``["markdown"]`` / ``["blocks"]``
        or, failing those, ``task.description``. Builds a ``[system, user]``
        conversation, calls the LLM, extracts a ```json``` fenced block (else the
        first balanced ``{...}`` object) using only stdlib ``json``, and parses it
        via :meth:`PaperReview.from_loose_dict`.

        On success, ``content`` is a one-line human summary (decision + overall),
        ``structured`` is the review's ``model_dump()``, and ``metadata`` carries
        ``persona`` / ``decision`` / ``overall``. If no parseable JSON is present,
        returns an output with the raw text as ``content``, ``structured=None`` and
        ``metadata={"parse_error": ...}``. Never raises: missing input or any
        failure produces an error-flagged output (appended once).

        Retrieval-grounded review: when ``payload["ground"]`` is truthy *and* a
        scholar client was supplied, related prior work is retrieved for the paper
        and injected into the user prompt, with an instruction to ground weaknesses
        and questions in it. The retrieved references are echoed back in
        ``metadata["related_work"]`` and ``structured["related_work"]`` so the
        caller sees what grounded the review. With no scholar client or grounding
        off (the default), behaviour is unchanged and the scholar client is never
        called. A scholar-search failure is caught and recorded in
        ``metadata["grounding_error"]``; the review still proceeds ungrounded.
        """
        metadata: dict[str, Any] = {"persona": self.persona.label}
        try:
            raw_paper = (
                task.payload.get("paper")
                or task.payload.get("markdown")
                or task.payload.get("blocks")
                or task.description
            )
            if not raw_paper:
                return self._error(session, "no 'paper'/'markdown'/'blocks' provided")

            # format: "structured" (default, JSON rubric) or "prose" (free-text review).
            fmt = str(task.payload.get("format", "structured")).lower()
            instructions = _PROSE_INSTRUCTIONS if fmt == "prose" else _INSTRUCTIONS

            paper_text = self._coerce_paper(raw_paper)

            # Multimodal grounding (opt-in): when a vision client is set *and* the
            # payload carries figures, look at the real images and fold their
            # descriptions into the reviewed text. Default (no vision / no figures)
            # leaves the text and metadata exactly as before.
            if self._vision is not None:
                descriptions = self._describe_figures(task.payload)
                if descriptions:
                    paper_text += "\n\n## Figures\n" + "\n\n".join(descriptions)
                    metadata["figures_seen"] = len(descriptions)
                    metadata["vision_review"] = True

            # Retrieval grounding (opt-in; default off keeps the legacy behaviour).
            ground = bool(task.payload.get("ground", False)) and self._scholar is not None
            related: list[S2Record] = []
            if ground:
                query = _grounding_query(task.payload.get("title"), paper_text)
                try:
                    found = self._scholar.search_title(query, None, None)  # type: ignore[union-attr]
                except Exception as exc:  # noqa: BLE001 - grounding is best-effort
                    metadata["grounding_error"] = str(exc)
                    ground = False
                else:
                    related = list(found[:_GROUNDING_TOP_K])

            metadata["grounded"] = ground
            related_summary = [{"title": r.title, "year": r.year} for r in related]
            if ground:
                metadata["related_work"] = related_summary

            user_content = f"{instructions}\n\nHere is the paper to review:\n```\n{paper_text}\n```"
            if ground and related:
                user_content += (
                    f"\n\n{_GROUNDING_INSTRUCTION}\n\n## Related prior work\n"
                    + _format_related_work(related)
                )

            messages = [
                Message(role="system", content=self.system_prompt),
                Message(role="user", content=user_content),
            ]
            raw = self.llm.complete(messages)

            if fmt == "prose":
                # Human-facing prose review: the text IS the result; no parsing.
                output = AgentOutput(
                    agent=self.name,
                    content=raw,
                    structured=None,
                    metadata={**metadata, "format": "prose"},
                )
                session.add(output)
                return output

            parsed = _extract_json_object(raw)
            if parsed is None:
                output = AgentOutput(
                    agent=self.name,
                    content=raw,
                    structured=None,
                    metadata={
                        **metadata,
                        "parse_error": "no parseable JSON object in LLM response",
                    },
                )
                session.add(output)
                return output

            review = PaperReview.from_loose_dict(parsed)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        structured = review.model_dump()
        if ground:
            structured["related_work"] = related_summary
        output = AgentOutput(
            agent=self.name,
            content=f"Decision: {review.decision} (overall {review.overall}/10). {review.summary}".strip(),
            structured=structured,
            metadata={
                **metadata,
                "decision": review.decision,
                "overall": review.overall,
            },
        )
        session.add(output)
        return output


def _grounding_query(title: Any, paper_text: str) -> str:
    """Derive a related-work search query for the paper.

    Prefers an explicit ``title``; otherwise the first Markdown ``#``/``##``
    heading in the paper text; failing that, the first ~12 words of the text.
    """
    if isinstance(title, str) and title.strip():
        return title.strip()
    for line in paper_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading
    return " ".join(paper_text.split()[:12])


def _format_related_work(records: list[S2Record]) -> str:
    """Render related-work ``records`` as a compact bullet block for the prompt."""
    lines: list[str] = []
    for record in records:
        year = record.year if record.year is not None else "n.d."
        authors = ", ".join(record.authors[:3]) or "unknown authors"
        abstract = _normalise_space(record.abstract or "")
        if len(abstract) > _GROUNDING_ABSTRACT_CHARS:
            abstract = abstract[:_GROUNDING_ABSTRACT_CHARS].rstrip() + "..."
        line = f"- {record.title} ({year}) - {authors}"
        if abstract:
            line += f"\n  {abstract}"
        lines.append(line)
    return "\n".join(lines)


def _normalise_space(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip the ends."""
    return re.sub(r"\s+", " ", text).strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from ``text`` using only stdlib ``json``.

    Prefers a ```json``` fenced block; otherwise scans for the first balanced
    ``{...}`` span and tries to parse it. Returns the decoded ``dict`` on success
    or ``None`` if nothing parses (callers treat ``None`` as a parse error). Never
    raises.
    """
    candidates: list[str] = []

    fence = "```json"
    start = text.find(fence)
    if start != -1:
        end = text.find("```", start + len(fence))
        if end != -1:
            candidates.append(text[start + len(fence) : end])

    span = _first_balanced_object(text)
    if span is not None:
        candidates.append(span)

    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(decoded, dict):
            return decoded
    return None


def _first_balanced_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` substring of ``text`` (or ``None``).

    Tracks brace depth while skipping over string literals so braces inside JSON
    strings do not unbalance the scan.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


__all__ = ["ReviewerExpert", "build_reviewer_system_prompt"]

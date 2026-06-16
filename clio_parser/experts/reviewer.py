"""The reviewer expert: AgentReview-style peer review of a paper.

:class:`ReviewerExpert` builds a persona-conditioned system prompt, asks the LLM
to review a paper, and parses the response into a structured
:class:`~clio_parser.experts.review_models.PaperReview`. The prompt structure and
rubric are re-typed from the AgentReview prompt in PaperOrchestra
``autoraters/agent_review.py``:

    https://github.com/google-deepmind/paper-orchestra  (Apache-2.0)
    Copyright 2026 Google LLC; licensed under the Apache License, Version 2.0.

No source code is copied; only the prompt content and field structure are adapted.

Like the other experts (:class:`~clio_parser.experts.paper_qa.PaperQAExpert`),
this expert never raises: missing inputs or any failure produce an error-flagged
:class:`AgentOutput` (appended once to the session), and an LLM response that does
not contain parseable JSON produces a ``parse_error``-flagged output rather than
an exception. It defaults to :class:`EchoLLMClient` so the harness runs offline
(the echo path naturally exercises the ``parse_error`` branch).
"""

from __future__ import annotations

import json
from typing import Any

from clio_parser.experts.review_models import PaperReview, PersonaSpec
from clio_parser.harness.base import BaseAgent
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Message, Task
from clio_parser.ingest.blocks import MemoryBlocks
from clio_parser.llm.client import EchoLLMClient, LLMClient

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
    ) -> None:
        """Build a reviewer expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            persona: Reviewer persona; defaults to the knowledgeable / responsible
                / benign "best case" reviewer.
        """
        self.persona = persona or PersonaSpec()
        super().__init__(
            role="reviewer",
            system_prompt=build_reviewer_system_prompt(self.persona),
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _coerce_paper(raw: Any) -> str:
        """Render ``raw`` paper input into review-ready Markdown text.

        Accepts a Markdown ``str`` directly, or a
        :class:`~clio_parser.ingest.blocks.MemoryBlocks` (or its ``model_dump``
        dict), rendering the latter at ``detail="full"``.
        """
        if isinstance(raw, str):
            return raw
        blocks = raw if isinstance(raw, MemoryBlocks) else MemoryBlocks.model_validate(raw)
        return "\n\n".join(blocks.select(detail="full"))

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
        """
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
            messages = [
                Message(role="system", content=self.system_prompt),
                Message(
                    role="user",
                    content=(
                        f"{instructions}\n\nHere is the paper to review:\n```\n{paper_text}\n```"
                    ),
                ),
            ]
            raw = self.llm.complete(messages)

            if fmt == "prose":
                # Human-facing prose review: the text IS the result; no parsing.
                output = AgentOutput(
                    agent=self.name,
                    content=raw,
                    structured=None,
                    metadata={"persona": self.persona.label, "format": "prose"},
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
                        "persona": self.persona.label,
                        "parse_error": "no parseable JSON object in LLM response",
                    },
                )
                session.add(output)
                return output

            review = PaperReview.from_loose_dict(parsed)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        output = AgentOutput(
            agent=self.name,
            content=f"Decision: {review.decision} (overall {review.overall}/10). {review.summary}".strip(),
            structured=review.model_dump(),
            metadata={
                "persona": self.persona.label,
                "decision": review.decision,
                "overall": review.overall,
            },
        )
        session.add(output)
        return output


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

"""The research expert: propose + (optionally) ground a literature brief.

:class:`ResearchExpert` re-expresses the literature-research / ideation step of
the JS writing toolkit wtf-p as a Python expert:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concept* (ask a model for foundational / recent / competing sources
plus gaps and a synthesis, then ground the proposed titles against a scholar
backend) is reproduced; no source code is copied. The LLM proposes sources and
gaps as JSON (parsed with the reviewer's
:func:`~clio_author.experts.reviewer._extract_json_object`); when a
:class:`~clio_author.retrieval.scholar.ScholarClient` is supplied each proposed
title is routed through :func:`~clio_author.retrieval.scholar.verify` so the
brief is grounded in real records rather than fabricated.

Like the other experts this one never raises: missing inputs or any failure
produce an error-flagged :class:`AgentOutput` (appended once). The default
:class:`EchoLLMClient` yields no parseable JSON, so the echo path degrades to a
``parse_error`` with an empty brief (it never invents verified citations).
"""

from __future__ import annotations

from typing import Any

from clio_author.experts.research_models import ResearchBrief, SourceNote
from clio_author.experts.reviewer import _extract_json_object
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.ingest.blocks import MemoryBlocks
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.retrieval.scholar import (
    Reference,
    ScholarClient,
    VerifiedCitation,
    verify,
)

RESEARCH_SYSTEM_PROMPT = (
    "You are the literature-research expert. For a topic or paper section you "
    "propose the prior work that grounds it -- foundational works, recent work, "
    "and competing/alternative approaches -- identify the open gaps your work "
    "would address, and synthesise the landscape. Propose only real, plausible "
    "titles; do not fabricate citation keys or invent fake records. The "
    "verification of titles against a scholarly index is done downstream.\n\n"
    "Produce a research brief as a fenced JSON block:\n"
    "```json\n"
    '{"topic": "<the topic>", '
    '"foundational": [{"title": "<paper title>", "note": "<why it matters>", '
    '"year": <int or null>}], '
    '"recent": [{"title": "...", "note": "...", "year": <int or null>}], '
    '"competing": [{"title": "...", "note": "...", "year": <int or null>}], '
    '"gaps": ["<open problem this work addresses>"], '
    '"synthesis": {"<theme>": ["<observation>"]}, '
    '"confidence": "HIGH|MEDIUM|LOW", '
    '"recommendations": ["<what to read / cite next>"]}\n'
    "```\n"
    "Keep the format precise; the JSON is parsed automatically."
)


class ResearchExpert(BaseAgent):
    """Expert that proposes and (optionally) grounds a literature brief."""

    def __init__(
        self, llm: LLMClient | None = None, *, scholar_client: ScholarClient | None = None
    ) -> None:
        """Build a research expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            scholar_client: Optional scholar client (the network seam). When set,
                proposed source titles are verified against it so the brief is
                grounded; when ``None`` the brief is returned ungrounded
                (``metadata["grounded"]`` is ``False``) and no network is touched.
        """
        super().__init__(
            role="research",
            system_prompt=RESEARCH_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._scholar = scholar_client

    @staticmethod
    def _resolve_topic(payload: dict[str, Any]) -> str:
        """Resolve the research topic from ``topic`` / ``section`` (+ ``outline``)."""
        topic = str(payload.get("topic") or "").strip()
        if topic:
            return topic
        section = str(payload.get("section") or "").strip()
        outline = str(payload.get("outline") or "").strip()
        parts = [part for part in (section, outline) if part]
        if parts:
            return " - ".join(parts)
        return ""

    @staticmethod
    def _grounding(payload: dict[str, Any]) -> str:
        """Assemble optional grounding context from ``blocks`` / ``source``."""
        blocks_raw = payload.get("blocks")
        if blocks_raw is not None:
            blocks = (
                blocks_raw
                if isinstance(blocks_raw, MemoryBlocks)
                else MemoryBlocks.model_validate(blocks_raw)
                if isinstance(blocks_raw, dict)
                else None
            )
            if blocks is not None:
                rendered = blocks.select(detail="summary")
                if rendered:
                    return "\n\n".join(rendered)
        source = payload.get("source")
        if source:
            return source if isinstance(source, str) else str(source)
        return ""

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Build a research brief for the topic in ``task``. Never raises.

        Reads ``topic`` (or ``section`` + ``outline``), optional ``blocks`` /
        ``source`` grounding, and ``depth`` (``"standard"`` | ``"deep"``). Asks
        the LLM for a JSON brief and parses it via
        :meth:`ResearchBrief.from_loose_dict`. When a scholar client is set, every
        proposed title is verified (:func:`verify`) and its source note is marked
        ``grounded`` with the matched record's title.

        On success ``structured`` is the brief's ``model_dump()``, ``content`` is
        a one-line summary, and ``metadata`` carries ``num_sources`` /
        ``confidence`` / ``grounded``. With no parseable JSON (e.g. the echo
        client) the output is ``parse_error``-flagged with an empty brief. Missing
        a topic produces an error-flagged output.
        """
        try:
            payload = task.payload
            topic = self._resolve_topic(payload)
            if not topic:
                return self._error(session, "no 'topic'/'section' provided")

            depth = str(payload.get("depth", "standard")).lower()
            grounding = self._grounding(payload)

            messages = self._build_messages(topic, grounding, depth)
            raw = self.llm.complete(messages)

            parsed = _extract_json_object(raw)
            if parsed is None:
                empty = ResearchBrief(topic=topic)
                output = AgentOutput(
                    agent=self.name,
                    content=raw,
                    structured=empty.model_dump(),
                    metadata={
                        "num_sources": 0,
                        "confidence": empty.confidence,
                        "grounded": False,
                        "parse_error": "no parseable JSON object in LLM response",
                    },
                )
                session.add(output)
                return output

            brief = ResearchBrief.from_loose_dict(parsed)
            if not brief.topic:
                brief = brief.model_copy(update={"topic": topic})

            grounded = False
            if self._scholar is not None:
                brief, grounded = self._ground_brief(brief)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        content = _render_summary(brief, grounded)
        output = AgentOutput(
            agent=self.name,
            content=content,
            structured=brief.model_dump(),
            metadata={
                "num_sources": brief.num_sources(),
                "confidence": brief.confidence,
                "grounded": grounded,
            },
        )
        session.add(output)
        return output

    def _build_messages(self, topic: str, grounding: str, depth: str) -> list[Message]:
        parts = [f"Topic / section to research:\n{topic}"]
        if depth == "deep":
            parts.append(
                "Depth: DEEP -- be thorough; aim for several sources per bucket "
                "and articulate the gaps precisely."
            )
        if grounding:
            parts.append(f"Grounding material from the work in progress:\n{grounding}")
        parts.append("Produce the research brief now in the required JSON format.")
        return [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content="\n\n".join(parts)),
        ]

    def _ground_brief(self, brief: ResearchBrief) -> tuple[ResearchBrief, bool]:
        """Verify each proposed title against the scholar client; mark grounded.

        Returns ``(updated_brief, grounded)`` where ``grounded`` is ``True`` when
        at least one source title matched a real record. A scholar failure is
        swallowed (best-effort): the source simply stays ungrounded. Never
        invents a verified record -- only titles the client actually returns are
        marked grounded.
        """
        assert self._scholar is not None  # guarded by the caller
        any_grounded = False

        def ground(notes: list[SourceNote]) -> list[SourceNote]:
            nonlocal any_grounded
            updated: list[SourceNote] = []
            for note in notes:
                if not note.title:
                    updated.append(note)
                    continue
                try:
                    verified = verify(
                        [Reference(query_title=note.title, year_hint=note.year)],
                        self._scholar,  # type: ignore[arg-type]
                    )
                except Exception:  # noqa: BLE001 - grounding is best-effort
                    verified = []
                if verified:
                    match: VerifiedCitation = verified[0]
                    any_grounded = True
                    updated.append(
                        note.model_copy(
                            update={
                                "grounded": True,
                                "verified_title": match.record.title,
                            }
                        )
                    )
                else:
                    updated.append(note)
            return updated

        updated_brief = brief.model_copy(
            update={
                "foundational": ground(brief.foundational),
                "recent": ground(brief.recent),
                "competing": ground(brief.competing),
            }
        )
        return updated_brief, any_grounded


def _render_summary(brief: ResearchBrief, grounded: bool) -> str:
    """Render a one-line human summary of a research brief."""
    grounded_count = sum(
        1
        for bucket in (brief.foundational, brief.recent, brief.competing)
        for note in bucket
        if note.grounded
    )
    head = (
        f"Research brief on '{brief.topic}': {brief.num_sources()} source(s) "
        f"({grounded_count} grounded), {len(brief.gaps)} gap(s), "
        f"confidence {brief.confidence}."
    )
    if not grounded and brief.num_sources():
        head += " (proposed sources not yet verified against a scholar index)"
    return head


__all__ = ["ResearchExpert", "RESEARCH_SYSTEM_PROMPT"]

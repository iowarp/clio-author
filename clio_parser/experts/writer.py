"""The writer expert: section-isolated drafting and feedback-driven revision.

:class:`WriterExpert` is the single *producer* in a :class:`CriticRefine` loop. It
has two phases keyed on ``session.data["critic_feedback"]``:

* **draft** (no feedback yet) -- assemble the section's source material and its
  outline/plan, inline *only* what this section needs (section isolation), and ask
  the LLM for grounded prose. Citation (``\\cite{key}``) and figure placeholders
  from the hints are kept verbatim; the model is told not to invent citations.
* **revise** (feedback present) -- inline the current draft and the critic feedback
  and ask for a targeted revision.

The section-writing structure (vision + per-section plan + scoped source, write
one section at a time) is referenced from PaperOrchestra (Apache-2.0); no source
code is copied. Like the other experts this one never raises: missing inputs, a
file refusal, or any failure produce an error-flagged :class:`AgentOutput`
(appended once). The default :class:`EchoLLMClient` keeps it offline.
"""

from __future__ import annotations

from typing import Any

from clio_parser.experts.write_models import SectionOutline, SectionPlan
from clio_parser.harness.base import BaseAgent
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Message, Task
from clio_parser.ingest.blocks import MemoryBlocks
from clio_parser.llm.client import EchoLLMClient, LLMClient
from clio_parser.tools.files import FileToolError, SafeFiles

WRITER_SYSTEM_PROMPT = (
    "You are the writing expert. You draft and revise one paper section at a time, "
    "grounded strictly in the provided source material. Write clear, technical "
    "academic prose. Preserve every citation placeholder (\\cite{key}) and figure "
    "reference exactly as given -- never invent, rename, or remove citations or "
    "figures. Stay within the section's stated goal and word budget."
)


class WriterExpert(BaseAgent):
    """Expert that drafts and revises a single paper section."""

    def __init__(self, llm: LLMClient | None = None, *, files: SafeFiles | None = None) -> None:
        """Build a writer expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            files: Optional :class:`SafeFiles`; when given together with
                ``payload["out_path"]`` the draft is written under its root.
        """
        self.files = files
        super().__init__(
            role="writer",
            system_prompt=WRITER_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _coerce_outline(payload: dict[str, Any]) -> SectionOutline | None:
        """Extract a :class:`SectionOutline` from ``payload`` (``outline``/plan)."""
        raw_plan = payload.get("section_plan")
        if raw_plan is not None:
            plan = (
                raw_plan
                if isinstance(raw_plan, SectionPlan)
                else SectionPlan.from_loose_dict(raw_plan)
                if isinstance(raw_plan, dict)
                else None
            )
            if plan is not None:
                return plan.outline
        raw = payload.get("outline")
        if raw is None:
            return None
        if isinstance(raw, SectionOutline):
            return raw
        if isinstance(raw, dict):
            return SectionOutline.from_loose_dict(raw)
        return None

    @staticmethod
    def _coerce_source(payload: dict[str, Any], section_path: str) -> str:
        """Assemble the section's scoped source text from ``payload``.

        Prefers ``payload["blocks"]`` as a :class:`MemoryBlocks`, rendered at
        ``detail="full"`` scoped to ``section_path`` (section isolation); falls
        back to ``payload["source"]`` / ``["materials"]``.
        """
        blocks_raw = payload.get("blocks")
        if blocks_raw is not None:
            blocks = (
                blocks_raw
                if isinstance(blocks_raw, MemoryBlocks)
                else MemoryBlocks.model_validate(blocks_raw)
            )
            rendered = blocks.select(
                section_path=section_path or None,
                detail="full",
            )
            if rendered:
                return "\n\n".join(rendered)
        source = payload.get("source") or payload.get("materials")
        if source:
            return source if isinstance(source, str) else str(source)
        return ""

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Draft or revise the section in ``task`` and thread it through the session.

        Draft phase (no ``session.data["critic_feedback"]``): assembles the
        section source and outline/plan, builds a ``[system, user]`` conversation
        inlining the vision, this section's goal/plan, the scoped source, and the
        citation/figure hints, calls the LLM, and (when ``files`` +
        ``payload["out_path"]``) writes the draft to a new file.

        Revise phase (feedback present): inlines the current draft and the critic
        feedback and asks for a targeted revision; an existing file is rewritten
        via ``apply_edit`` (whole-body replace).

        Always sets ``session.data["draft"]`` and returns one error-free or
        error-flagged output. Never raises.
        """
        try:
            feedback = session.data.get("critic_feedback")
            phase = "revise" if feedback else "draft"

            if phase == "revise":
                return self._run_revise(task, session, str(feedback))
            return self._run_draft(task, session)
        except FileToolError as exc:
            return self._error(session, f"file tool error: {exc}")
        except Exception as exc:  # noqa: BLE001 - never raise; flag on the output
            return self._error(session, str(exc))

    def _run_draft(self, task: Task, session: SessionContext) -> AgentOutput:
        payload = task.payload
        outline = self._coerce_outline(payload)
        if outline is None:
            return self._error(session, "no 'outline'/'section_plan' provided")

        source = self._coerce_source(payload, outline.section_path)
        if not source and not payload.get("source") and not payload.get("blocks"):
            # Fall back to the task description as raw material.
            source = task.description or ""
        if not source:
            return self._error(session, "no 'blocks'/'source'/'materials' provided")

        vision = str(payload.get("vision", ""))
        messages = self._draft_messages(outline, source, vision)
        draft = self.llm.complete(messages)

        out_path = payload.get("out_path")
        wrote: list[str] = []
        if self.files is not None and out_path:
            path = self.files.write_new(str(out_path), draft)
            wrote.append(str(path))

        session.data["draft"] = draft
        return self._output(
            draft=draft,
            section_path=outline.section_path or outline.title,
            out_path=str(out_path) if out_path else None,
            phase="draft",
            wrote=wrote,
            session=session,
        )

    def _run_revise(self, task: Task, session: SessionContext, feedback: str) -> AgentOutput:
        payload = task.payload
        current = str(session.data.get("draft", ""))
        outline = self._coerce_outline(payload)
        section_path = (outline.section_path or outline.title) if outline else ""

        messages = self._revise_messages(current, feedback, outline)
        revised = self.llm.complete(messages)

        out_path = payload.get("out_path")
        wrote: list[str] = []
        if self.files is not None and out_path and current:
            # Whole-body replace assumes ``current`` (== session.data["draft"])
            # stays in lockstep with the file on disk; an out-of-band write makes
            # ``current`` no longer match and surfaces EditNotApplicableError
            # (flagged, not silent).
            path = self.files.apply_edit(str(out_path), current, revised, count=1)
            wrote.append(str(path))

        session.data["draft"] = revised
        return self._output(
            draft=revised,
            section_path=section_path,
            out_path=str(out_path) if out_path else None,
            phase="revise",
            wrote=wrote,
            session=session,
        )

    def _draft_messages(self, outline: SectionOutline, source: str, vision: str) -> list[Message]:
        parts: list[str] = []
        if vision:
            parts.append(f"Paper vision:\n{vision}")
        parts.append(f"Section: {outline.section_path or outline.title}")
        if outline.goal:
            parts.append(f"Goal of this section:\n{outline.goal}")
        if outline.word_budget:
            parts.append(f"Target length: about {outline.word_budget} words.")
        if outline.citation_hints:
            parts.append(
                "Citation placeholders to use verbatim (do not invent others):\n"
                + "\n".join(f"- {hint}" for hint in outline.citation_hints)
            )
        if outline.figure_refs:
            parts.append(
                "Figure references to keep verbatim:\n"
                + "\n".join(f"- {ref}" for ref in outline.figure_refs)
            )
        parts.append(f"Source material for this section only:\n{source}")
        parts.append(
            "Write the prose for this section now. Use only the source material "
            "above; keep all citation and figure placeholders exactly as given."
        )
        return [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content="\n\n".join(parts)),
        ]

    def _revise_messages(
        self, current: str, feedback: str, outline: SectionOutline | None
    ) -> list[Message]:
        parts: list[str] = []
        if outline is not None and (outline.section_path or outline.title):
            parts.append(f"Section: {outline.section_path or outline.title}")
        parts.append(f"Current draft:\n{current}")
        parts.append(f"Reviewer feedback to address:\n{feedback}")
        parts.append(
            "Revise the section to address every point of feedback. Preserve all "
            "citation and figure placeholders. Return the full revised section."
        )
        return [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content="\n\n".join(parts)),
        ]

    def _output(
        self,
        *,
        draft: str,
        section_path: str,
        out_path: str | None,
        phase: str,
        wrote: list[str],
        session: SessionContext,
    ) -> AgentOutput:
        word_count = len(draft.split())
        summary = f"Wrote {word_count} words for section '{section_path}' ({phase})."
        output = AgentOutput(
            agent=self.name,
            content=draft,
            structured={
                "section_path": section_path,
                "draft": draft,
                "out_path": out_path,
                "word_count": word_count,
            },
            metadata={"phase": phase, "wrote": wrote, "summary": summary},
        )
        session.add(output)
        return output


__all__ = ["WriterExpert", "WRITER_SYSTEM_PROMPT"]

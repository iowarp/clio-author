"""The editor expert: standalone, feedback-driven revision of existing prose.

:class:`EditorExpert` takes a piece of existing prose plus directive feedback and
asks the LLM for a targeted revision. Feedback may come from a structured
:class:`~clio_author.experts.review_models.PaperReview` (its weaknesses /
questions / summary are rendered into directive text), from free-form
``critic_notes``, or from ``session.data["critic_feedback"]``.

Unlike :class:`~clio_author.experts.writer.WriterExpert`, the editor is *not* the
producer in a :class:`CriticRefine` loop; it is a one-shot revision step. When a
harness file ``target`` and a :class:`SafeFiles` are given, the revision is applied
to that file via ``apply_edit`` (whole-body replace); otherwise the revised text is
returned in ``structured``. Like the other experts it never raises: missing inputs
or any failure produce an error-flagged :class:`AgentOutput` (appended once). The
default :class:`EchoLLMClient` keeps it offline.
"""

from __future__ import annotations

from typing import Any

from clio_author.experts.review_models import PaperReview
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.tools.files import FileToolError, SafeFiles

EDITOR_SYSTEM_PROMPT = (
    "You are the editing expert. You revise existing academic prose to address "
    "specific reviewer feedback, making targeted changes while preserving the "
    "author's intent, every citation placeholder (\\cite{key}), and every figure "
    "reference. Do not invent new claims or citations; return the full revised text."
)


def render_review_feedback(review: PaperReview) -> str:
    """Render a :class:`PaperReview` into directive revision feedback text."""
    parts: list[str] = []
    if review.summary:
        parts.append(f"Summary of the review: {review.summary}")
    if review.weaknesses:
        parts.append("Weaknesses to fix:\n" + "\n".join(f"- {w}" for w in review.weaknesses))
    if review.questions:
        parts.append("Questions to address:\n" + "\n".join(f"- {q}" for q in review.questions))
    return "\n\n".join(parts)


class EditorExpert(BaseAgent):
    """Expert that revises existing prose to address feedback."""

    def __init__(self, llm: LLMClient | None = None, *, files: SafeFiles | None = None) -> None:
        """Build an editor expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            files: Optional :class:`SafeFiles`; when given with ``payload["target"]``
                the revision is read from and applied to that file.
        """
        self.files = files
        super().__init__(
            role="editor",
            system_prompt=EDITOR_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _coerce_review(raw: Any) -> PaperReview | None:
        """Coerce ``raw`` into a :class:`PaperReview` (model/dict) or ``None``."""
        if isinstance(raw, PaperReview):
            return raw
        if isinstance(raw, dict):
            return PaperReview.from_loose_dict(raw)
        return None

    def _resolve_prose(self, payload: dict[str, Any], session: SessionContext) -> str:
        """Read the prose to edit from payload / session / file ``target``."""
        prose = payload.get("draft") or session.data.get("draft")
        if prose:
            return str(prose)
        target = payload.get("target")
        if self.files is not None and target:
            return self.files.read(str(target))
        return ""

    def _resolve_feedback(self, payload: dict[str, Any], session: SessionContext) -> str:
        """Render directive feedback from a review / notes / session feedback."""
        review = self._coerce_review(payload.get("review"))
        if review is not None:
            rendered = render_review_feedback(review)
            if rendered:
                return rendered
        notes = payload.get("critic_notes") or session.data.get("critic_feedback")
        return str(notes) if notes else ""

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Revise the prose in ``task`` to address its feedback. Never raises.

        Reads prose from ``payload["draft"]`` / ``session.data["draft"]`` /
        ``files.read(payload["target"])`` and feedback from ``payload["review"]``
        (a :class:`PaperReview`) / ``payload["critic_notes"]`` /
        ``session.data["critic_feedback"]``. Calls the LLM for a targeted
        revision, applies it via ``apply_edit`` when a file ``target`` is given,
        and returns one output whose ``structured`` carries the revised text.
        """
        try:
            payload = task.payload
            prose = self._resolve_prose(payload, session)
            if not prose:
                return self._error(session, "no prose to edit ('draft'/'target' not provided)")
            feedback = self._resolve_feedback(payload, session)
            if not feedback:
                return self._error(session, "no feedback ('review'/'critic_notes' not provided)")

            messages = [
                Message(role="system", content=self.system_prompt),
                Message(
                    role="user",
                    content=(
                        f"Current text:\n{prose}\n\n"
                        f"Feedback to address:\n{feedback}\n\n"
                        "Revise the text to address every point above. Preserve all "
                        "citation and figure placeholders. Return the full revised text."
                    ),
                ),
            ]
            revised = self.llm.complete(messages)

            target = payload.get("target")
            wrote: list[str] = []
            if self.files is not None and target:
                # Whole-body replace assumes ``prose`` (== session.data["draft"])
                # stays in lockstep with the file on disk; an out-of-band write
                # makes ``prose`` no longer match and surfaces
                # EditNotApplicableError (flagged, not silent).
                path = self.files.apply_edit(str(target), prose, revised, count=1)
                wrote.append(str(path))

            session.data["draft"] = revised
        except FileToolError as exc:
            return self._error(session, f"file tool error: {exc}")
        except Exception as exc:  # noqa: BLE001 - never raise; flag on the output
            return self._error(session, str(exc))

        output = AgentOutput(
            agent=self.name,
            content=revised,
            structured={
                "revised": revised,
                "target": str(target) if target else None,
                "word_count": len(revised.split()),
            },
            metadata={"wrote": wrote},
        )
        session.add(output)
        return output


__all__ = ["EditorExpert", "EDITOR_SYSTEM_PROMPT", "render_review_feedback"]

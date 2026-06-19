"""The rebuttal expert: author response to a peer review, point by point.

:class:`RebuttalExpert` takes a manuscript plus a peer review and asks the LLM for
an author rebuttal that addresses each weakness and question in turn -- grounded
strictly in the paper, inventing no new results or citations. The review may be a
structured :class:`~clio_author.experts.review_models.PaperReview` (its weaknesses
/ questions / summary are rendered into directive text via
:func:`~clio_author.experts.editor.render_review_feedback`) or free-form
``review_text`` / ``critic_notes``.

It mirrors the shape of :class:`~clio_author.experts.editor.EditorExpert`: a
one-shot step that defaults to :class:`EchoLLMClient` (offline) and, when a
:class:`SafeFiles` and ``payload["target"]`` are given, applies the rebuttal to
that file. Like the other experts it never raises: missing inputs or any failure
produce an error-flagged :class:`AgentOutput` (appended once).

Completing the review -> rebuttal -> meta-review lifecycle closes a gap surfaced
by the MOPRD peer-review dataset (rebuttals and meta-reviews are first-class
artefacts of the review process, not just the review itself).
"""

from __future__ import annotations

from typing import Any

from clio_author.experts.editor import render_review_feedback
from clio_author.experts.review_models import PaperReview
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.ingest.blocks import MemoryBlocks
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.tools.files import FileToolError, SafeFiles

REBUTTAL_SYSTEM_PROMPT = (
    "You are the author responding to a peer review. Write a respectful, "
    "point-by-point rebuttal that addresses each weakness and question, grounded "
    "strictly in the paper; concede what is fair, clarify misunderstandings, and "
    "propose concrete revisions; do not invent results or citations."
)


class RebuttalExpert(BaseAgent):
    """Expert that drafts an author rebuttal addressing a review point by point."""

    def __init__(self, llm: LLMClient | None = None, *, files: SafeFiles | None = None) -> None:
        """Build a rebuttal expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            files: Optional :class:`SafeFiles`; when given with ``payload["target"]``
                the rebuttal is applied to that file.
        """
        self.files = files
        super().__init__(
            role="rebuttal",
            system_prompt=REBUTTAL_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _coerce_paper(raw: Any) -> str:
        """Render ``raw`` manuscript input into rebuttal-ready Markdown text.

        Accepts a Markdown ``str`` directly, or a
        :class:`~clio_author.ingest.blocks.MemoryBlocks` (or its ``model_dump``
        dict), rendering the latter at ``detail="full"``.
        """
        if isinstance(raw, str):
            return raw
        blocks = raw if isinstance(raw, MemoryBlocks) else MemoryBlocks.model_validate(raw)
        return "\n\n".join(blocks.select(detail="full"))

    @staticmethod
    def _resolve_review(payload: dict[str, Any]) -> str:
        """Render the review into directive text from a model / dict / free text."""
        raw = payload.get("review")
        if isinstance(raw, PaperReview):
            rendered = render_review_feedback(raw)
            if rendered:
                return rendered
        elif isinstance(raw, dict):
            rendered = render_review_feedback(PaperReview.from_loose_dict(raw))
            if rendered:
                return rendered
        elif isinstance(raw, str) and raw.strip():
            return raw
        notes = payload.get("review_text") or payload.get("critic_notes")
        return str(notes) if notes else ""

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Draft an author rebuttal to the review in ``task``. Never raises.

        Reads the manuscript from ``payload["paper"]`` / ``["draft"]`` /
        ``["markdown"]`` and the review from ``payload["review"]`` (a
        :class:`PaperReview` dump/dict), ``payload["review_text"]``, or
        ``payload["critic_notes"]``. Calls the LLM once and returns one output
        whose ``content`` and ``structured["rebuttal"]`` carry the rebuttal text.
        When a :class:`SafeFiles` and ``payload["target"]`` are given, the rebuttal
        is written to that file. Missing inputs produce an error-flagged output.
        """
        try:
            payload = task.payload
            raw_paper = payload.get("paper") or payload.get("draft") or payload.get("markdown")
            if not raw_paper:
                return self._error(session, "no 'paper'/'draft'/'markdown' provided")
            review = self._resolve_review(payload)
            if not review:
                return self._error(session, "no 'review'/'review_text'/'critic_notes' provided")

            paper_text = self._coerce_paper(raw_paper)
            messages = [
                Message(role="system", content=self.system_prompt),
                Message(
                    role="user",
                    content=(
                        f"Here is the paper:\n```\n{paper_text}\n```\n\n"
                        f"Here is the peer review to respond to:\n{review}\n\n"
                        "Write a respectful, point-by-point author rebuttal that "
                        "addresses every weakness and question above. Ground every "
                        "response in the paper; do not invent new results or citations."
                    ),
                ),
            ]
            rebuttal = self.llm.complete(messages)

            target = payload.get("target")
            wrote: list[str] = []
            if self.files is not None and target:
                path = self.files.write_new(str(target), rebuttal)
                wrote.append(str(path))
        except FileToolError as exc:
            return self._error(session, f"file tool error: {exc}")
        except Exception as exc:  # noqa: BLE001 - never raise; flag on the output
            return self._error(session, str(exc))

        output = AgentOutput(
            agent=self.name,
            content=rebuttal,
            structured={"rebuttal": rebuttal},
            metadata={"wrote": wrote} if wrote else {},
        )
        session.add(output)
        return output


__all__ = ["RebuttalExpert", "REBUTTAL_SYSTEM_PROMPT"]

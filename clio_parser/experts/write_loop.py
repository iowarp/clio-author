"""Writer <-> reviewer refinement loop wiring.

:class:`ReviewerExpert` produces structured reviews but never emits the
:data:`~clio_parser.harness.patterns.NO_CHANGES_SENTINEL` that
:class:`~clio_parser.harness.patterns.CriticRefine` uses to stop early.
:class:`ReviewerAsCritic` adapts a reviewer into a critic: on an ``Accept``
decision (or a review with no weaknesses) it emits the sentinel; otherwise it
renders the weaknesses / questions as feedback so ``CriticRefine`` threads them
into ``session.data["critic_feedback"]`` for the writer's revise phase.

:func:`run_write_review_loop` wires a :class:`WriterExpert` (producer) and a
``ReviewerAsCritic``-wrapped reviewer through ``CriticRefine`` over an
:class:`~clio_parser.harness.engine.Engine`. ``patterns.py`` is not modified.
"""

from __future__ import annotations

from clio_parser.experts.reviewer import ReviewerExpert
from clio_parser.experts.writer import WriterExpert
from clio_parser.harness.engine import Engine
from clio_parser.harness.patterns import NO_CHANGES_SENTINEL, CriticRefine
from clio_parser.harness.protocol import AgentProtocol
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Task


class ReviewerAsCritic:
    """Adapt a :class:`ReviewerExpert` into a :class:`CriticRefine` critic.

    Runs the wrapped reviewer, then maps its structured review onto a critic
    output: an ``Accept`` decision or a review with no weaknesses yields the
    :data:`NO_CHANGES_SENTINEL` (loop stops); otherwise the weaknesses and
    questions are rendered as feedback content. An error-flagged or unparsed
    reviewer output is passed through unchanged so the loop halts gracefully.
    """

    def __init__(self, reviewer: ReviewerExpert) -> None:
        self.reviewer = reviewer

    @property
    def name(self) -> str:
        """The critic's identifier."""
        return "reviewer-critic"

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Review the current draft and emit a critic signal. Never raises.

        The reviewer reviews ``session.data["draft"]`` (threaded by
        ``CriticRefine``), falling back to the task's own paper payload. The
        returned output's ``content`` is either the sentinel or rendered
        feedback; ``structured`` carries the underlying review.
        """
        # Review the current draft when the loop has produced one.
        draft = session.data.get("draft")
        review_task = task
        if draft:
            review_task = Task(
                id=task.id,
                description=task.description,
                payload={**task.payload, "paper": str(draft)},
            )

        review_output = self.reviewer.run(review_task, session)
        if "error" in review_output.metadata or review_output.structured is None:
            # A degraded (error or unparsed) review cannot drive a revision, so
            # flag an error on a critic output to halt CriticRefine cleanly. The
            # original reviewer output is already on the session history.
            reason = review_output.metadata.get("error") or review_output.metadata.get(
                "parse_error", "reviewer produced no structured review"
            )
            output = AgentOutput(
                agent=self.name,
                content=review_output.content,
                structured=review_output.structured,
                metadata={"error": str(reason)},
            )
            session.add(output)
            return output

        structured = review_output.structured
        decision = structured.get("decision")
        weaknesses = list(structured.get("weaknesses") or [])
        questions = list(structured.get("questions") or [])

        if decision == "Accept" or not weaknesses:
            content = NO_CHANGES_SENTINEL
        else:
            parts = ["Weaknesses to address:"]
            parts.extend(f"- {w}" for w in weaknesses)
            if questions:
                parts.append("Questions to address:")
                parts.extend(f"- {q}" for q in questions)
            content = "\n".join(parts)

        output = AgentOutput(
            agent=self.name,
            content=content,
            structured=structured,
            metadata={
                "decision": decision,
                "weakness_count": len(weaknesses),
            },
        )
        session.add(output)
        return output


def run_write_review_loop(
    task: Task,
    *,
    writer: WriterExpert,
    reviewer: ReviewerExpert,
    max_rounds: int = 3,
    session: SessionContext | None = None,
) -> list[AgentOutput]:
    """Run a writer/reviewer :class:`CriticRefine` loop and return its history.

    The writer drafts once, then for up to ``max_rounds`` rounds a
    :class:`ReviewerAsCritic`-wrapped ``reviewer`` reviews the draft and the
    writer revises in response, stopping on an ``Accept`` (sentinel) or an
    error-flagged output. Returns the full ordered output history.
    """
    # Build a fresh task so the caller's payload dict is never mutated.
    loop_task = task.model_copy(update={"payload": {**task.payload, "max_rounds": max_rounds}})
    agents: list[AgentProtocol] = [writer, ReviewerAsCritic(reviewer)]
    return Engine().run(agents, CriticRefine(), loop_task, session)


__all__ = ["ReviewerAsCritic", "run_write_review_loop"]

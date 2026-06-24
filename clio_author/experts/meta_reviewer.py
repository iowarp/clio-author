"""The meta-reviewer expert and the multi-reviewer panel runner.

:class:`MetaReviewerExpert` plays an inclusive area-chair: it aggregates several
:class:`~clio_author.experts.review_models.PaperReview`s into a single
:class:`~clio_author.experts.review_models.MetaReview`. The aggregation is a
deterministic, offline fallback (rounded mean of each numeric axis plus a
majority/threshold decision) so a panel runs hermetically with no canned JSON; an
LLM-driven synthesis path can layer on top later.

The blind-review -> synthesis flow re-implements the *concept* of independent
synthesis (multiple independent reviews aggregated by a separate area-chair
persona). No AGPL source is copied; the review field set and rubric are adapted
from the AgentReview prompt in PaperOrchestra (Apache-2.0) -- see
:mod:`clio_author.experts.review_models`.

Like the other experts, this never raises: bad input yields an error-flagged
:class:`~clio_author.harness.types.AgentOutput` (appended once).

Variance-triggered escalation to a RoundRobin discussion among reviewers is
deferred to a later milestone.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import mean, pstdev
from typing import Any

from clio_author.experts.review_models import MetaReview, PaperReview, PersonaSpec
from clio_author.experts.reviewer import ReviewerExpert
from clio_author.harness.base import BaseAgent
from clio_author.harness.engine import Engine
from clio_author.harness.patterns import Parallel
from clio_author.harness.protocol import AgentProtocol
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.llm.client import EchoLLMClient, LLMClient

META_REVIEWER_SYSTEM_PROMPT = (
    "You are a knowledgeable, experienced area chair at a top-tier venue. You "
    "meta-review a paper that was reviewed by several reviewers, aggregating "
    "their reviews into a single meta-review in the same format. You are "
    "inclusive: you weigh all reviewers' opinions together with your own "
    "judgment to reach the final decision."
)

# Numeric axes aggregated by the deterministic fallback, with their bounds.
_AXES: dict[str, tuple[int, int]] = dict(PaperReview._AXIS_BOUNDS)

# Mean-overall threshold at/above which the fallback decision is "Accept".
_ACCEPT_OVERALL_THRESHOLD = 6


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def review_robustness(reviews: Sequence[PaperReview]) -> dict[str, Any]:
    """How trustworthy is the verdict, given how much the reviewers disagree?

    Inspired by AgentReview's finding that a large share of accept/reject
    decisions is driven by reviewer variance rather than the paper. Deterministic:
    ``agreement`` is the fraction siding with the majority decision; ``overall_std``
    is the spread of overall ratings. The ``label`` is **solid** (reviewers agree,
    tight scores), **split** (they disagree or scores are wide), else **borderline**.
    """
    n = len(reviews)
    if n == 0:
        return {"agreement": 1.0, "overall_std": 0.0, "label": "solid", "reviewer_count": 0}
    accept = sum(1 for r in reviews if r.decision == "Accept")
    agreement = max(accept, n - accept) / n
    overalls = [r.overall for r in reviews]
    overall_std = pstdev(overalls) if n > 1 else 0.0
    if agreement >= 0.8 and overall_std <= 1.0:
        label = "solid"
    elif agreement < 0.6 or overall_std > 2.0:
        label = "split"
    else:
        label = "borderline"
    return {
        "agreement": round(agreement, 3),
        "overall_std": round(overall_std, 3),
        "label": label,
        "reviewer_count": n,
    }


class MetaReviewerExpert(BaseAgent):
    """Expert that synthesizes multiple reviews into one :class:`MetaReview`."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        """Build a meta-reviewer expert (defaults to offline :class:`EchoLLMClient`)."""
        super().__init__(
            role="meta_reviewer",
            system_prompt=META_REVIEWER_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _coerce_reviews(raw: Any) -> list[PaperReview]:
        """Coerce a sequence of :class:`PaperReview`/dicts into PaperReviews."""
        reviews: list[PaperReview] = []
        if not isinstance(raw, (list, tuple)):
            return reviews
        for item in raw:
            if isinstance(item, PaperReview):
                reviews.append(item)
            elif isinstance(item, dict):
                reviews.append(PaperReview.from_loose_dict(item))
        return reviews

    @staticmethod
    def _reviews_from_history(session: SessionContext) -> list[PaperReview]:
        """Recover reviews from reviewer outputs recorded on the session."""
        reviews: list[PaperReview] = []
        for output in session.history:
            if output.agent != "reviewer" or not output.structured:
                continue
            reviews.append(PaperReview.from_loose_dict(output.structured))
        return reviews

    @staticmethod
    def aggregate(reviews: Sequence[PaperReview]) -> MetaReview:
        """Deterministically aggregate ``reviews`` into a :class:`MetaReview`.

        Each numeric axis is the rounded mean of that axis across the reviews
        (clamped into bounds). The decision is ``"Accept"`` when the mean overall
        rating is at least the accept threshold or a majority of reviewers voted
        Accept; otherwise ``"Reject"``. Text fields are concatenated across
        reviews, and ``ethical_concerns`` is the OR of the reviewers'.
        """
        data: dict[str, Any] = {"reviewer_count": len(reviews)}
        for axis, (low, high) in _AXES.items():
            values = [getattr(review, axis) for review in reviews]
            data[axis] = _clamp(int(round(mean(values))), low, high) if values else low

        for field in ("strengths", "weaknesses", "questions", "limitations"):
            merged: list[str] = []
            for review in reviews:
                merged.extend(getattr(review, field))
            data[field] = merged

        data["ethical_concerns"] = any(review.ethical_concerns for review in reviews)
        data["summary"] = " ".join(review.summary for review in reviews if review.summary).strip()

        accept_votes = sum(1 for review in reviews if review.decision == "Accept")
        mean_overall = mean(review.overall for review in reviews) if reviews else 0
        majority_accept = reviews and accept_votes > len(reviews) / 2
        data["decision"] = (
            "Accept" if (mean_overall >= _ACCEPT_OVERALL_THRESHOLD or majority_accept) else "Reject"
        )

        return MetaReview.model_validate(data)

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Aggregate reviews into a :class:`MetaReview` and record the output.

        Reads reviews from ``task.payload["reviews"]`` (a list of
        :class:`PaperReview`/dicts) or, when absent, from the structured reviewer
        outputs on ``session.history``. Uses the deterministic
        :meth:`aggregate` fallback so the run is hermetic. ``structured`` is the
        meta-review's ``model_dump()`` and ``metadata`` carries ``decision`` /
        ``overall`` / ``reviewer_count``. Never raises: no reviews or any failure
        produces an error-flagged output (appended once).
        """
        try:
            raw = task.payload.get("reviews")
            reviews = self._coerce_reviews(raw) if raw is not None else []
            if not reviews:
                reviews = self._reviews_from_history(session)
            if not reviews:
                return self._error(session, "no reviews to aggregate")

            meta = self.aggregate(reviews)
            robustness = review_robustness(reviews)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        structured = meta.model_dump()
        structured["robustness"] = robustness
        output = AgentOutput(
            agent=self.name,
            content=(
                f"Meta-decision: {meta.decision} (overall {meta.overall}/10) "
                f"from {meta.reviewer_count} reviewer(s); verdict is {robustness['label']} "
                f"(agreement {robustness['agreement']}, score spread {robustness['overall_std']})."
            ),
            structured=structured,
            metadata={
                "decision": meta.decision,
                "overall": meta.overall,
                "reviewer_count": meta.reviewer_count,
                "robustness": robustness["label"],
            },
        )
        session.add(output)
        return output


def run_panel(
    paper: Any,
    personas: Sequence[PersonaSpec],
    llm: LLMClient | None = None,
    *,
    synthesize: bool = True,
) -> list[AgentOutput]:
    """Run a blind review panel over ``paper`` and optionally synthesize.

    Builds one :class:`ReviewerExpert` per persona (sharing ``llm``, default
    :class:`EchoLLMClient`), runs them on the same paper via the
    :class:`~clio_author.harness.patterns.Parallel` pattern, then -- when
    ``synthesize`` is set -- appends a :class:`MetaReviewerExpert` aggregation
    over the reviewers' structured outputs.

    Returns the full ordered list of outputs: ``N`` reviewer outputs followed by
    one meta-review (when synthesizing). Hermetic by default; never raises (each
    expert flags its own failures).
    """
    client = llm or EchoLLMClient()
    reviewers: list[AgentProtocol] = [
        ReviewerExpert(llm=client, persona=persona) for persona in personas
    ]
    session = SessionContext(id="panel")
    task = Task(id="panel", description="review", payload={"paper": paper})

    engine = Engine()
    outputs = list(engine.run(reviewers, Parallel(), task, session))

    if synthesize:
        meta = MetaReviewerExpert(llm=client)
        outputs.append(meta.run(task, session))

    return outputs


__all__ = [
    "MetaReviewerExpert",
    "META_REVIEWER_SYSTEM_PROMPT",
    "run_panel",
    "review_robustness",
]

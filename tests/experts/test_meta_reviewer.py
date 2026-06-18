"""Hermetic tests for :class:`MetaReviewerExpert` and :func:`run_panel`.

Covers the deterministic aggregation of canned reviews (mean axes, majority
decision), a ``run_panel`` over the :class:`Parallel` pattern producing N reviews
plus one meta-review, and the offline echo fallback that never raises.
"""

from __future__ import annotations

from clio_author.experts.meta_reviewer import MetaReviewerExpert, run_panel
from clio_author.experts.review_models import MetaReview, PaperReview, PersonaSpec
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Task


def _review(overall: int, decision: str, originality: int) -> PaperReview:
    return PaperReview.from_loose_dict(
        {
            "Summary": f"review with overall {overall}",
            "Strengths": ["s"],
            "Weaknesses": ["w"],
            "Originality": originality,
            "Overall": overall,
            "Confidence": 3,
            "Decision": decision,
        }
    )


def test_meta_reviewer_aggregates_mean_and_majority() -> None:
    reviews = [
        _review(8, "Accept", 4),
        _review(7, "Accept", 3),
        _review(3, "Reject", 2),
    ]
    expert = MetaReviewerExpert()
    session = SessionContext(id="s")
    task = Task(id="t", description="meta", payload={"reviews": reviews})

    output = expert.run(task, session)

    assert output.structured is not None
    meta = MetaReview.model_validate(output.structured)
    assert meta.reviewer_count == 3
    assert meta.overall == 6  # round(mean(8,7,3)) = round(6.0)
    assert meta.originality == 3  # round(mean(4,3,2)) = 3
    # mean overall 6.0 >= threshold AND majority accept -> Accept.
    assert meta.decision == "Accept"
    assert output.metadata["reviewer_count"] == 3
    assert session.history == [output]


def test_meta_reviewer_majority_reject_below_threshold() -> None:
    reviews = [_review(4, "Reject", 2), _review(4, "Reject", 2), _review(6, "Accept", 3)]
    expert = MetaReviewerExpert()
    session = SessionContext(id="s")
    output = expert.run(Task(id="t", description="meta", payload={"reviews": reviews}), session)

    meta = MetaReview.model_validate(output.structured)
    # mean overall = round((4+4+6)/3) = round(4.67) = 5 < 6, majority Reject.
    assert meta.overall == 5
    assert meta.decision == "Reject"


def test_meta_reviewer_accepts_dicts() -> None:
    reviews = [{"Overall": 8, "Decision": "Accept"}, {"Overall": 7, "Decision": "Accept"}]
    expert = MetaReviewerExpert()
    session = SessionContext(id="s")
    output = expert.run(Task(id="t", description="meta", payload={"reviews": reviews}), session)

    assert output.structured is not None
    assert output.metadata["decision"] == "Accept"


def test_meta_reviewer_no_reviews_errors() -> None:
    expert = MetaReviewerExpert()
    session = SessionContext(id="s")
    output = expert.run(Task(id="t", description="meta", payload={}), session)

    assert output.content == ""
    assert "error" in output.metadata


def test_run_panel_produces_n_reviews_and_one_meta() -> None:
    personas = [
        PersonaSpec(label="r1"),
        PersonaSpec(label="r2"),
        PersonaSpec(label="r3"),
    ]
    outputs = run_panel("# Paper\nbody", personas, synthesize=True)

    # 3 reviewers (echo -> parse_error) + 1 meta-reviewer.
    assert len(outputs) == 4
    assert [o.agent for o in outputs[:3]] == ["reviewer", "reviewer", "reviewer"]
    assert outputs[-1].agent == "meta_reviewer"


def test_run_panel_offline_echo_falls_back_without_raising() -> None:
    personas = [PersonaSpec(label="r1"), PersonaSpec(label="r2")]
    outputs = run_panel("# Paper", personas, synthesize=True)

    # Echo reviewers parse_error -> no structured reviews -> meta-reviewer errors,
    # but nothing raises and every output is recorded.
    reviewers = outputs[:2]
    assert all("parse_error" in o.metadata for o in reviewers)
    meta = outputs[-1]
    assert meta.agent == "meta_reviewer"
    assert "error" in meta.metadata


def test_run_panel_without_synthesis() -> None:
    personas = [PersonaSpec(label="r1")]
    outputs = run_panel("# Paper", personas, synthesize=False)

    assert len(outputs) == 1
    assert outputs[0].agent == "reviewer"

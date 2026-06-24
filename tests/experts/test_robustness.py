"""Tests for the deterministic review-robustness signal (AgentReview-inspired)."""

from __future__ import annotations

from clio_author.experts.meta_reviewer import MetaReviewerExpert, review_robustness
from clio_author.experts.review_models import PaperReview
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Task


def _review(decision: str, overall: int) -> PaperReview:
    return PaperReview.from_loose_dict({"decision": decision, "overall": overall})


def test_unanimous_tight_is_solid() -> None:
    r = review_robustness([_review("Accept", 8), _review("Accept", 8), _review("Accept", 7)])
    assert r["label"] == "solid"
    assert r["agreement"] == 1.0


def test_disagreement_is_split() -> None:
    r = review_robustness([_review("Accept", 9), _review("Reject", 3), _review("Reject", 4)])
    assert r["label"] == "split"
    assert r["agreement"] < 0.7


def test_meta_review_attaches_robustness() -> None:
    out = MetaReviewerExpert().run(
        Task(
            id="t",
            description="meta_review",
            payload={
                "reviews": [
                    {"decision": "Accept", "overall": 8},
                    {"decision": "Reject", "overall": 3},
                ]
            },
        ),
        SessionContext(id="s"),
    )
    assert "robustness" in out.structured
    assert out.metadata["robustness"] in {"solid", "borderline", "split"}

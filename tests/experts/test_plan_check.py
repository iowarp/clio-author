"""Hermetic tests for :class:`PlanCheckExpert` (deterministic pre-write check).

No LLM is involved: the same plan always yields the same checklist. Covers the
clean-plan pass, each failure dimension, the word-target tolerance, and the
missing-input error path.
"""

from __future__ import annotations

from clio_author.experts.plan_check import PlanCheckExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Task


def _task(**payload: object) -> Task:
    return Task(id="t", description="plan_check", payload={**payload, "action": "plan_check"})


def _good_plan() -> dict:
    return {
        "outline": {"title": "P", "sections": [{"title": "Intro"}, {"title": "Method"}]},
        "plans": [
            {
                "outline": {"title": "Intro", "word_budget": 300},
                "tasks": ["write the intro"],
                "claims": ["X matters"],
                "sources": ["smith2020"],
            },
            {
                "outline": {"title": "Method", "word_budget": 500},
                "tasks": ["describe the method"],
                "claims": ["Y works"],
                "sources": ["jones2021"],
            },
        ],
    }


def test_clean_plan_passes() -> None:
    out = PlanCheckExpert().run(_task(plan=_good_plan()), SessionContext(id="s"))
    assert out.metadata["passed"] is True
    assert out.metadata["num_problems"] == 0
    assert out.structured["budget_total"] == 800


def test_each_failure_dimension_is_flagged() -> None:
    plan = {
        "outline": {"title": "P", "sections": [{"title": "Intro"}, {"title": "Missing"}]},
        "plans": [
            {
                # claim but no source/hint -> uncited; research_needed but no topics
                "outline": {"title": "Intro", "word_budget": 0, "research_needed": True},
                "tasks": [],  # taskless
                "claims": ["unbacked claim"],  # uncited
                "sources": [],
            }
        ],
    }
    out = PlanCheckExpert().run(_task(plan=plan), SessionContext(id="s"))
    s = out.structured
    assert out.metadata["passed"] is False
    assert "Missing" in s["missing_plans"]  # outline section with no plan
    assert "Intro" in s["taskless"]
    assert "Intro" in s["uncited_claim_sections"]
    assert "Intro" in s["missing_budgets"]  # word_budget 0 -> treated as missing
    assert "Intro" in s["unresolved_research"]


def test_word_target_tolerance() -> None:
    plan = _good_plan()  # budgets sum to 800
    # within 15% of 850 -> ok
    ok = PlanCheckExpert().run(_task(plan=plan, word_target=850), SessionContext(id="s"))
    assert ok.structured["budget_ok"] is True
    # 800 vs 2000 is far outside tolerance -> flagged
    bad = PlanCheckExpert().run(_task(plan=plan, word_target=2000), SessionContext(id="s"))
    assert bad.structured["budget_ok"] is False
    assert bad.metadata["passed"] is False


def test_missing_plan_is_error_flagged() -> None:
    out = PlanCheckExpert().run(_task(), SessionContext(id="s"))
    assert "error" in out.metadata

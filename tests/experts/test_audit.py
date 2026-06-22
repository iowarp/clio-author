"""Hermetic tests for :class:`AuditExpert` (deterministic, no LLM)."""

from __future__ import annotations

from clio_author.experts.audit import AuditExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Task
from clio_author.retrieval.scholar import S2Record, VerifiedCitation


def _run(payload: dict[str, object]) -> object:
    return AuditExpert().run(
        Task(id="t", description="audit", payload=payload), SessionContext(id="s")
    )


def test_audit_clean_manuscript_passes() -> None:
    out = _run(
        {
            "sections": [
                {"title": "Intro", "draft": "one two three four five", "word_budget": 5},
            ],
            "bibtex": "@article{a, title = {X}}",
        }
    )
    assert out.agent == "audit"
    assert "error" not in out.metadata
    assert out.metadata["passed"] is True
    assert "PASSED" in out.content


def test_audit_flags_placeholders_and_budget() -> None:
    out = _run(
        {
            "sections": [
                {"title": "Intro", "draft": "short [TODO] and \\cite{}", "word_budget": 100},
            ],
        }
    )
    s = out.structured
    assert s is not None
    assert s["placeholders"]["todo"] == 1
    assert s["placeholders"]["empty_cite"] == 1
    assert any(w["under_budget"] for w in s["word_counts"])
    assert out.metadata["passed"] is False


def test_audit_missing_required_section_from_outline() -> None:
    out = _run(
        {
            "sections": [{"title": "Intro", "draft": "body text here yes"}],
            "outline": {"title": "P", "sections": [{"title": "Intro"}, {"title": "Conclusion"}]},
        }
    )
    s = out.structured
    assert s is not None
    assert "Conclusion" in s["missing_sections"]


def test_audit_citation_coverage_uncovered() -> None:
    out = _run(
        {
            "markdown": "## Intro\n\nbody with \\cite{ghost}.",
            "bibtex": "@article{real, title = {X}}",
        }
    )
    s = out.structured
    assert s is not None
    assert s["coverage"]["uncovered_cites"] == ["ghost"]


def test_audit_verified_coverage_meets_90pct() -> None:
    record = S2Record(paper_id="p1", title="X", year=2020, abstract="...")
    verified = [
        VerifiedCitation(record=record, score=99.0, citation_key="x2020", bibtex="@article{x2020}")
    ]
    out = _run(
        {
            "sections": [{"title": "Intro", "draft": "body text"}],
            "candidates": [{"title": "X", "year": 2020}],
            "verified": [v.model_dump() for v in verified],
        }
    )
    s = out.structured
    assert s is not None
    assert s["coverage"]["meets_90pct"] is True


def test_audit_empty_payload_errors() -> None:
    out = _run({})
    assert "error" in out.metadata
    assert out.structured is None

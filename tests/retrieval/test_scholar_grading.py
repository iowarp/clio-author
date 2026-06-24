"""Hermetic tests for graded citation verification (CiteCheck/CiteGuard-style).

`grade_reference` labels a candidate Exact / Minor / Major from retrieved records
and surfaces alternative real titles; `verify_and_grade` does it with one search
per reference via the offline `FakeScholarClient`; `grade_summary` rolls up the
citation-integrity ratio. No network.
"""

from __future__ import annotations

from clio_author.retrieval.scholar import (
    FakeScholarClient,
    GradedCitation,
    Reference,
    S2Record,
    grade_reference,
    grade_summary,
    verify_and_grade,
)

_TITLE = "neural machine translation by jointly learning to align and translate"


def _rec(title: str, year: int = 2015, pid: str = "p1") -> S2Record:
    return S2Record(
        paper_id=pid,
        title=title,
        authors=["Dzmitry Bahdanau"],
        year=year,
        abstract="An attention mechanism for translation.",
    )


def test_grade_exact_when_title_and_year_match() -> None:
    g = grade_reference(Reference(query_title=_TITLE, year_hint=2015), [_rec(_TITLE)])
    assert g.severity == "exact"
    assert g.score >= 92
    assert g.matched_title == _TITLE


def test_grade_minor_on_year_drift() -> None:
    # Title matches perfectly but the year hint disagrees -> metadata drift = minor.
    g = grade_reference(Reference(query_title=_TITLE, year_hint=1999), [_rec(_TITLE, year=2015)])
    assert g.severity == "minor"
    assert g.matched_title == _TITLE


def test_grade_major_when_nothing_matches() -> None:
    g = grade_reference(Reference(query_title="a totally fabricated paper title xyz"), [])
    assert g.severity == "major"
    assert g.matched_title is None


def test_grade_surfaces_alternatives() -> None:
    alt = _rec(_TITLE + " (extended journal version)", pid="p2")
    g = grade_reference(Reference(query_title=_TITLE), [_rec(_TITLE), alt])
    assert g.severity == "exact"
    assert any("extended journal version" in a for a in g.alternatives)


def test_verify_and_grade_one_search_per_ref() -> None:
    client = FakeScholarClient({_TITLE: [_rec(_TITLE)]})
    verified, graded = verify_and_grade([Reference(query_title=_TITLE, year_hint=2015)], client)
    assert len(graded) == 1 and graded[0].severity == "exact"
    assert len(verified) == 1  # the strict path still yields a BibTeX-able match


def test_grade_summary_counts_and_integrity() -> None:
    graded = [
        GradedCitation(candidate_title="a", severity="exact", score=99),
        GradedCitation(candidate_title="b", severity="minor", score=80),
        GradedCitation(candidate_title="c", severity="major", score=10),
    ]
    s = grade_summary(graded)
    assert s["counts"] == {"exact": 1, "minor": 1, "major": 1}
    assert abs(s["citation_integrity"] - (2 / 3)) < 1e-9

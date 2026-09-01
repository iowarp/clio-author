"""Regressions for citation verification reporting a real paper with wrong metadata.

Verifying "Attention Is All You Need" returned ``severity: exact`` and
``citation_integrity: 1.0`` while handing back ``year = {2025}`` for a 2017 paper.
Nothing in the result said the year was unchecked, and the BibTeX was malformed on
top of it. These tests pin each half of that.
"""

from __future__ import annotations

from clio_author.retrieval.scholar import (
    Reference,
    S2Record,
    _bibtex,
    best_match,
    grade_reference,
    year_conflicts,
)

_ABSTRACT = "The dominant sequence transduction models are based on recurrent networks."
_AUTHORS = ["Ashish Vaswani", "Noam Shazeer"]


def _openalex_2025() -> S2Record:
    """The real record that caused this: right paper, refreshed 2025 date."""
    return S2Record(
        paper_id="openalex:https://openalex.org/W2626778328",
        title="Attention Is All You Need",
        authors=_AUTHORS,
        year=2025,
        publication_date="2025-08-23",
        venue=None,
        abstract=_ABSTRACT,
    )


def _arxiv_2017() -> S2Record:
    return S2Record(
        paper_id="arxiv:1706.03762v7",
        title="Attention Is All You Need",
        authors=_AUTHORS,
        year=2017,
        publication_date="2017-06-12",
        venue="arXiv",
        abstract=_ABSTRACT,
    )


# --------------------------------------------------------------------------- #
# selection: a tie must not be decided by which backend was configured first
# --------------------------------------------------------------------------- #


def test_best_match_prefers_the_earliest_year_on_a_tie() -> None:
    """Cascade order used to decide, so OpenAlex's 2025 date beat arXiv's 2017."""
    records = [_openalex_2025(), _arxiv_2017()]  # OpenAlex first, as the cascade yields it
    match = best_match(Reference(query_title="Attention Is All You Need"), records)

    assert match is not None
    assert match.record.year == 2017
    assert match.record.paper_id == "arxiv:1706.03762v7"


def test_best_match_is_order_independent() -> None:
    ref = Reference(query_title="Attention Is All You Need")
    forward = best_match(ref, [_openalex_2025(), _arxiv_2017()])
    reverse = best_match(ref, [_arxiv_2017(), _openalex_2025()])

    assert forward is not None and reverse is not None
    assert forward.record.year == reverse.record.year == 2017


def test_an_explicit_year_hint_still_wins() -> None:
    """The year bonus must outrank the earliest-year tie-break."""
    ref = Reference(query_title="Attention Is All You Need", year_hint=2025)
    match = best_match(ref, [_arxiv_2017(), _openalex_2025()])

    assert match is not None
    assert match.record.year == 2025


# --------------------------------------------------------------------------- #
# grading: an unchecked year must not read as a verified one
# --------------------------------------------------------------------------- #


def test_year_conflicts_reports_disagreeing_backends() -> None:
    conflict = year_conflicts([_openalex_2025(), _arxiv_2017()], "Attention Is All You Need")
    assert conflict == [2017, 2025]


def test_year_conflicts_is_quiet_when_backends_agree() -> None:
    assert year_conflicts([_arxiv_2017(), _arxiv_2017()], "Attention Is All You Need") == []


def test_grade_without_a_year_hint_is_not_year_verified() -> None:
    """The original overclaim: severity 'exact' with the year never checked."""
    graded = grade_reference(
        Reference(query_title="Attention Is All You Need"),
        [_openalex_2025(), _arxiv_2017()],
    )

    assert graded.year_verified is False
    assert any("year not verified" in w for w in graded.warnings)


def test_grade_surfaces_the_backend_year_conflict() -> None:
    graded = grade_reference(
        Reference(query_title="Attention Is All You Need"),
        [_openalex_2025(), _arxiv_2017()],
    )

    assert graded.year_conflict == [2017, 2025]
    assert any("disagree on the year" in w for w in graded.warnings)


def test_grade_with_a_matching_year_hint_is_year_verified() -> None:
    graded = grade_reference(
        Reference(query_title="Attention Is All You Need", year_hint=2017),
        [_arxiv_2017()],
    )

    assert graded.year_verified is True
    assert graded.warnings == []


def test_grade_flags_a_year_mismatch() -> None:
    graded = grade_reference(
        Reference(query_title="Attention Is All You Need", year_hint=2017),
        [_openalex_2025()],
    )

    assert graded.year_verified is False
    assert graded.severity == "minor"
    assert any("year mismatch" in w for w in graded.warnings)


def test_a_fabricated_citation_carries_a_warning() -> None:
    """``major`` is the most serious verdict, so it must not be the silent one."""
    graded = grade_reference(
        Reference(query_title="Quantum Transformers for Underwater Basket Weaving"),
        [_arxiv_2017()],
    )

    assert graded.severity == "major"
    assert graded.year_verified is False
    assert any("may be fabricated" in w for w in graded.warnings)


# --------------------------------------------------------------------------- #
# bibtex: never emit an entry the user cannot actually compile
# --------------------------------------------------------------------------- #


def test_arxiv_record_becomes_misc_with_eprint() -> None:
    """It used to render ``@inproceedings`` with ``booktitle = {arXiv}``."""
    entry = _bibtex(_arxiv_2017(), "vaswani2017attention")

    assert entry.startswith("@misc{")
    assert "eprint = {1706.03762v7}" in entry
    assert "archivePrefix = {arXiv}" in entry
    assert "booktitle" not in entry


def test_record_with_no_venue_is_not_a_bare_inproceedings() -> None:
    """``@inproceedings`` without ``booktitle`` is malformed; say what is missing."""
    entry = _bibtex(_openalex_2025(), "vaswani2025attention")

    assert entry.startswith("@misc{")
    assert "booktitle" not in entry
    assert "note = {venue not reported" in entry


def test_real_venue_still_renders_inproceedings() -> None:
    record = S2Record(
        paper_id="openalex:W1",
        title="Attention Is All You Need",
        authors=_AUTHORS,
        year=2017,
        venue="Advances in Neural Information Processing Systems",
        abstract=_ABSTRACT,
    )
    entry = _bibtex(record, "vaswani2017attention")

    assert entry.startswith("@inproceedings{")
    assert "booktitle = {Advances in Neural Information Processing Systems}" in entry


def test_journal_record_still_renders_article() -> None:
    record = S2Record(
        paper_id="openalex:W2",
        title="Some Journal Paper",
        authors=_AUTHORS,
        year=2019,
        journal="Nature",
        abstract=_ABSTRACT,
    )
    entry = _bibtex(record, "x2019some")

    assert entry.startswith("@article{")
    assert "journal = {Nature}" in entry

"""Hermetic tests for the citation-grounding verification logic.

These tests exercise the pure functions and :class:`FakeScholarClient` with no
network and no ``thefuzz``/``httpx`` installed: :func:`fuzzy_ratio` takes the
stdlib :class:`difflib` fallback, so the threshold/year-bonus boundaries below
are pinned to that path's ratios.
"""

from __future__ import annotations

import importlib.util

import pytest

from clio_parser.retrieval.scholar import (
    Candidate,
    FakeScholarClient,
    Reference,
    S2Record,
    VerifiedCitation,
    best_match,
    dedupe,
    fuzzy_ratio,
    is_date_valid,
    mint_citation_key,
    verified_coverage,
    verify,
)

# Reference title and truncations whose difflib ratios are pinned (see the
# module docstring): cut to 39 chars -> ratio 71, cut to 38 -> 70, cut to 33 -> 65.
_TITLE = "neural machine translation by jointly learning to align and translate"
_Q_RATIO_71 = "neural machine translation by jointly "  # fuzzy_ratio == 71
_Q_RATIO_70 = "neural machine translation by jointly"  # fuzzy_ratio == 70
_Q_RATIO_65 = "neural machine translation by joi"  # fuzzy_ratio == 65

# The threshold-boundary ratios above are pinned to the stdlib difflib fallback.
# If ``thefuzz`` is importable in the dev env, ``fuzzy_ratio`` takes that path and
# the pinned values no longer hold, so skip those boundary tests to avoid
# confusing breakage.
_HAS_THEFUZZ = importlib.util.find_spec("thefuzz") is not None
_difflib_only = pytest.mark.skipif(
    _HAS_THEFUZZ, reason="threshold boundaries are pinned to the difflib fallback ratios"
)


def _record(**kwargs: object) -> S2Record:
    base: dict[str, object] = {
        "paper_id": "p1",
        "title": _TITLE,
        "authors": ["Dzmitry Bahdanau", "Yoshua Bengio"],
        "year": 2015,
        "abstract": "We propose an attention mechanism for translation.",
        "journal": None,
    }
    base.update(kwargs)
    return S2Record.model_validate(base)


def test_fuzzy_ratio_difflib_path_in_bounds() -> None:
    assert fuzzy_ratio("identical", "identical") == 100
    assert 0 <= fuzzy_ratio("abc", "xyz") < 100


@_difflib_only
def test_threshold_boundary_71_passes_70_fails() -> None:
    record = _record()
    passing = best_match(Reference(query_title=_Q_RATIO_71), [record], threshold=70)
    assert passing is not None
    assert passing.score == 71.0

    failing = best_match(Reference(query_title=_Q_RATIO_70), [record], threshold=70)
    assert failing is None


@_difflib_only
def test_year_bonus_pushes_borderline_over_threshold() -> None:
    record = _record(year=2015)
    # Without the year hint, ratio 65 <= threshold 70 -> no match.
    assert best_match(Reference(query_title=_Q_RATIO_65), [record], threshold=70) is None
    # With a matching year hint, 65 + 10 = 75 > 70 -> match.
    matched = best_match(Reference(query_title=_Q_RATIO_65, year_hint=2015), [record], threshold=70)
    assert matched is not None
    assert matched.score == 75.0


@_difflib_only
def test_year_bonus_not_applied_on_mismatch() -> None:
    record = _record(year=1999)
    assert (
        best_match(Reference(query_title=_Q_RATIO_65, year_hint=2015), [record], threshold=70)
        is None
    )


def test_is_date_valid_pre_and_post_cutoff() -> None:
    # No cutoff -> always valid.
    assert is_date_valid("2030-01-01", 2030, None) is True
    # Parseable publication date strictly before the cutoff first-of-month.
    assert is_date_valid("2020-05-10", 2020, "2020-06") is True
    assert is_date_valid("2020-06-10", 2020, "2020-06") is False


def test_is_date_valid_year_only_fallback() -> None:
    # Year-only: earlier year passes; cutoff year passes only if month > 1.
    assert is_date_valid(None, 2019, "2020-06") is True
    assert is_date_valid(None, 2020, "2020-06") is True
    assert is_date_valid(None, 2020, "2020-01") is False
    assert is_date_valid(None, 2021, "2020-06") is False


def test_best_match_cutoff_date_gate() -> None:
    # A record published after the cutoff is rejected by best_match's date gate.
    after = _record(publication_date="2020-08-10", year=2020)
    assert (
        best_match(Reference(query_title=_TITLE), [after], threshold=70, cutoff_date="2020-06")
        is None
    )
    # With no cutoff (None), the same record is accepted (no-op gate).
    accepted = best_match(Reference(query_title=_TITLE), [after], threshold=70, cutoff_date=None)
    assert accepted is not None
    assert accepted.record.paper_id == "p1"
    # A record before the cutoff passes the gate.
    before = _record(publication_date="2020-01-10", year=2020)
    passing = best_match(
        Reference(query_title=_TITLE), [before], threshold=70, cutoff_date="2020-06"
    )
    assert passing is not None
    assert passing.record.paper_id == "p1"


def test_verify_threads_cutoff_into_gate() -> None:
    # verify() must apply the cutoff via best_match even with FakeScholarClient.
    after = _record(publication_date="2020-08-10", year=2020)
    client = FakeScholarClient({_TITLE: [after]})
    refs = [Reference(query_title=_TITLE)]
    assert verify(refs, client, cutoff_date="2020-06", threshold=70) == []
    # Without a cutoff the same reference verifies.
    verified = verify(refs, client, cutoff_date=None, threshold=70)
    assert len(verified) == 1


def test_abstract_empty_record_rejected() -> None:
    record = _record(abstract="   ")
    assert best_match(Reference(query_title=_TITLE), [record], threshold=70) is None
    record_none = _record(abstract=None)
    assert best_match(Reference(query_title=_TITLE), [record_none], threshold=70) is None


def test_mint_citation_key_shape() -> None:
    record = _record()
    key = mint_citation_key(record)
    # first-author lastname + year + two title words (stopwords dropped).
    assert key == "bahdanau2015neuralmachine"


def test_mint_citation_key_fallbacks() -> None:
    record = S2Record(paper_id="x", title="On The Topic", authors=[], year=None)
    assert mint_citation_key(record) == "anonndtopic"


def _verified(paper_id: str, key: str) -> VerifiedCitation:
    record = S2Record(paper_id=paper_id, title="T", authors=["A B"], year=2020, abstract="a")
    return VerifiedCitation(record=record, score=80.0, citation_key=key, bibtex=f"@x{{{key}}}")


def test_dedupe_collapses_same_paper_id() -> None:
    cites = [_verified("p1", "k1"), _verified("p1", "k1"), _verified("p2", "k2")]
    out = dedupe(cites)
    assert [c.record.paper_id for c in out] == ["p1", "p2"]


def test_dedupe_resolves_key_collisions() -> None:
    cites = [_verified("p1", "same"), _verified("p2", "same"), _verified("p3", "same")]
    out = dedupe(cites)
    assert [c.citation_key for c in out] == ["samea", "sameb", "samec"]
    # The suffix is reflected in the rendered bibtex too.
    assert "samea" in out[0].bibtex


def test_verified_coverage_rounding() -> None:
    cands = [Candidate(title=f"t{i}") for i in range(10)]
    # int(10 * 0.9) == 9 required.
    min_required, ratio, meets = verified_coverage(
        cands, [_verified(f"p{i}", f"k{i}") for i in range(9)]
    )
    assert min_required == 9
    assert ratio == 0.9
    assert meets is True
    # 8/10 fails.
    _, _, meets8 = verified_coverage(cands, [_verified(f"p{i}", f"k{i}") for i in range(8)])
    assert meets8 is False


def test_verified_coverage_empty_candidates() -> None:
    min_required, ratio, meets = verified_coverage([], [])
    assert min_required == 0
    assert ratio == 0.0
    assert meets is True


def test_verify_end_to_end_with_fake_client() -> None:
    record = _record()
    client = FakeScholarClient({_Q_RATIO_71: [record]})
    refs = [Reference(query_title=_Q_RATIO_71)]
    verified = verify(refs, client, threshold=70)
    assert len(verified) == 1
    assert verified[0].record.paper_id == "p1"
    assert verified[0].citation_key == "bahdanau2015neuralmachine"
    # A reference the client knows nothing about yields no match.
    empty = verify([Reference(query_title="unknown paper")], client, threshold=70)
    assert empty == []


def test_to_bibtex_article_vs_inproceedings() -> None:
    article = best_match(Reference(query_title=_TITLE), [_record(journal="JMLR")], threshold=70)
    assert article is not None
    assert article.bibtex.startswith("@article{")
    assert "journal = {JMLR}" in article.bibtex

    proc = best_match(Reference(query_title=_TITLE), [_record(venue="ICLR")], threshold=70)
    assert proc is not None
    assert proc.bibtex.startswith("@inproceedings{")
    assert "booktitle = {ICLR}" in proc.bibtex


def test_resolve_scholar_client() -> None:
    from clio_parser.retrieval.scholar import (
        SemanticScholarClient,
        resolve_scholar_client,
    )

    assert isinstance(resolve_scholar_client(None), SemanticScholarClient)
    assert isinstance(resolve_scholar_client("auto"), SemanticScholarClient)
    assert resolve_scholar_client("off") is None
    assert resolve_scholar_client("none") is None

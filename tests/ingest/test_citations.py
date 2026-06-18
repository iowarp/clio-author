"""Hermetic tests for citation linking, range expansion and anchors."""

from __future__ import annotations

from clio_author.ingest.postprocess.citations import (
    _expand_citation_ranges,
    process_citations,
)


def test_single_citation_linked() -> None:
    assert process_citations("See [7] for details.") == "See [[7]](#ref-7) for details."


def test_range_expansion() -> None:
    out = _expand_citation_ranges("prior work [11]-[14] shows")
    assert out == "prior work [11], [12], [13], [14] shows"


def test_range_then_linked_end_to_end() -> None:
    out = process_citations("see [11]-[13]")
    assert out == "see [[11]](#ref-11), [[12]](#ref-12), [[13]](#ref-13)"


def test_range_width_capped() -> None:
    # 0..100 is wider than the cap, so it is left untouched.
    out = _expand_citation_ranges("[1]-[100]")
    assert out == "[1]-[100]"


def test_linking_is_idempotent() -> None:
    once = process_citations("see [7] here")
    twice = process_citations(once)
    assert once == twice == "see [[7]](#ref-7) here"


def test_four_digit_year_not_linked() -> None:
    # 4-digit numbers (years) must NOT become citation links.
    out = process_citations("published in [2024] and bare 2024")
    assert "#ref-2024" not in out
    assert "[2024]" in out


def test_references_section_not_relinked_but_anchored() -> None:
    md = "See [1].\n\n## References\n\n[1] Author, Title, 2020.\n"
    out = process_citations(md)
    # Body citation linked.
    assert "[[1]](#ref-1)" in out.split("## References")[0]
    # Reference entry anchored, not linked.
    refs = out.split("## References")[1]
    assert '<a id="ref-1"></a>[1] Author' in refs
    assert "[[1]]" not in refs


def test_reference_anchors_idempotent() -> None:
    md = "## References\n\n[1] A.\n\n[2] B.\n"
    once = process_citations(md)
    twice = process_citations(once)
    assert once == twice

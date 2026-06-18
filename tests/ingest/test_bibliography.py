"""Hermetic tests for bibliography spacing and reference counting."""

from __future__ import annotations

from clio_author.ingest.postprocess.bibliography import (
    extract_reference_count,
    process_bibliography,
)


def test_blank_line_inserted_between_entries() -> None:
    md = "## References\n[1] First.\n[2] Second.\n[3] Third.\n"
    out = process_bibliography(md)
    body = out.split("## References\n", 1)[1]
    assert "[1] First.\n\n[2] Second.\n\n[3] Third." in body


def test_anchor_aware_entries() -> None:
    md = '## References\n<a id="ref-1"></a>[1] First.\n<a id="ref-2"></a>[2] Second.\n'
    out = process_bibliography(md)
    assert '[1] First.\n\n<a id="ref-2"></a>[2] Second.' in out


def test_no_references_section_is_noop() -> None:
    md = "Body text only, no refs.\n"
    assert process_bibliography(md) == md


def test_extract_reference_count() -> None:
    md = "## References\n[1] A.\n[2] B.\n[3] C.\n"
    assert extract_reference_count(md) == 3


def test_extract_reference_count_no_section() -> None:
    assert extract_reference_count("no refs here [1]") == 0

"""Deterministic unit tests for the pure BibTeX / citation-key helpers."""

from __future__ import annotations

from clio_author.experts.bib_utils import (
    cross_check,
    extract_cite_keys,
    find_duplicates,
    find_malformed,
    parse_bibtex,
)

_BIB = """
@article{smith2020,
  author = {Jane Smith},
  title = {On Attention},
  journal = {J. ML},
  year = {2020}
}

@inproceedings{lee2019,
  author = {Kim Lee},
  title = {Fast Methods},
  booktitle = {NeurIPS},
  year = {2019}
}
"""


def test_parse_bibtex_extracts_type_key_and_fields() -> None:
    entries = parse_bibtex(_BIB)
    assert len(entries) == 2
    first = entries[0]
    assert first["type"] == "article"
    assert first["key"] == "smith2020"
    assert "title" in first["fields"]
    assert "author" in first["fields"]
    assert "journal" in first["fields"]


def test_parse_bibtex_empty_and_garbage() -> None:
    assert parse_bibtex("") == []
    assert parse_bibtex("not bibtex at all") == []


def test_find_duplicates() -> None:
    entries = [
        {"key": "a", "fields": ["title"]},
        {"key": "b", "fields": ["title"]},
        {"key": "a", "fields": ["title"]},
        {"key": "a", "fields": ["title"]},
    ]
    assert find_duplicates(entries) == ["a"]


def test_find_malformed_missing_title_and_key() -> None:
    entries = [
        {"key": "ok", "fields": ["title", "author"]},
        {"key": "notitle", "fields": ["author"]},
        {"key": "", "fields": ["title"]},
    ]
    malformed = find_malformed(entries)
    keys = {m["key"] for m in malformed}
    assert "ok" not in keys
    by_key = {m["key"]: m["missing"] for m in malformed}
    assert by_key["notitle"] == ["title"]
    assert "key" in by_key[""]


def test_parse_then_malformed_on_keyless_entry() -> None:
    # An entry with no key (`@article{,...}`) is parsed with an empty key and
    # flagged by find_malformed.
    entries = parse_bibtex("@article{, title={X}}")
    malformed = find_malformed(entries)
    assert any("key" in m["missing"] for m in malformed)


def test_extract_cite_keys_handles_variants_and_commas() -> None:
    text = (
        r"As shown \cite{a}, and \citep{b, c} and \citet[p. 5]{d}, "
        r"plus an empty \cite{} should be ignored."
    )
    assert extract_cite_keys(text) == {"a", "b", "c", "d"}


def test_extract_cite_keys_empty() -> None:
    assert extract_cite_keys("no citations here") == set()


def test_cross_check_reports_both_directions() -> None:
    result = cross_check({"a", "missing"}, {"a", "unused"})
    assert result["missing_in_bib"] == ["missing"]
    assert result["uncited_in_bib"] == ["unused"]

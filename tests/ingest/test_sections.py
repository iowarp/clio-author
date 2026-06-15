"""Hermetic tests for heading reconstruction (sections pass)."""

from __future__ import annotations

from clio_parser.ingest.blocks import build_section_blocks
from clio_parser.ingest.postprocess import process_markdown
from clio_parser.ingest.postprocess.sections import (
    _determine_header_level,
    process_sections,
)


def test_header_levels_from_numbering_depth() -> None:
    assert _determine_header_level("3") == 2
    assert _determine_header_level("3.1") == 3
    assert _determine_header_level("3.1.1") == 4
    assert _determine_header_level("3.1.1.1") == 5
    # Capped at 6.
    assert _determine_header_level("1.2.3.4.5.6.7") == 6


def test_numbered_section_becomes_header() -> None:
    out = process_sections("3.1 Background\n\nSome body text here.")
    assert out.startswith("### 3.1 Background")


def test_subsubsection_gets_four_hashes() -> None:
    out = process_sections("3.1.1 Design overview\n\nHermes is a middleware.")
    assert "#### 3.1.1 Design overview" in out


def test_roman_numeral_top_level_section() -> None:
    out = process_sections("I. INTRODUCTION\n\nModern systems are complex.")
    assert "## I. INTRODUCTION" in out


def test_abstract_header_artifact() -> None:
    out = process_sections("Abstract -Modern HPC systems are large.")
    assert out.startswith("## Abstract\n\nModern HPC systems are large.")


def test_index_terms_header_artifact() -> None:
    out = process_sections("Index Terms -storage, caching, IO")
    assert out.startswith("## Index Terms\n\nstorage, caching, IO")


def test_long_paragraph_not_promoted() -> None:
    paragraph = "3.1 " + "word " * 40  # well over the 120-char title guard
    out = process_sections(paragraph)
    assert not out.startswith("#")


def test_existing_header_untouched() -> None:
    out = process_sections("## 2. Background\n\nText.")
    assert out.count("## 2. Background") == 1


def test_numbered_bullet_subsection_with_colon() -> None:
    md = "- 1) Architecture overview:\n\nThe system has three layers."
    out = process_sections(md)
    assert "### 1) Architecture overview" in out


def test_top_level_arabic_section_promoted_all_caps() -> None:
    out = process_sections("1. INTRODUCTION\n\nModern systems are complex.")
    assert "## 1. INTRODUCTION" in out


def test_top_level_arabic_section_promoted_title_case() -> None:
    out = process_sections("2. Related Work\n\nPrior studies exist.")
    assert "## 2. Related Work" in out


def test_top_level_section_is_level_two() -> None:
    assert _determine_header_level("1") == 2


def test_multilevel_section_still_promoted() -> None:
    # Regression guard: multi-level numbering keeps the bare numbering + ###.
    out = process_sections("3.1 Background\n\nSome body text here.")
    assert "### 3.1 Background" in out
    assert "## 3.1" not in out.replace("### 3.1", "")


def test_numbered_sentence_not_promoted() -> None:
    md = "1. We use method X to evaluate Y.\n\nMore prose here."
    out = process_sections(md)
    assert out == md
    assert not out.startswith("#")


def test_numbered_list_not_promoted() -> None:
    md = "1. First item\n2. Second item\n3. Third item"
    out = process_sections(md)
    assert out == md
    assert "#" not in out


def test_line_ending_in_colon_not_promoted() -> None:
    md = "1. Setup of the system:\n\nThe rest follows."
    out = process_sections(md)
    assert out == md


def test_numbered_clause_with_midline_period_not_promoted() -> None:
    # The title-portion is a capitalized clause (several lowercase words), so the
    # inline "Title. Body" splitter must leave it as prose, not split a heading.
    md = "1. We then describe the approach. Results follow in the next section.\n\nText."
    out = process_sections(md)
    assert "## 1." not in out
    assert "We then describe the approach" in out


def test_process_markdown_promotes_top_and_sub_level() -> None:
    md = "1. Introduction\n\nIntro body text.\n\n1.1 Background\n\nBackground body text."
    out = process_markdown(md)
    assert "## 1. Introduction" in out
    assert "### 1.1 Background" in out

    sections = build_section_blocks(out)
    paths = [section.section_path for section in sections]
    assert "Introduction" in paths
    assert "Introduction > Background" in paths

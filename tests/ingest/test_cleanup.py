"""Hermetic tests for text cleanup (ligatures, glyphs, blank lines, tables)."""

from __future__ import annotations

from clio_author.ingest.postprocess.cleanup import cleanup_text


def test_ligatures_replaced() -> None:
    out = cleanup_text("the ﬁle and ﬂow of ﬀ ag")
    assert "file" in out
    assert "flow" in out
    assert "ff ag" in out


def test_en_dash_to_hyphen() -> None:
    assert cleanup_text("pages 10–20") == "pages 10-20"


def test_named_glyph_to_greek() -> None:
    out = cleanup_text("the value glyph[epsilon1] is small and glyph[alpha] too")
    assert "ε" in out
    assert "α" in out


def test_numeric_glyph_dropped() -> None:
    out = cleanup_text("noise GLYPH<123> here")
    assert "GLYPH" not in out


def test_excessive_blank_lines_collapsed() -> None:
    out = cleanup_text("a\n\n\n\n\nb")
    assert out == "a\n\nb"


def test_trailing_whitespace_stripped() -> None:
    assert cleanup_text("line with spaces   \nnext") == "line with spaces\nnext"


def test_image_comment_removed() -> None:
    out = cleanup_text("before\n<!-- image -->\nafter")
    assert "<!-- image -->" not in out


def test_table_rows_untouched() -> None:
    # Markdown table rows (leading '|') must survive cleanup verbatim.
    table = "| Name | Value |\n| --- | --- |\n| alpha | 1 |\n"
    out = cleanup_text(table, merge_paragraphs=True, fix_hyphenation=True)
    assert "| Name | Value |" in out
    assert "| --- | --- |" in out
    assert "| alpha | 1 |" in out


def test_paragraph_merge_off_by_default() -> None:
    md = "a sentence fragment continuing\n\nwith more text"
    # Default leaves the blank-line split intact.
    assert cleanup_text(md) == md
    # Opt-in merges it.
    assert (
        cleanup_text(md, merge_paragraphs=True) == "a sentence fragment continuing with more text"
    )


def test_hyphenation_off_by_default() -> None:
    md = "band-\nwidth"
    assert cleanup_text(md) == "band-\nwidth"
    assert cleanup_text(md, fix_hyphenation=True) == "bandwidth"

"""Hermetic tests for the clean-room GFM table-repair pass."""

from __future__ import annotations

from clio_author.ingest import process_markdown
from clio_author.ingest.tables import process_tables


def test_separator_inserted_when_missing() -> None:
    md = "| A | B |\n| 1 | 2 |\n"
    out = process_tables(md)
    lines = out.split("\n")
    assert lines[0] == "| A | B |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| 1 | 2 |"


def test_existing_separator_not_duplicated() -> None:
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    out = process_tables(md)
    assert out.count("| --- | --- |") == 1


def test_alignment_separator_recognized() -> None:
    md = "| A | B |\n| :--- | ---: |\n| 1 | 2 |\n"
    out = process_tables(md)
    # The alignment separator is treated as a separator (regenerated, not padded
    # into a data row) so no extra separator is inserted.
    sep_lines = [
        ln
        for ln in out.split("\n")
        if ln.strip() and set(ln.replace("|", "").replace(" ", "")) <= {"-"}
    ]
    assert len(sep_lines) == 1


def test_ragged_rows_padded_to_max_columns() -> None:
    md = "| A | B | C |\n| --- | --- | --- |\n| 1 | 2 |\n| x |\n"
    out = process_tables(md)
    for line in out.strip().split("\n"):
        assert line.count("|") == 4  # 3 columns -> 4 pipes


def test_extra_cells_kept_and_short_rows_padded() -> None:
    # First row has 2 cols, a later row has 4 -> block max is 4; extra cells kept.
    md = "| A | B |\n| 1 | 2 | 3 | 4 |\n"
    out = process_tables(md)
    data_lines = [ln for ln in out.split("\n") if ln.strip()]
    # header (now padded to 4) + inserted separator + data row
    assert data_lines[0] == "| A | B |  |  |"
    assert data_lines[1] == "| --- | --- | --- | --- |"
    assert data_lines[2] == "| 1 | 2 | 3 | 4 |"


def test_inner_blank_line_removed() -> None:
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n| 3 | 4 |\n"
    out = process_tables(md)
    # The blank line between two data rows is removed (block stays contiguous).
    assert "\n\n" not in out.strip()
    assert "| 1 | 2 |" in out
    assert "| 3 | 4 |" in out


def test_split_continuation_merged_into_previous_cell() -> None:
    md = "| Name | Note |\n| --- | --- |\n| Foo | a long\n| Bar | b |\n"
    out = process_tables(md)
    assert "a long" in out
    # The split continuation has no pipe; it must be merged, not left dangling.
    lines = [ln for ln in out.split("\n") if ln.strip()]
    assert all("|" in ln for ln in lines)


def test_continuation_without_pipe_merged() -> None:
    # A genuinely pipe-less continuation line directly under a data row is the
    # only merge case; it appends to the previous row's last cell.
    md = "| Term | Definition |\n| --- | --- |\n| RAG | retrieval augmented\ngeneration\n| GAN | adversarial |\n"
    out = process_tables(md)
    assert "retrieval augmented generation" in out


def test_idempotent() -> None:
    md = "Intro text.\n\n| A | B | C |\n| 1 | 2 |\ncontinuation\n| x | y | z |\n\nOutro.\n"
    once = process_tables(md)
    twice = process_tables(once)
    assert once == twice


def test_non_table_text_untouched() -> None:
    # A lone prose line that *contains* a pipe must NOT be wrapped into a table:
    # it is not table-like (no separator, no second multi-cell row).
    md = "# Heading\n\nA paragraph with a | pipe in prose is not a row.\n\nDone.\n"
    out = process_tables(md)
    assert out == md


def test_code_fence_untouched() -> None:
    md = "```\n| not | a | table |\n| neither | is | this |\n```\n"
    out = process_tables(md)
    assert out == md


def test_pipe_in_prose_not_corrupted_when_no_table() -> None:
    # Genuine pipes in flowing prose, but no GFM table -> left exactly as-is.
    md = "Recall the relation a | b that holds in text.\n\nAnother | paragraph here.\n"
    out = process_tables(md)
    assert out == md


def test_set_builder_math_with_mid_untouched() -> None:
    # Set-builder / abs-value math using ``\mid`` or ``|`` inside ``$...$`` is
    # prose-with-math, not a table.
    md = r"We define $\{x \mid x>0\}$ and also $\{x | x>0\}$ in the text." + "\n"
    out = process_tables(md)
    assert out == md


def test_inline_code_with_pipe_untouched() -> None:
    # A pipe inside inline-code backticks is not a cell delimiter.
    md = "Run `a | b` to pipe the output into the next stage.\n"
    out = process_tables(md)
    assert out == md


def test_list_items_with_pipe_untouched() -> None:
    # List items that happen to carry a single pipe are not table rows.
    md = "- item a | detail\n- item b | detail\n"
    out = process_tables(md)
    assert out == md


def test_separator_only_block_untouched() -> None:
    # A separator row with no header/data is not a table; no second separator is
    # inserted and the line is left as-is.
    md = "| --- | --- |\n"
    out = process_tables(md)
    assert out == md


def test_block_opening_with_separator_no_double_separator() -> None:
    # A block whose first row is already a separator followed by data rows must
    # not gain a duplicate separator.
    md = "| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n"
    out = process_tables(md)
    assert out.count("| --- | --- |") == 1


def test_fenced_block_with_real_table_after() -> None:
    md = "```python\nx = a | b\n```\n\n| A | B |\n| 1 | 2 |\n"
    out = process_tables(md)
    assert "x = a | b" in out  # code untouched
    assert "| --- | --- |" in out  # real table repaired


def test_prose_and_math_preserved_while_real_table_normalized() -> None:
    # A pipe-bearing prose line and a math line sit next to a genuine table:
    # the prose/math are untouched, only the real table gains its separator.
    md = (
        r"We define $\{x \mid x>0\}$ as the positive reals." + "\n\n"
        "| Metric | Value |\n| 0.9 | 0.8 |\n\n"
        "Run `a | b` afterward.\n"
    )
    out = process_tables(md)
    assert r"We define $\{x \mid x>0\}$ as the positive reals." in out
    assert "Run `a | b` afterward." in out
    assert "| --- | --- |" in out  # only the real table was repaired
    assert out.count("| --- | --- |") == 1


def test_lone_single_pipe_line_not_a_table() -> None:
    # A single ``|``-bearing line with no separator and no second multi-cell row
    # is prose, not a one-row table.
    md = "Column A | Column B in a stray heading line.\n"
    out = process_tables(md)
    assert out == md


def test_process_markdown_keeps_wellformed_table() -> None:
    md = "## Results\n\n| Metric | Value |\n| --- | --- |\n| Accuracy | 0.9 |\n| F1 | 0.8 |\n"
    out = process_markdown(md)
    assert "| Metric | Value |" in out
    assert "| --- | --- |" in out
    assert out.count("| --- | --- |") == 1
    assert "| Accuracy | 0.9 |" in out
    # End-to-end idempotence through the full pipeline.
    assert process_markdown(out) == out

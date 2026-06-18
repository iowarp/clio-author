# Clean-room implementation from behavior described in project notes.
"""Table repair: normalize GFM table blocks extracted from scientific PDFs.

This pass is a pure-Python, regex/string-only repair for GitHub-Flavored
Markdown (GFM) tables -- the fidelity gap none of the reference systems closed
(see ``artifact/notes/M7-PLAN.md``). It is conservative and idempotent:

* contiguous runs of ``|``-bearing lines are treated as one *candidate* table
  block, but a candidate is only normalized when it is genuinely table-like
  (it contains a separator row, or has >=2 consecutive multi-cell rows);
* a missing header separator row (``| --- | --- |``) is inserted after the
  header;
* every row is normalized to the block's max column count (short rows padded
  with empty cells, extra cells kept), with consistent leading/trailing pipes;
* stray blank lines *inside* a block are dropped;
* an obviously-split continuation (a ``|``-less, non-blank line directly under a
  data row) is merged into the previous row's last cell -- this single case
  only.

When deciding whether a line is a table row, ``|`` characters inside inline-code
backticks (`` `...|...` ``) or inline math (``$...|...$`` / ``\\mid``) are
ignored: such a line is prose, not a table row. Fenced code blocks
(```` ``` ````) are never touched, and non-table prose is left exactly as-is.
"""

from __future__ import annotations

import re

# A separator-row cell: optional colons around a run of dashes (GFM alignment).
_SEPARATOR_CELL = re.compile(r"^:?-{1,}:?$")
# A code-fence marker (``` or ~~~), possibly indented, possibly with an info string.
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
# Inline-code spans (one or more backticks) and inline-math spans (``$...$``).
# These are masked before counting pipes so that prose with piped code/math is
# not mistaken for a table row.
_INLINE_CODE = re.compile(r"(`+)(?:.*?)\1")
_INLINE_MATH = re.compile(r"\$[^$\n]*\$")
# A leading list-item or blockquote marker. Lines opening with one of these are
# Markdown list/quote items, never GFM table rows, even when they carry a pipe.
_LIST_MARKER = re.compile(r"^\s*(?:[-*+>]\s|\d+[.)]\s)")


def _mask_inline(line: str) -> str:
    """Blank out inline-code, inline-math and ``\\mid`` spans for ``|`` counting.

    Replaces the *contents* of inline-code (`` `...` ``) and inline-math
    (``$...$``) spans -- as well as the LaTeX ``\\mid`` token -- with spaces so
    that pipes living inside them are not counted as table-cell delimiters. The
    line length is preserved; only ``|``-bearing regions become inert.
    """
    masked = _INLINE_CODE.sub(lambda m: " " * len(m.group(0)), line)
    masked = _INLINE_MATH.sub(lambda m: " " * len(m.group(0)), masked)
    masked = masked.replace(r"\mid", "    ")
    return masked


def _is_pipe_row(line: str) -> bool:
    """True when ``line`` is a non-blank line bearing a real (unmasked) pipe.

    List items and blockquotes (``- a | b``, ``> a | b``) are excluded: a
    leading list/quote marker makes the line a list item, not a table row.
    """
    if not line.strip() or _LIST_MARKER.match(line):
        return False
    return "|" in _mask_inline(line)


def _cell_count(line: str) -> int:
    """Number of ``|``-delimited cells on a masked line (0 if no real pipe)."""
    masked = _mask_inline(line)
    if "|" not in masked:
        return 0
    return len(_split_cells(masked))


def process_tables(content: str) -> str:
    """Normalize every genuine GFM table block in ``content``.

    Args:
        content: Markdown that may contain ragged/headerless GFM tables.

    Returns:
        Markdown with each genuine table block normalized. Pure and idempotent
        -- running twice yields the same result as running once. Fenced code,
        prose, math, inline-code and list pipes are untouched.
    """
    lines = content.split("\n")
    result: list[str] = []
    in_fence = False
    fence_marker = ""
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        fence_match = _FENCE.match(line)

        if in_fence:
            result.append(line)
            # A closing fence uses the same marker character as the opener.
            if fence_match and fence_match.group(1)[0] == fence_marker[0]:
                in_fence = False
                fence_marker = ""
            i += 1
            continue

        if fence_match:
            in_fence = True
            fence_marker = fence_match.group(1)
            result.append(line)
            i += 1
            continue

        if _is_pipe_row(line):
            block, consumed = _collect_block(lines, i)
            if _is_table_like(block):
                result.extend(_normalize_block(block))
            else:
                # Not a genuine table -- leave the candidate lines untouched.
                result.extend(block)
            i += consumed
            continue

        result.append(line)
        i += 1

    return "\n".join(result)


def _collect_block(lines: list[str], start: int) -> tuple[list[str], int]:
    """Collect a contiguous candidate table block starting at ``start``.

    A block extends across consecutive ``|``-bearing lines (pipes inside
    inline-code/math are ignored). A ``|``-less continuation line *between* two
    table rows is absorbed; a blank line, or a line that ends the block (no
    table row follows), is not. Returns the raw block lines and the number of
    source lines consumed.
    """
    block: list[str] = []
    i = start
    n = len(lines)

    while i < n:
        line = lines[i]
        if _FENCE.match(line):
            break

        if _is_pipe_row(line):
            block.append(line)
            i += 1
            continue

        # Non-pipe line: only absorb it (a stray blank line or a split
        # continuation row) if a table row follows, so the block stays
        # contiguous. Otherwise the block ends here.
        if _next_table_row_index(lines, i + 1) is not None:
            block.append(line)
            i += 1
            continue
        break

    return block, i - start


def _next_table_row_index(lines: list[str], start: int) -> int | None:
    """Index of the next ``|``-bearing line, if one immediately follows.

    Only a single intervening non-table line is bridged (a split continuation
    row); two such lines in a row end the block.
    """
    if start >= len(lines):
        return None
    line = lines[start]
    if _FENCE.match(line):
        return None
    if _is_pipe_row(line):
        return start
    return None


def _is_table_like(block: list[str]) -> bool:
    """True when a candidate block is a genuine GFM table.

    A block qualifies only if it either contains a recognizable separator row
    (``| --- | --- |``, alignment colons allowed) *with* at least one non-
    separator pipe row, or has >=2 consecutive pipe rows that each expose >=2
    ``|``-delimited cells. A lone piped line, or single-``|`` lines without a
    separator, are prose -- not tables.
    """
    pipe_rows = [line for line in block if _is_pipe_row(line)]
    if not pipe_rows:
        return False

    separator_rows = [
        line for line in pipe_rows if _is_separator_cells(_split_cells(_mask_inline(line)))
    ]
    # A separator row makes it a table only when real content accompanies it; a
    # block of nothing but separator rows is not a table.
    if separator_rows and len(separator_rows) < len(pipe_rows):
        return True

    # Otherwise require >=2 consecutive multi-cell *content* rows (separator
    # rows don't count toward genuine table-ness on their own).
    run = 0
    for line in block:
        if (
            _is_pipe_row(line)
            and _cell_count(line) >= 2
            and not _is_separator_cells(_split_cells(_mask_inline(line)))
        ):
            run += 1
            if run >= 2:
                return True
        elif not line.strip():
            # A blank line breaks the consecutive run.
            run = 0
        # A bridged continuation line keeps the run alive (it belongs to the
        # preceding row), so we neither reset nor increment on it.
    return False


def _split_cells(row: str) -> list[str]:
    """Split a GFM row into trimmed cell strings (outer pipes stripped)."""
    stripped = row.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_separator_cells(cells: list[str]) -> bool:
    """True when every cell is a GFM separator cell (``---`` / ``:--:``)."""
    return len(cells) > 0 and all(bool(_SEPARATOR_CELL.match(cell)) for cell in cells)


def _render_row(cells: list[str]) -> str:
    """Render cells with consistent leading/trailing pipes."""
    return "| " + " | ".join(cells) + " |"


def _normalize_block(block: list[str]) -> list[str]:
    """Repair one collected table block into well-formed GFM rows."""
    # 1. Merge split continuations and drop inner blank lines, building a list of
    #    cell-lists. A ``|``-less, non-blank line directly under a data row is
    #    appended to the previous row's last cell.
    rows: list[list[str]] = []
    for line in block:
        if not line.strip():
            # Stray blank line inside the block -> drop.
            continue
        if not _is_pipe_row(line):
            # Split continuation (no real pipe): merge into the previous row's
            # last cell.
            if rows:
                extra = line.strip()
                if rows[-1][-1]:
                    rows[-1][-1] = f"{rows[-1][-1]} {extra}"
                else:
                    rows[-1][-1] = extra
            else:
                # No preceding row -- treat as a single-cell row (defensive).
                rows.append([line.strip()])
            continue
        rows.append(_split_cells(line))

    if not rows:
        return list(block)

    # 2. Locate an existing separator row. It may be the first row (a table that
    #    already opens with its header separated) or the conventional second
    #    row; track its position so we don't pad it or insert a duplicate.
    sep_index: int | None = None
    if _is_separator_cells(rows[0]):
        sep_index = 0
    elif len(rows) >= 2 and _is_separator_cells(rows[1]):
        sep_index = 1

    # 3. Compute the block's max column count over *data* rows (ignore the
    #    separator's own cell count, which we regenerate).
    max_cols = max(
        (len(cells) for idx, cells in enumerate(rows) if idx != sep_index),
        default=0,
    )
    max_cols = max(max_cols, 1)

    # 4. Pad data rows to max_cols (keep extra cells). Regenerate the separator.
    out: list[str] = []
    for idx, cells in enumerate(rows):
        if idx == sep_index:
            out.append(_render_row(["---"] * max_cols))
            continue
        if len(cells) < max_cols:
            cells = cells + [""] * (max_cols - len(cells))
        out.append(_render_row(cells))

    # 5. Insert a separator row after the header when none was present. If the
    #    block already opens with a separator (sep_index == 0) we never insert a
    #    duplicate.
    if sep_index is None:
        separator = _render_row(["---"] * max_cols)
        out.insert(1, separator)

    return out


__all__ = ["process_tables"]

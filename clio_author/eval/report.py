"""Pure metric extraction and Markdown report rendering for processed papers.

:func:`compute_md_metrics` counts structural features of a processed Markdown
document; :func:`build_report` renders a Markdown comparison table from a mapping
of ``{system_name: metrics}``. Both are pure and hermetic -- they operate on
strings and dicts only, with no file or network access -- so they run in the
default suite. The heavy PDF -> Markdown step that produces the input lives in
the gated baseline harness.
"""

from __future__ import annotations

import re

from clio_author.ingest.postprocess.bibliography import extract_reference_count
from clio_author.ingest.tables import _is_pipe_row, _is_table_like

# Metric keys, in the order they appear in a rendered report's columns.
METRIC_KEYS: tuple[str, ...] = (
    "sections",
    "linked_citations",
    "figures",
    "tables",
    "references",
)

_HEADING = re.compile(r"(?m)^#{1,6}\s+\S")
_LINKED_CITATION = re.compile(r"\[\[\d+\]\]\(#ref-\d+\)")
_EMBEDDED_FIGURE = re.compile(r"!\[")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def compute_md_metrics(markdown: str) -> dict[str, int]:
    """Count structural features of a processed Markdown document.

    Args:
        markdown: Post-processed scientific Markdown.

    Returns:
        A dict with integer counts for ``sections`` (ATX headings),
        ``linked_citations`` (``[[N]](#ref-N)`` links), ``figures`` (embedded
        ``![`` images), ``tables`` (GFM table blocks) and ``references``
        (reference entries). Keys follow :data:`METRIC_KEYS`.
    """
    return {
        "sections": len(_HEADING.findall(markdown)),
        "linked_citations": len(_LINKED_CITATION.findall(markdown)),
        "figures": len(_EMBEDDED_FIGURE.findall(markdown)),
        "tables": _count_table_blocks(markdown),
        "references": extract_reference_count(markdown),
    }


def _count_table_blocks(markdown: str) -> int:
    """Count *genuine* GFM table blocks, ignoring fenced code regions.

    A candidate block is a maximal run of consecutive ``|``-bearing, non-blank
    lines (pipes inside inline-code/math are ignored). A candidate is counted
    only when it is genuinely table-like -- it has a separator row alongside
    content, or >=2 consecutive multi-cell rows -- mirroring the narrowed
    definition used by :func:`clio_author.ingest.tables.process_tables`. Lines
    inside ```` ``` ```` / ``~~~`` fences are never counted.
    """
    count = 0
    in_fence = False
    fence_char = ""
    block: list[str] = []

    def flush() -> None:
        nonlocal count
        if block and _is_table_like(block):
            count += 1
        block.clear()

    for line in markdown.split("\n"):
        fence_match = _FENCE.match(line)
        if in_fence:
            if fence_match and fence_match.group(1)[0] == fence_char:
                in_fence = False
                fence_char = ""
            flush()
            continue
        if fence_match:
            in_fence = True
            fence_char = fence_match.group(1)[0]
            flush()
            continue

        if _is_pipe_row(line):
            block.append(line)
        else:
            flush()

    flush()
    return count


def build_report(results: dict[str, dict[str, int]], *, title: str = "Fidelity report") -> str:
    """Render a Markdown comparison report from per-system metrics.

    Args:
        results: Mapping of ``{system_name: metrics_dict}`` where each metrics
            dict is shaped like :func:`compute_md_metrics` output.
        title: Heading for the report.

    Returns:
        A Markdown document containing a table whose rows are systems and whose
        columns are metrics. Pure -- no I/O is performed.
    """
    # Preserve metric ordering: known keys first, then any extras seen in input.
    seen: list[str] = list(METRIC_KEYS)
    for metrics in results.values():
        for key in metrics:
            if key not in seen:
                seen.append(key)

    header_cells = ["System", *(_humanize(key) for key in seen)]
    lines: list[str] = [f"# {title}", ""]
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")

    for name, metrics in results.items():
        row = [name, *(str(metrics.get(key, 0)) for key in seen)]
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    return "\n".join(lines)


def _humanize(key: str) -> str:
    """``linked_citations`` -> ``Linked citations`` for report column headers."""
    return key.replace("_", " ").capitalize()


__all__ = ["compute_md_metrics", "build_report", "METRIC_KEYS"]

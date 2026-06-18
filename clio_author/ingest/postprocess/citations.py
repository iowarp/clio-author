# Adapted from the paper-to-md project (MIT, (c) 2025 Jaime Cernuda): https://github.com/JaimeCernuda/paper-to-md
"""Citation processing: link inline numeric citations and anchor references.

Turns ``[7]`` into ``[[7]](#ref-7)``, expands ranges like ``[11]-[14]`` into a
comma-separated list, and adds ``<a id="ref-N">`` anchors so the links resolve.
The document is split at the References header so the bibliography itself is not
re-linked. Linking is idempotent and only matches 1-3 digit numbers, so 4-digit
years are left untouched.
"""

from __future__ import annotations

import re

# Maximum span of an expanded citation range (caps pathological inputs).
MAX_RANGE_WIDTH = 50

_REFERENCE_HEADERS: tuple[str, ...] = (
    r"^## References\s*$",
    r"^## REFERENCES\s*$",
    r"^# References\s*$",
    r"^References\s*$",
)


def process_citations(content: str) -> str:
    """Link inline citations in the body and anchor entries in the references."""
    main_body = content
    references_section = ""

    for pattern in _REFERENCE_HEADERS:
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            main_body = content[: match.start()]
            references_section = content[match.start() :]
            break

    main_body = _expand_citation_ranges(main_body)
    main_body = _link_single_citations(main_body)

    if references_section:
        references_section = _add_reference_anchors(references_section)

    return main_body + references_section


def _expand_citation_ranges(content: str) -> str:
    """``[11]-[14]`` -> ``[11], [12], [13], [14]`` (width-capped)."""

    def expand_range(match: re.Match[str]) -> str:
        start = int(match.group(1))
        end = int(match.group(2))
        if start > end:
            start, end = end, start
        if end - start > MAX_RANGE_WIDTH:
            return match.group(0)
        return ", ".join(f"[{i}]" for i in range(start, end + 1))

    return re.sub(r"\[(\d+)\]\s*[-–—]\s*\[(\d+)\]", expand_range, content)


def _link_single_citations(content: str) -> str:
    """``[7]`` -> ``[[7]](#ref-7)``; idempotent and skips link/image syntax.

    Only 1-3 digit numbers are linked so 4-digit years (e.g. ``[2024]`` or a
    bare ``2024``) are never turned into citation links.
    """

    def link_citation(match: re.Match[str]) -> str:
        prefix = match.string[max(0, match.start() - 2) : match.start()]
        # Skip markdown link/image syntax and already-linked citations.
        if prefix.endswith("](") or prefix.endswith("![") or prefix.endswith("["):
            return match.group(0)
        num = match.group(1)
        return f"[[{num}]](#ref-{num})"

    return re.sub(r"(?<!\])\[(\d{1,3})\](?!\()", link_citation, content)


def _add_reference_anchors(references: str) -> str:
    """``[1] Author...`` -> ``<a id="ref-1"></a>[1] Author...`` (idempotent)."""
    # Strip bullet prefixes: "- [1]" -> "[1]".
    references = re.sub(r"^-\s*\[(\d{1,3})\]", r"[\1]", references, flags=re.MULTILINE)

    def add_anchor_with_indent(match: re.Match[str]) -> str:
        indent = match.group(1)
        num = match.group(2)
        # Already anchored just before this match -> leave alone.
        if f'id="ref-{num}"' in match.string[max(0, match.start() - 50) : match.start()]:
            return match.group(0)
        return f'{indent}<a id="ref-{num}"></a>[{num}]'

    return re.sub(r"^(\s*)\[(\d{1,3})\]", add_anchor_with_indent, references, flags=re.MULTILINE)

# Adapted from the paper-to-md project (MIT, (c) 2025 Jaime Cernuda): https://github.com/JaimeCernuda/paper-to-md
"""Bibliography processing: separate reference entries with blank lines.

Ensures each ``[N]`` reference entry is separated by a blank line (anchor-aware,
so ``<a id="ref-N"></a>[N]`` and ``- [N]`` forms are recognised) and exposes a
small helper to count reference entries.
"""

from __future__ import annotations

import re

_REFERENCE_HEADERS: tuple[str, ...] = (
    r"^## References\s*$",
    r"^## REFERENCES\s*$",
    r"^# References\s*$",
    r"^References\s*$",
)

# A reference entry start: optional anchor, optional bullet, then "[N]".
_REFERENCE_START = re.compile(r"^\s*(?:<a[^>]*></a>)?(?:-\s*)?\[(\d{1,3})\]")


def process_bibliography(content: str) -> str:
    """Add blank-line spacing between reference entries in the references block."""
    for pattern in _REFERENCE_HEADERS:
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            before = content[: match.end()]
            after = _format_reference_entries(content[match.end() :])
            return before + after
    return content


def _format_reference_entries(references_text: str) -> str:
    """Ensure each ``[N]`` entry is separated from the previous one by a blank line."""
    lines = references_text.split("\n")
    result: list[str] = []
    prev_was_reference = False

    for line in lines:
        is_reference_start = bool(_REFERENCE_START.match(line))
        if is_reference_start and prev_was_reference and result and result[-1].strip() != "":
            result.append("")
        result.append(line)
        prev_was_reference = is_reference_start or (
            prev_was_reference and line.strip() != "" and not is_reference_start
        )

    return "\n".join(result)


def extract_reference_count(content: str) -> int:
    """Count distinct ``[N]`` reference entries in the references section.

    Returns 0 when no references section is present.
    """
    references_text = content
    found = False
    for pattern in _REFERENCE_HEADERS:
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            references_text = content[match.end() :]
            found = True
            break
    if not found:
        return 0

    numbers: set[int] = set()
    for line in references_text.split("\n"):
        entry = _REFERENCE_START.match(line)
        if entry:
            numbers.add(int(entry.group(1)))
    return len(numbers)

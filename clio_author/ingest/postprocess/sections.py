# Adapted from the paper-to-md project (MIT): https://github.com/JaimeCernuda/paper-to-md
"""Section processing: reconstruct heading hierarchy from numbering depth.

Academic PDFs lose their heading structure during extraction. This pass rebuilds
it from the section numbering:

- ``1. INTRODUCTION`` / ``I. INTRODUCTION`` -> ``## 1. INTRODUCTION``
- ``2. Related Work``                       -> ``## 2. Related Work``
- ``3.1 Background``                        -> ``### 3.1 Background``
- ``3.1.1 Details``                         -> ``#### 3.1.1 Details``

The header level is ``min(depth + 1, 6)`` where ``depth`` is the number of
dotted components. ``_is_section_title`` guards against promoting paragraph text
(e.g. numbered list items or sentences like ``1. We use method X.``) to a
heading.
"""

from __future__ import annotations

import re

# Longer text than this is almost certainly a paragraph, not a heading.
MAX_TITLE_LENGTH = 120

# Roman numerals 1-20, ordered longest-first so the regex is greedy-correct.
_ROMAN_VALUES: dict[str, int] = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
    "XV": 15,
    "XVI": 16,
    "XVII": 17,
    "XVIII": 18,
    "XIX": 19,
    "XX": 20,
}


def process_sections(content: str) -> str:
    """Reconstruct the heading hierarchy in ``content``.

    Handles abstract/index-term artifacts, hierarchical numbered sections,
    Roman-numeral top-level sections and numbered-bullet subsections.
    """
    content = _fix_abstract_header(content)
    content = _fix_index_terms_header(content)
    content = _fix_hierarchical_sections(content)
    content = _fix_roman_sections(content)
    content = _fix_numbered_bullet_subsections(content)
    return content


def _fix_abstract_header(content: str) -> str:
    """``Abstract -Modern HPC...`` -> ``## Abstract\\n\\nModern HPC...``."""
    pattern = r"^(#+\s*)?Abstract\s*[-–—]\s*"
    return re.sub(pattern, "## Abstract\n\n", content, count=1, flags=re.MULTILINE | re.IGNORECASE)


def _fix_index_terms_header(content: str) -> str:
    """``Index Terms -keywords`` -> ``## Index Terms\\n\\nkeywords``."""
    pattern = r"^(#+\s*)?Index Terms\s*[-–—]\s*"
    return re.sub(
        pattern, "## Index Terms\n\n", content, count=1, flags=re.MULTILINE | re.IGNORECASE
    )


def _determine_header_level(numbering: str) -> int:
    """Map dotted numbering depth to a Markdown header level (capped at 6).

    ``"3"`` -> 2, ``"3.1"`` -> 3, ``"3.1.1"`` -> 4, ... capped at ``######``.
    """
    depth = len(numbering.split("."))
    return min(depth + 1, 6)


def _looks_like_sentence(title: str) -> bool:
    """Heuristic: does ``title`` read as prose rather than a section heading?

    Real top-level headings are short title-case or all-caps phrases
    (``INTRODUCTION``, ``Related Work``). A numbered sentence such as
    ``We use method X to evaluate Y`` has many lowercase words and reads as a
    clause. We treat a candidate as prose when it contains a run of lowercase
    "function" words that a Title-Case heading would not.
    """
    words = [w for w in re.split(r"\s+", title) if w]
    if not words:
        return False

    # All-caps headings (e.g. INTRODUCTION) are never sentences.
    if all(not w[0].islower() for w in words):
        return False

    # Count words that start lowercase (articles, verbs in a clause, ...).
    # Headings are Title Cased, so they have very few of these; a sentence
    # such as "We use method X to evaluate Y" has several.
    lowercase_leading = sum(1 for w in words if w[0].islower())
    return lowercase_leading >= 2


def _is_section_title(title: str, following_lines: list[str]) -> bool:
    """Heuristic: does ``title`` look like a heading rather than body text?"""
    if len(title) > MAX_TITLE_LENGTH:
        return False
    # Trailing sentence/clause punctuation -> a list item or sentence, not a
    # heading (e.g. "1. Setup:" or "1. First,").
    if title.rstrip().endswith((":", ",", ";")):
        return False
    # More than one sentence boundary -> almost certainly a paragraph.
    if title.count(". ") > 1:
        return False
    # Reads like a sentence/clause rather than a heading title.
    if _looks_like_sentence(title):
        return False

    for line in following_lines:
        stripped = line.strip()
        if not stripped:
            continue
        # A following numbered/lettered section means this is still a title.
        if re.match(r"^\d+(\.\d+)*\s+\w", stripped):
            return True
        if re.match(r"^[A-Z]\.\s+\w", stripped):
            return True
        return True
    return True


def _format_numbering(numbering: str) -> str:
    """Render the numbering label for a heading.

    Single-level Arabic numbers keep a trailing dot (``1.``) to match the
    ``## 1. INTRODUCTION`` / ``## I. INTRODUCTION`` style; multi-level numbers
    are written bare (``3.1``).
    """
    return f"{numbering}." if "." not in numbering else numbering


def _is_tight_numbered_list(lines: list[str], index: int) -> bool:
    """Is the numbered line at ``index`` part of a tight numbered list?

    A list has items on adjacent lines (no blank separators), whereas sections
    are separated by body paragraphs. We treat the line as a list item when the
    immediately preceding or following line is itself a single-level numbered
    item with no blank line in between.
    """
    item_re = re.compile(r"^\d+\.?\s+\S")

    neighbours = []
    if index + 1 < len(lines):
        neighbours.append(lines[index + 1])
    if index - 1 >= 0:
        neighbours.append(lines[index - 1])
    return any(line.strip() and item_re.match(line.strip()) for line in neighbours)


def _fix_hierarchical_sections(content: str) -> str:
    """Convert ``N.N[.N...] Title`` lines into the matching Markdown headers."""
    lines = content.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("#"):
            result.append(line)
            i += 1
            continue

        # Pattern 1: numbering + title alone on the line. The numbering may be
        # single-level (``1.``) or multi-level (``3.1``, ``3.1.1``); a single
        # trailing dot on the numbering (``1.``) is consumed before the title.
        section_match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][^.]+?)\.?\s*$", stripped)
        if section_match:
            numbering = section_match.group(1)
            title = section_match.group(2).strip()
            following = lines[i + 1 : i + 5] if i + 1 < len(lines) else []
            # A single-level number adjacent to other numbered lines is a list
            # item, not a section heading.
            is_list = "." not in numbering and _is_tight_numbered_list(lines, i)
            if not is_list and _is_section_title(title, following):
                level = _determine_header_level(numbering)
                result.append(f"{'#' * level} {_format_numbering(numbering)} {title}")
                if i + 1 < len(lines) and lines[i + 1].strip():
                    result.append("")
                i += 1
                continue

        # Pattern 2: numbering + title + body text on the same line. Mirrors
        # Pattern 1's numbering shape (single- or multi-level, optional trailing
        # dot) and applies the same title guard so a clause like
        # "1. We use X. Then Y." is not split into a heading.
        inline_match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][^.]{2,50})\.\s+(.+)$", stripped)
        if inline_match:
            numbering = inline_match.group(1)
            title = inline_match.group(2).strip()
            body = inline_match.group(3).strip()
            if len(title) <= 60 and _is_section_title(title, []):
                level = _determine_header_level(numbering)
                result.append(f"{'#' * level} {_format_numbering(numbering)} {title}")
                result.append("")
                result.append(body)
                i += 1
                continue

        result.append(line)
        i += 1

    return "\n".join(result)


def _fix_roman_sections(content: str) -> str:
    """Promote ``I. INTRODUCTION`` style top-level Roman-numeral sections to ``##``."""
    lines = content.split("\n")
    result: list[str] = []
    roman_alt = "|".join(sorted(_ROMAN_VALUES, key=len, reverse=True))
    pattern = re.compile(rf"^({roman_alt})\.\s+([A-Z][^.]+?)\.?\s*$")

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            result.append(line)
            continue
        match = pattern.match(stripped)
        if match:
            numeral = match.group(1)
            title = match.group(2).strip()
            following = lines[i + 1 : i + 5]
            if _is_section_title(title, following):
                result.append(f"## {numeral}. {title}")
                continue
        result.append(line)

    return "\n".join(result)


def _fix_numbered_bullet_subsections(content: str) -> str:
    """Convert titled numbered bullets to subsection headers; plainify the rest."""
    lines = content.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # "- N) Title:" with a trailing colon and following paragraph -> ### header.
        subsection_match = re.match(r"^-\s*(\d+[).])\s*(.+):\s*$", line)
        if subsection_match:
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1

            has_following_paragraphs = False
            if j < len(lines):
                next_line = lines[j].strip()
                if (
                    next_line
                    and not re.match(r"^[-*•]\s", next_line)
                    and not re.match(r"^\d+[).]\s", next_line)
                ):
                    has_following_paragraphs = True

            if has_following_paragraphs:
                num = subsection_match.group(1)
                title = subsection_match.group(2)
                result.append(f"### {num} {title}")
                result.append("")
                i += 1
                continue

        # "- 1) item" -> "1. item" (plain numbered list).
        bullet_match = re.match(r"^-\s*(\d+)\)\s*(.+)$", line)
        if bullet_match:
            result.append(f"{bullet_match.group(1)}. {bullet_match.group(2)}")
        else:
            result.append(line)
        i += 1

    return "\n".join(result)

"""Deterministic BibTeX / citation-key utilities (pure, no LLM, no network).

These helpers underpin the reference-checking workflow that the JS writing
toolkit wtf-p performs over a paper's bibliography:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concept* of "scan a .bib + the prose and cross-check citation keys"
is re-expressed here; no source code is copied. The functions are intentionally
small, regex-based, and fully unit-testable offline: :func:`parse_bibtex`
extracts ``@type{key, ...}`` entries (key + the field names present),
:func:`find_duplicates` / :func:`find_malformed` flag structural problems,
:func:`extract_cite_keys` pulls ``\\cite{...}`` keys out of prose, and
:func:`cross_check` reconciles the two key sets.
"""

from __future__ import annotations

import re
from typing import Any

# A BibTeX entry header: ``@type{`` then an optional key up to the first comma
# or closing brace. The key group may be empty (e.g. ``@article{,...}``) so a
# malformed keyless entry is still parsed and can be flagged.
_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s}]*)\s*[,}]", re.IGNORECASE)
# A field assignment inside an entry body: ``title = {...}`` / ``year = 2020``.
_FIELD_RE = re.compile(r"(\w+)\s*=", re.IGNORECASE)
# Any LaTeX-ish citation command, capturing the brace group of keys.
_CITE_RE = re.compile(r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{([^}]*)\}")

# Fields a well-formed entry is expected to carry (lower-cased names).
_REQUIRED_FIELDS = ("title",)


def _entry_body(text: str, header_end: int) -> str:
    """Return the brace-balanced body of an entry starting just after its ``{``.

    ``header_end`` is the index of the opening ``{`` of the entry. Returns the
    substring between that brace and its matching close brace (exclusive), or the
    remainder of ``text`` if the braces never balance (malformed input).
    """
    depth = 0
    for index in range(header_end, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[header_end + 1 : index]
    return text[header_end + 1 :]


def parse_bibtex(text: str) -> list[dict[str, Any]]:
    """Parse ``text`` into a list of ``{type, key, fields}`` entry dicts.

    ``type`` is the lower-cased entry type (e.g. ``article``), ``key`` is the
    citation key, and ``fields`` is the sorted list of (lower-cased) field names
    *present* in the entry body. Best-effort and never raises: a header with no
    balanced body still yields an entry with whatever fields were found. The
    bare-key entry ``@article{a}`` (no comma) is not matched as an entry header
    -- such an entry is reported by :func:`find_malformed` via the raw scan.
    """
    entries: list[dict[str, Any]] = []
    for match in _ENTRY_RE.finditer(text):
        entry_type = match.group(1).lower()
        key = match.group(2).strip()
        brace_index = text.find("{", match.start())
        body = _entry_body(text, brace_index) if brace_index != -1 else ""
        # Drop the key fragment (before the first comma) before scanning fields.
        _, _, field_region = body.partition(",")
        fields = sorted({m.group(1).lower() for m in _FIELD_RE.finditer(field_region)})
        entries.append({"type": entry_type, "key": key, "fields": fields})
    return entries


def find_duplicates(entries: list[dict[str, Any]]) -> list[str]:
    """Return the citation keys that appear more than once across ``entries``."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for entry in entries:
        key = str(entry.get("key") or "")
        if not key:
            continue
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    return duplicates


def find_malformed(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return entries missing a key or a required field, with the reason.

    Each result is ``{key, missing}`` where ``missing`` lists the problems:
    ``"key"`` when the citation key is empty, plus any required field name (e.g.
    ``"title"``) absent from the entry's ``fields``.
    """
    malformed: list[dict[str, Any]] = []
    for entry in entries:
        key = str(entry.get("key") or "")
        fields = entry.get("fields") or []
        missing: list[str] = []
        if not key:
            missing.append("key")
        for required in _REQUIRED_FIELDS:
            if required not in fields:
                missing.append(required)
        if missing:
            malformed.append({"key": key, "missing": missing})
    return malformed


def extract_cite_keys(text: str) -> set[str]:
    """Extract the set of citation keys referenced by ``\\cite{...}`` in ``text``.

    Handles ``\\cite`` / ``\\citep`` / ``\\citet`` (and other ``\\cite*`` forms),
    an optional ``[...]`` option group, and comma-separated keys inside the
    braces. Empty keys (e.g. a stray ``\\cite{}``) are dropped.
    """
    keys: set[str] = set()
    for match in _CITE_RE.finditer(text):
        for raw in match.group(1).split(","):
            key = raw.strip()
            if key:
                keys.add(key)
    return keys


def cross_check(cite_keys: set[str], bib_keys: set[str]) -> dict[str, list[str]]:
    """Reconcile cited keys against bibliography keys.

    Returns ``{missing_in_bib, uncited_in_bib}``: keys cited in the prose but
    absent from the ``.bib`` (a broken reference), and keys defined in the
    ``.bib`` but never cited (dead weight). Both lists are sorted for stable
    output.
    """
    return {
        "missing_in_bib": sorted(cite_keys - bib_keys),
        "uncited_in_bib": sorted(bib_keys - cite_keys),
    }


__all__ = [
    "parse_bibtex",
    "find_duplicates",
    "find_malformed",
    "extract_cite_keys",
    "cross_check",
]

# Adapted from the paper-to-md project (MIT, (c) 2025 Jaime Cernuda): https://github.com/JaimeCernuda/paper-to-md
"""General text cleanup: ligatures, glyph artifacts, blank lines, whitespace.

Default (always-on) passes are conservative and structure-preserving:

1. drop ``<!-- image -->`` placeholder comments
2. fix ligatures (fi, fl, ff, ...) and en-dashes
3. map ``glyph[...]`` / ``GLYPH<N>`` artifacts to Unicode (Greek, etc.)
4. collapse runs of >2 blank lines
5. strip trailing whitespace

Opt-in passes (``merge_paragraphs`` / ``fix_hyphenation``, both off by default)
are more aggressive and can change wording, so callers must enable them.

Markdown table rows (lines starting with ``|``) are never merged or rewritten by
the structural passes -- table fidelity is preserved here and deferred to M7.

.. # TODO(M7): tables.py -- first-class table extraction/repair lives in M7;
   this module only guarantees it does not corrupt ``|``-delimited rows.
"""

from __future__ import annotations

import re

# Ligature and dash normalization (codepoint -> ASCII/Unicode replacement).
_LIGATURES: dict[str, str] = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "ft",
    "ﬆ": "st",
    "–": "-",  # en-dash -> hyphen
}

# Docling/OCR "glyph[name]" artifacts mapped to their Unicode characters.
# Covers the lowercase + uppercase Greek alphabet (the common scientific case).
_GLYPH_MAP: dict[str, str] = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "epsilon1": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "omicron": "ο",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "sigma1": "ς",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "phi1": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Theta": "Θ",
    "Lambda": "Λ",
    "Xi": "Ξ",
    "Pi": "Π",
    "Sigma": "Σ",
    "Upsilon": "Υ",
    "Phi": "Φ",
    "Psi": "Ψ",
    "Omega": "Ω",
}


def cleanup_text(
    content: str,
    *,
    merge_paragraphs: bool = False,
    fix_hyphenation: bool = False,
) -> str:
    """Apply general text cleanup.

    Args:
        content: Markdown content.
        merge_paragraphs: Opt-in. Merge paragraphs split across page breaks.
        fix_hyphenation: Opt-in. Re-join words hyphenated at line endings.

    Returns:
        Cleaned Markdown. Default passes never touch table rows.
    """
    content = _remove_image_comments(content)
    content = _fix_ligatures(content)
    content = _fix_glyph_artifacts(content)
    if fix_hyphenation:
        content = _fix_hyphenated_words(content)
    if merge_paragraphs:
        content = _merge_split_paragraphs(content)
    content = _fix_excessive_blank_lines(content)
    content = _fix_trailing_whitespace(content)
    return content


def _remove_image_comments(content: str) -> str:
    """Drop ``<!-- image -->`` placeholder comments left by Docling."""
    return "\n".join(line for line in content.split("\n") if line.strip() != "<!-- image -->")


def _fix_ligatures(content: str) -> str:
    """Replace ligature characters and en-dashes with ASCII equivalents."""
    for ligature, replacement in _LIGATURES.items():
        content = content.replace(ligature, replacement)
    return content


def _fix_glyph_artifacts(content: str) -> str:
    """Map ``glyph[name]`` / ``GLYPH<N>`` artifacts to Unicode where known.

    Named glyphs (``glyph[epsilon1]`` -> ``ε``) are mapped via
    :data:`_GLYPH_MAP`; unknown named glyphs and numeric ``GLYPH<N>`` markers
    (which carry no recoverable character) are dropped.
    """

    def replace_named(match: re.Match[str]) -> str:
        return _GLYPH_MAP.get(match.group(1), "")

    content = re.sub(r"glyph\[([A-Za-z0-9]+)\]", replace_named, content, flags=re.IGNORECASE)
    content = re.sub(r"GLYPH<\d+>", "", content)
    content = re.sub(r"GLYPH&lt;\d+&gt;", "", content)
    return content


def _fix_hyphenated_words(content: str) -> str:
    """Re-join words hyphenated at line endings (opt-in; skips headings/fences/tables)."""
    lines = content.split("\n")
    protected: set[int] = set()
    in_code_fence = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            protected.add(i)
            continue
        if in_code_fence or stripped.startswith("#") or stripped.startswith("|"):
            protected.add(i)

    result: list[str] = list(lines)
    to_remove: set[int] = set()

    for i in range(len(result) - 1):
        if i in protected or i in to_remove:
            continue
        if not re.search(r"(\w+)-$", result[i].rstrip()):
            continue

        next_idx = i + 1
        blank_gap = False
        if next_idx < len(result) and result[next_idx].strip() == "":
            blank_gap = True
            next_idx = i + 2

        if next_idx >= len(result) or next_idx in protected:
            continue

        next_line = result[next_idx].strip()
        if not next_line or not next_line[0].islower():
            continue

        if re.match(r"^([a-z]\w*)-", next_line):
            merged = result[i].rstrip().rstrip("-") + "-" + next_line
        else:
            merged = result[i].rstrip().rstrip("-") + next_line

        result[i] = merged
        to_remove.add(next_idx)
        if blank_gap:
            to_remove.add(i + 1)

    return "\n".join(line for idx, line in enumerate(result) if idx not in to_remove)


def _merge_split_paragraphs(content: str) -> str:
    """Merge paragraphs split by page breaks (opt-in; never touches table rows)."""
    lines = content.split("\n")
    result: list[str] = []
    i = 0

    def is_structural(text: str) -> bool:
        return (
            text.startswith("#")
            or text.startswith("![")
            or text.startswith("-")
            or text.startswith("*")
            or text.startswith("|")
            or bool(re.match(r"^\d+[.)]\s", text))
        )

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if (
            i + 2 < len(lines)
            and stripped
            and not is_structural(stripped)
            and not re.search(r'[.!?:;"\)>]$', line.rstrip())
            and lines[i + 1].strip() == ""
            and lines[i + 2].strip()
            and not is_structural(lines[i + 2].strip())
            and not re.match(r"^(Fig|Figure|Table)\b", lines[i + 2].strip())
        ):
            next_line = lines[i + 2].strip()
            if next_line[0].islower() or next_line.startswith("("):
                result.append(line.rstrip() + " " + next_line)
                i += 3
                continue
        result.append(line)
        i += 1

    return "\n".join(result)


def _fix_excessive_blank_lines(content: str) -> str:
    """Collapse runs of 3+ newlines down to a single blank line."""
    return re.sub(r"\n{3,}", "\n\n", content)


def _fix_trailing_whitespace(content: str) -> str:
    """Strip trailing whitespace from every line."""
    return "\n".join(line.rstrip() for line in content.split("\n"))

# Clean-room implementation from behavior described in project notes.
"""Equation repair: undo common Docling/OCR damage to inline and display math.

This pass is a clean-room re-implementation built from the *behavioural*
description of the equations pass (see ``artifact/notes/phagocyte.md`` section 4
and ``artifact/notes/M1-PLAN.md``). It is a best-effort **heuristic**, not a
general-purpose LaTeX repairer -- it targets specific extraction artifacts.

Generic transforms (always on):
    * placeholder repair -- ``<!-- formula-not-decoded -->`` -> a readable marker
    * generic de-spacing  -- ``d _ { k }`` -> ``d_{k}``, ``1 0 0 0`` -> ``1000``
    * latex spacing       -- ``\\ frac`` -> ``\\frac``
    * delimiter normalize -- blank lines around ``$$ ... $$`` display math
    * bare-newline repair -- stray ``\\`` inside display math become real breaks

Domain-specific fixes (``domain_fixes=True``, **off by default**) cover known
transformer / GAN paper idioms (e.g. ``p _ { data }`` -> ``p_{data}``,
``M u l t i H e a d`` -> ``MultiHead``). These are brittle outside that
distribution and so are opt-in only.
"""

from __future__ import annotations

import re

#: Replacement marker for formulas Docling could not decode.
FORMULA_PLACEHOLDER = "*[Formula - see original PDF]*"

# Generic ASCII operator/word de-spacing applied inside math. Domain-neutral.
_DESPACE_TOKENS: tuple[tuple[str, str], ...] = (
    (r"\\\s+(frac|sqrt|sum|prod|int|partial|nabla|begin|end|left|right|text)", r"\\\1"),
)

# Domain-specific (transformer/GAN) repairs. Opt-in only -- see ``domain_fixes``.
_DOMAIN_FIXES: tuple[tuple[str, str], ...] = (
    # Spaced-out identifiers seen in transformer papers.
    (r"\bM\s*u\s*l\s*t\s*i\s*H\s*e\s*a\s*d\b", "MultiHead"),
    (r"\bd\s*_\s*\{\s*k\s*\}", "d_{k}"),
    (r"\bd\s*_\s*\{\s*m\s*o\s*d\s*e\s*l\s*\}", "d_{model}"),
    # GAN data-distribution subscript.
    (r"\bp\s*_\s*\{\s*d\s*a\s*t\s*a\s*\}", "p_{data}"),
    (r"\bp\s*_\s*\{\s*g\s*\}", "p_{g}"),
)


def process_equations(content: str, *, domain_fixes: bool = False) -> str:
    """Repair extraction artifacts in math.

    Args:
        content: Markdown that may contain damaged inline/display math.
        domain_fixes: When ``True``, also apply the opt-in transformer/GAN
            specific repairs. **Off by default** -- treat them as a heuristic
            for that paper distribution, not a general fix.

    Returns:
        Markdown with normalized math.
    """
    content = _fix_formula_placeholders(content)
    content = _fix_generic_spacing(content)
    content = _clean_latex_spacing(content)
    if domain_fixes:
        content = _apply_domain_fixes(content)
    content = _fix_bare_newlines_in_display_math(content)
    content = _normalize_equation_delimiters(content)
    return content


def _fix_formula_placeholders(content: str) -> str:
    """Replace Docling's not-decoded comments with a readable marker."""
    return re.sub(
        r"<!--\s*formula-not-decoded\s*-->",
        FORMULA_PLACEHOLDER,
        content,
        flags=re.IGNORECASE,
    )


def _fix_generic_spacing(content: str) -> str:
    """Collapse generic de-spacing artifacts inside math regions only.

    Operates on ``$...$`` and ``$$...$$`` spans so prose is never touched:

    * ``d _ { k }`` -> ``d_{k}`` (spaces around subscript/superscript/braces)
    * ``1 0 0 0`` -> ``1000`` (spaced-out digit runs)
    """

    def fix_span(match: re.Match[str]) -> str:
        body = match.group("body")
        # Tighten spacing around sub/superscripts and braces.
        body = re.sub(r"\s*([_^])\s*", r"\1", body)
        body = re.sub(r"\s*([{}])\s*", r"\1", body)
        # Join spaced-out digit runs ("1 0 0 0" -> "1000").
        body = re.sub(r"(?<=\d)(?:\s+(?=\d))", "", body)
        return f"{match.group('open')}{body}{match.group('close')}"

    # Display math first, then inline, so the inline pass never eats ``$$``.
    content = re.sub(
        r"(?P<open>\$\$)(?P<body>.+?)(?P<close>\$\$)", fix_span, content, flags=re.DOTALL
    )
    content = re.sub(r"(?P<open>\$)(?P<body>[^$\n]+?)(?P<close>\$)", fix_span, content)
    return content


def _clean_latex_spacing(content: str) -> str:
    """``\\ frac`` -> ``\\frac``: remove the stray space after a backslash."""
    for pattern, replacement in _DESPACE_TOKENS:
        content = re.sub(pattern, replacement, content)
    return content


def _apply_domain_fixes(content: str) -> str:
    """Apply the opt-in transformer/GAN specific repairs."""
    for pattern, replacement in _DOMAIN_FIXES:
        content = re.sub(pattern, replacement, content)
    return content


def _fix_bare_newlines_in_display_math(content: str) -> str:
    """Wrap multi-line ``$$`` blocks containing real ``\\\\`` breaks in ``aligned``.

    A bare ``\\\\`` followed by a newline is a genuine line break; we wrap the
    block in ``\\begin{aligned} ... \\end{aligned}`` so it renders. A trailing
    ``\\command`` (e.g. ``\\alpha``) is *not* a line break and is left alone.
    """

    def wrap_block(match: re.Match[str]) -> str:
        body = match.group("body").strip("\n")
        if "aligned" in body or "\\begin" in body:
            return match.group(0)
        # Only act when there is a real "\\" line break inside the block.
        if not re.search(r"\\\\\s*\n", body):
            return match.group(0)
        return f"$$\n\\begin{{aligned}}\n{body}\n\\end{{aligned}}\n$$"

    return re.sub(r"\$\$(?P<body>.*?)\$\$", wrap_block, content, flags=re.DOTALL)


def _normalize_equation_delimiters(content: str) -> str:
    """Ensure display-math ``$$`` blocks are surrounded by blank lines."""
    lines = content.split("\n")
    result: list[str] = []

    for line in lines:
        stripped = line.strip()
        is_block_delim = stripped == "$$" or (
            stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 2
        )
        if is_block_delim and result and result[-1].strip() != "":
            result.append("")
        result.append(line)

    return "\n".join(result)

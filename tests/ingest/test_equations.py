"""Hermetic tests for the clean-room equation repair pass."""

from __future__ import annotations

from clio_parser.ingest.postprocess.equations import (
    FORMULA_PLACEHOLDER,
    process_equations,
)


def test_formula_placeholder_replaced() -> None:
    out = process_equations("Before <!-- formula-not-decoded --> after.")
    assert FORMULA_PLACEHOLDER in out
    assert "formula-not-decoded" not in out


def test_subscript_despacing_inside_math() -> None:
    out = process_equations("the value $d _ { k }$ matters")
    assert "$d_{k}$" in out


def test_spaced_digits_joined_inside_math() -> None:
    out = process_equations("base $1 0 0 0 0$ steps")
    assert "$10000$" in out


def test_prose_digits_untouched() -> None:
    # Spaced numbers outside math must not be merged.
    text = "We ran 1 0 trials in prose."
    assert process_equations(text) == text


def test_latex_backslash_spacing_fixed() -> None:
    out = process_equations(r"$$ \ frac{a}{b} $$")
    assert r"\frac" in out


def test_delimiter_normalization_adds_blank_line() -> None:
    out = process_equations("text\n$$\nx = 1\n$$")
    assert "text\n\n$$" in out


def test_domain_fixes_off_by_default() -> None:
    # Letters spaced out *inside* a subscript (transformer idiom). Generic
    # de-spacing tightens the braces but leaves "m o d e l"; only the opt-in
    # domain fix joins it into "model".
    text = "the $d _ { m o d e l }$ dimension"
    out_default = process_equations(text)
    assert "d_{model}" not in out_default
    assert "d_{model}" in process_equations(text, domain_fixes=True)


def test_domain_fix_multihead_opt_in() -> None:
    text = "uses M u l t i H e a d attention"
    assert "MultiHead" not in process_equations(text)
    assert "MultiHead" in process_equations(text, domain_fixes=True)


def test_bare_newline_display_math_wrapped() -> None:
    md = "$$\na = b \\\\\nc = d\n$$"
    out = process_equations(md)
    assert "\\begin{aligned}" in out
    assert "\\end{aligned}" in out

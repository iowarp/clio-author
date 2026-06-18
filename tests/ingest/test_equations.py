"""Hermetic tests for the clean-room equation repair pass."""

from __future__ import annotations

from clio_author.ingest.postprocess.equations import (
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


def test_generic_despacing_on_non_transformer_equation() -> None:
    # A chemistry/physics-style equation with no transformer/GAN vocabulary is
    # still cleaned generically: braces/subscripts tightened, backslash de-spaced.
    text = r"the rate $k _ { r e v } = \ frac { 1 } { 2 }$ holds"
    out = process_equations(text)
    assert "k_{rev}" not in out  # generic pass does not join lone letters
    assert "k_{" in out  # but it does tighten the subscript brace/underscore
    assert r"\frac" in out
    assert r"\frac{1}{2}" in out


def test_generic_path_does_not_apply_domain_rewrites() -> None:
    # domain_fixes=False must never apply transformer/GAN-specific rewrites.
    # These join *multi-letter* spaced runs that generic de-spacing leaves alone.
    text = "uses M u l t i H e a d with $p _ { d a t a }$"
    out = process_equations(text)
    assert "MultiHead" not in out
    assert "p_{data}" not in out


def test_domain_fixes_apply_transformer_and_gan_rewrites() -> None:
    text = "uses M u l t i H e a d with $p _ { d a t a }$"
    out = process_equations(text, domain_fixes=True)
    assert "MultiHead" in out
    assert "p_{data}" in out


def test_generic_path_is_domain_neutral_on_plain_equation() -> None:
    # A clean, well-formed equation with no artifacts is returned unchanged by
    # the default (domain-neutral) path -- no spurious rewrites.
    text = "energy $E = m c^2$ and momentum $p = m v$"
    assert process_equations(text) == text

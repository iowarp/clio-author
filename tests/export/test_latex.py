"""Hermetic, pure (no-I/O) tests for the Markdown -> LaTeX converters.

The conversion is a deterministic string transform, so these tests assert on the
exact LaTeX shape with no model and no filesystem.
"""

from __future__ import annotations

from clio_parser.export.latex import escape_latex, markdown_to_latex, to_latex_document


# --------------------------------------------------------------------------- #
# escape_latex                                                                #
# --------------------------------------------------------------------------- #
def test_escape_all_specials() -> None:
    assert escape_latex("&") == "\\&"
    assert escape_latex("%") == "\\%"
    assert escape_latex("$") == "\\$"
    assert escape_latex("#") == "\\#"
    assert escape_latex("_") == "\\_"
    assert escape_latex("{") == "\\{"
    assert escape_latex("}") == "\\}"
    assert escape_latex("~") == "\\textasciitilde{}"
    assert escape_latex("^") == "\\textasciicircum{}"
    assert escape_latex("\\") == "\\textbackslash{}"


def test_escape_backslash_does_not_double_escape() -> None:
    # A lone backslash must not have the braces of its replacement re-escaped.
    assert escape_latex("a\\b") == "a\\textbackslash{}b"
    # Mixed specials stay one-pass clean.
    assert escape_latex("100% & rising") == "100\\% \\& rising"


# --------------------------------------------------------------------------- #
# markdown_to_latex                                                           #
# --------------------------------------------------------------------------- #
def test_headings_map_to_sectioning() -> None:
    md = "## Intro\n\n### Details\n\n#### Finer"
    out = markdown_to_latex(md)
    assert "\\section{Intro}" in out
    assert "\\subsection{Details}" in out
    assert "\\subsubsection{Finer}" in out


def test_heading_strips_leading_number() -> None:
    out = markdown_to_latex("## 2. Methods")
    assert "\\section{Methods}" in out
    assert "2." not in out
    out2 = markdown_to_latex("### 2.1 Setup")
    assert "\\subsection{Setup}" in out2


def test_inline_bold_italic_code() -> None:
    out = markdown_to_latex("This is **bold** and *italic* and `code`.")
    assert "\\textbf{bold}" in out
    assert "\\textit{italic}" in out
    assert "\\texttt{code}" in out


def test_underscore_italic() -> None:
    out = markdown_to_latex("An _emphasised_ word.")
    assert "\\textit{emphasised}" in out


def test_paragraphs_join_wrapped_lines() -> None:
    out = markdown_to_latex("Line one\nstill one.\n\nSecond paragraph.")
    assert "Line one still one." in out
    assert "\n\n" in out  # blank-line-separated paragraphs


def test_bullet_list_becomes_itemize() -> None:
    out = markdown_to_latex("- first\n- second")
    assert "\\begin{itemize}" in out
    assert "\\item first" in out
    assert "\\item second" in out
    assert "\\end{itemize}" in out


def test_numbered_list_becomes_enumerate() -> None:
    out = markdown_to_latex("1. alpha\n2. beta")
    assert "\\begin{enumerate}" in out
    assert "\\item alpha" in out
    assert "\\end{enumerate}" in out


def test_specials_escaped_in_body() -> None:
    out = markdown_to_latex("Yields 90% with A & B in field_one.")
    assert "90\\%" in out
    assert "A \\& B" in out
    assert "field\\_one" in out


def test_link_renders_as_text() -> None:
    out = markdown_to_latex("See [the paper](http://example.com/x) now.")
    assert "the paper" in out
    assert "http://example.com" not in out


def test_reference_marker_preserved_as_bracket() -> None:
    out = markdown_to_latex("As shown [[3]](#ref-3) earlier.")
    assert "[3]" in out
    assert "#ref" not in out


def test_odd_input_never_crashes() -> None:
    for sample in ("", "\n\n\n", "###", "* ", "100% ^_^ \\ {", "no markdown at all"):
        assert isinstance(markdown_to_latex(sample), str)


# --------------------------------------------------------------------------- #
# to_latex_document                                                           #
# --------------------------------------------------------------------------- #
def test_document_skeleton() -> None:
    doc = to_latex_document("My Title", [("Intro", "Body text.")])
    assert doc.startswith("\\documentclass{article}")
    assert "\\usepackage[utf8]{inputenc}" in doc
    assert "\\title{My Title}" in doc
    assert "\\author{clio-parser}" in doc
    assert "\\begin{document}" in doc
    assert "\\maketitle" in doc
    assert doc.rstrip().endswith("\\end{document}")


def test_document_section_per_entry() -> None:
    doc = to_latex_document("T", [("Intro", "a"), ("Method", "b"), ("Results", "c")])
    assert doc.count("\\section{") == 3
    assert "\\section{Intro}" in doc
    assert "\\section{Method}" in doc
    assert "\\section{Results}" in doc


def test_document_dedupes_leading_heading() -> None:
    # The body repeats its own "## Intro" heading; the document supplies the
    # canonical \section, so the body's heading must be dropped (one \section).
    doc = to_latex_document("T", [("Intro", "## Intro\n\nReal body.")])
    assert doc.count("\\section{Intro}") == 1
    assert "Real body." in doc


def test_document_bibliography_when_bibtex_given() -> None:
    doc = to_latex_document("T", [("Intro", "x")], bibtex="@article{a, title={A}}")
    assert "\\bibliographystyle{plain}" in doc
    assert "\\bibliography{references}" in doc


def test_document_no_bibliography_without_bibtex() -> None:
    doc = to_latex_document("T", [("Intro", "x")])
    assert "\\bibliography" not in doc


def test_document_title_escaped() -> None:
    doc = to_latex_document("Cost & Margin 90%", [("Intro", "x")])
    assert "\\title{Cost \\& Margin 90\\%}" in doc


def test_document_author_override() -> None:
    doc = to_latex_document("T", [("Intro", "x")], author="Ada Lovelace")
    assert "\\author{Ada Lovelace}" in doc

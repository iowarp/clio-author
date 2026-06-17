"""Pure-stdlib Markdown -> LaTeX conversion and the ``export`` orchestration.

The functions here convert the small Markdown subset the writer emits (headings,
paragraphs, bold/italic/code, bullet/numbered lists, links) into LaTeX, and
assemble a standalone ``\\documentclass{article}`` document. Everything is a pure
string transform -- no pandoc, no LaTeX toolchain, no I/O in the converters.

:func:`run_export` is the orchestration entry (the routed ``export`` action). It
mirrors :mod:`clio_parser.experts.compose`: a plain helper that never raises --
any failure becomes an error-flagged :class:`AgentOutput`. With no real model in
play the conversion is fully deterministic, so the suite stays hermetic.

This completes PaperOrchestra parity (it emits a ``.tex`` manuscript); the serial
compose -> export idea is referenced from PaperOrchestra (Apache-2.0). No source
code is copied -- the conversion is re-implemented from scratch.
"""

from __future__ import annotations

import re
from typing import Any

from clio_parser.experts.write_models import PaperOutline
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Task
from clio_parser.tools.files import FileToolError, SafeFiles

# The command-bearing specials (\ ~ ^) expand to LaTeX commands that themselves
# contain braces, so they are routed through sentinels first, the simple specials
# are escaped, and the sentinels are expanded last -- this prevents the brace
# rules from re-escaping the braces those commands introduce.
_SENTINEL_BACKSLASH = "\x00BACKSLASH\x00"
_SENTINEL_TILDE = "\x00TILDE\x00"
_SENTINEL_CARET = "\x00CARET\x00"

_COMMAND_SPECIALS: tuple[tuple[str, str], ...] = (
    ("\\", _SENTINEL_BACKSLASH),
    ("~", _SENTINEL_TILDE),
    ("^", _SENTINEL_CARET),
)
_SIMPLE_SPECIALS: tuple[tuple[str, str], ...] = (
    ("&", "\\&"),
    ("%", "\\%"),
    ("$", "\\$"),
    ("#", "\\#"),
    ("_", "\\_"),
    ("{", "\\{"),
    ("}", "\\}"),
)
_SENTINEL_EXPANSIONS: tuple[tuple[str, str], ...] = (
    (_SENTINEL_BACKSLASH, "\\textbackslash{}"),
    (_SENTINEL_TILDE, "\\textasciitilde{}"),
    (_SENTINEL_CARET, "\\textasciicircum{}"),
)

# Inline Markdown emphasis/code, applied to *already-escaped* text. The markers
# (``*`` ``_`` `` ` ``) are not LaTeX specials, so they survive escaping intact;
# the braces the commands introduce are therefore safe (escaping ran first).
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_STAR_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_ITALIC_USCORE_RE = re.compile(r"\\_(.+?)\\_")
_CODE_RE = re.compile(r"`(.+?)`")
# A reference marker the writer emits: [[3]](#ref-3) -> [3]. Escaping turns the
# fragment into [[3]](\#ref-3) (or \#ref\_3 for the underscore spelling), so the
# leading "#" may be escaped and the separator may be "-" or an escaped "_".
_REF_MARKER_RE = re.compile(r"\[\[(\d+)\]\]\(\\?#ref(?:-|\\?_)\d+\)")
# A Markdown link [text](url) -> text (avoids requiring hyperref).
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\d+\.\s+(.*)$")
_LEADING_NUMBER_RE = re.compile(r"^\d+(\.\d+)*\.?\s*")

_HEADING_COMMANDS = {
    1: "section",
    2: "section",
    3: "subsection",
    4: "subsubsection",
    5: "paragraph",
    6: "subparagraph",
}


def escape_latex(text: str) -> str:
    """Escape LaTeX special characters in a plain-text run.

    Handles ``\\ & % $ # _ { } ~ ^``. Command-bearing specials (``\\ ~ ^``) are
    routed through sentinels first so the brace rules cannot re-escape the braces
    their command replacements introduce; the sentinels are expanded last. Apply
    this only to plain text, not to text that already contains LaTeX commands.
    """
    for char, sentinel in _COMMAND_SPECIALS:
        text = text.replace(char, sentinel)
    for char, replacement in _SIMPLE_SPECIALS:
        text = text.replace(char, replacement)
    for sentinel, replacement in _SENTINEL_EXPANSIONS:
        text = text.replace(sentinel, replacement)
    return text


def _apply_inline(escaped: str) -> str:
    """Apply inline Markdown conversions to an already-escaped string."""
    # Citation/reference markers first, before the generic link rule eats them.
    escaped = _REF_MARKER_RE.sub(r"[\1]", escaped)
    escaped = _LINK_RE.sub(r"\1", escaped)
    escaped = _CODE_RE.sub(r"\\texttt{\1}", escaped)
    escaped = _BOLD_RE.sub(r"\\textbf{\1}", escaped)
    escaped = _ITALIC_STAR_RE.sub(r"\\textit{\1}", escaped)
    escaped = _ITALIC_USCORE_RE.sub(r"\\textit{\1}", escaped)
    return escaped


def _inline(text: str) -> str:
    """Escape ``text`` then apply inline Markdown conversions."""
    return _apply_inline(escape_latex(text))


def _strip_leading_number(text: str) -> str:
    """Drop a leading ``N.``/``N.N`` section number from a heading."""
    return _LEADING_NUMBER_RE.sub("", text).strip()


def markdown_to_latex(md: str) -> str:
    """Convert the common Markdown subset the writer emits into LaTeX.

    Line-based and total: headings become ``\\section``/``\\subsection``/
    ``\\subsubsection`` (a leading ``N.`` number is stripped), blank-line
    separated paragraphs are joined and inline-converted, ``- ``/``* `` runs
    become ``itemize`` and ``N.`` runs become ``enumerate``, and links render as
    their text. Unrecognized lines fall back to escaped paragraph text. Never
    raises on odd input.
    """
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_env: str | None = None

    def flush_paragraph() -> None:
        if paragraph:
            out.append(_inline(" ".join(paragraph).strip()))
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_env
        if list_env is not None:
            out.append(f"\\begin{{{list_env}}}")
            out.extend(f"  \\item {item}" for item in list_items)
            out.append(f"\\end{{{list_env}}}")
            list_items.clear()
            list_env = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading = _HEADING_RE.match(stripped)
        if heading is not None:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            command = _HEADING_COMMANDS.get(level, "section")
            title = _inline(_strip_leading_number(heading.group(2).strip()))
            out.append(f"\\{command}{{{title}}}")
            continue

        bullet = _BULLET_RE.match(stripped)
        if bullet is not None:
            flush_paragraph()
            if list_env not in (None, "itemize"):
                flush_list()
            list_env = "itemize"
            list_items.append(_inline(bullet.group(1).strip()))
            continue

        ordered = _ORDERED_RE.match(stripped)
        if ordered is not None:
            flush_paragraph()
            if list_env not in (None, "enumerate"):
                flush_list()
            list_env = "enumerate"
            list_items.append(_inline(ordered.group(1).strip()))
            continue

        # Plain text line: accumulate into the current paragraph.
        flush_list()
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    return "\n\n".join(part for part in out if part)


def _strip_leading_heading(body: str, title: str) -> str:
    """Drop a leading Markdown heading matching ``title`` (compose's dedup idea).

    The writer often emits its own ``## Title`` (or ``## 1. Title``) heading; the
    document supplies the canonical ``\\section``, so a matching leading heading
    is stripped to avoid a doubled header.
    """
    body = body.lstrip("\n")
    parts = body.split("\n", 1)
    first = parts[0].strip()
    if first.startswith("#"):
        heading_text = _strip_leading_number(first.lstrip("#").strip()).lower()
        if heading_text == title.strip().lower():
            return parts[1].lstrip("\n") if len(parts) > 1 else ""
    return body


def to_latex_document(
    title: str,
    body_sections: list[tuple[str, str]],
    *,
    bibtex: str | None = None,
    documentclass: str = "article",
    author: str | None = None,
) -> str:
    """Assemble a standalone, compilable LaTeX document.

    ``body_sections`` is a list of ``(section_title, section_markdown)`` pairs;
    each becomes a ``\\section{<escaped title>}`` followed by the converted body
    (a leading heading matching the title is stripped to avoid doubling). When
    ``bibtex`` is given the document emits ``\\bibliographystyle{plain}`` +
    ``\\bibliography{references}`` (the companion ``references.bib`` is written
    alongside by the caller).
    """
    author_text = escape_latex(author) if author else "clio-parser"
    lines: list[str] = [
        f"\\documentclass{{{documentclass}}}",
        "\\usepackage[utf8]{inputenc}",
        "\\usepackage{graphicx}",
        f"\\title{{{escape_latex(title)}}}",
        f"\\author{{{author_text}}}",
        "\\date{\\today}",
        "",
        "\\begin{document}",
        "\\maketitle",
    ]
    for section_title, section_md in body_sections:
        body = _strip_leading_heading(section_md, section_title)
        lines.append("")
        lines.append(f"\\section{{{escape_latex(section_title)}}}")
        converted = markdown_to_latex(body)
        if converted:
            lines.append(converted)
    if bibtex:
        lines.append("")
        lines.append("\\bibliographystyle{plain}")
        lines.append("\\bibliography{references}")
    lines.append("")
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Orchestration: the routed ``export`` action                                 #
# --------------------------------------------------------------------------- #
def run_export(
    task: Task,
    *,
    files: SafeFiles | None = None,
    session: SessionContext | None = None,
) -> AgentOutput:
    """Export a composed manuscript to LaTeX (the routed ``export`` action).

    Reads ``task.payload``: ``title`` (optional; defaults from an ``outline``
    title, else ``"Untitled"``); one of ``sections`` (compose's
    ``[{title, draft}]`` shape) or ``markdown`` (a full manuscript split on
    ``##`` headings) or ``outline`` + ``sections``; ``bibtex`` /
    ``suggested_bibtex`` (optional); ``out_dir`` (optional). When a
    :class:`SafeFiles` is reachable, writes ``paper.tex`` (and ``references.bib``
    when a bibliography is present) with no-clobber semantics.

    Returns one :class:`AgentOutput` (``agent="export"``). Only error-flags when
    nothing can be produced (no sections and no usable markdown). Never raises.
    """
    try:
        return _run_export(task, files=files, session=session)
    except Exception as exc:  # noqa: BLE001 - never raise; flag error on the output
        out = AgentOutput(agent="export", content="", metadata={"error": str(exc)})
        if session is not None:
            session.add(out)
        return out


def _run_export(
    task: Task,
    *,
    files: SafeFiles | None,
    session: SessionContext | None,
) -> AgentOutput:
    payload = task.payload
    out_dir = payload.get("out_dir")
    if files is None and out_dir:
        files = SafeFiles(out_dir)

    title, sections = _resolve_sections(payload)
    if not sections:
        return _error(session, "no 'sections', 'markdown', or 'outline' to export")

    bibtex = str(payload.get("bibtex") or payload.get("suggested_bibtex") or "").strip()
    bib = bibtex or None

    latex = to_latex_document(
        title,
        [(s["title"], s["draft"]) for s in sections],
        bibtex=bib,
    )

    wrote: list[str] = []
    if files is not None:
        wrote = _persist(files, latex, bib)

    out = AgentOutput(
        agent="export",
        content=latex,
        structured={"latex": latex, "bibtex": bib},
        metadata={"wrote": wrote, "format": "latex", "num_sections": len(sections)},
    )
    if session is not None:
        session.add(out)
    return out


def _resolve_sections(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Resolve ``(title, sections)`` from the export payload.

    Precedence: explicit ``sections`` (compose's shape), else a full ``markdown``
    manuscript split on ``##`` headings. The title defaults from ``outline`` (or
    the markdown's ``#`` title) and falls back to ``"Untitled"``.
    """
    title = str(payload.get("title") or "").strip()
    if not title:
        title = _title_from_outline(payload.get("outline"))

    raw_sections = payload.get("sections")
    if isinstance(raw_sections, (list, tuple)) and raw_sections:
        sections = [_coerce_section(item) for item in raw_sections]
        sections = [s for s in sections if s["title"] or s["draft"]]
        return (title or "Untitled"), sections

    markdown = payload.get("markdown")
    if isinstance(markdown, str) and markdown.strip():
        md_title, md_sections = _split_markdown(markdown)
        return (title or md_title or "Untitled"), md_sections

    return (title or "Untitled"), []


def _title_from_outline(raw: Any) -> str:
    """Best-effort extract a title from an outline payload (``""`` if absent)."""
    if isinstance(raw, PaperOutline):
        return raw.title
    if isinstance(raw, dict):
        return str(raw.get("title") or "").strip()
    return ""


def _coerce_section(item: Any) -> dict[str, str]:
    """Coerce a loose section item into ``{title, draft}`` strings."""
    if isinstance(item, dict):
        title = str(item.get("title") or item.get("section_path") or "").strip()
        draft = str(item.get("draft") or item.get("body") or item.get("content") or "")
        return {"title": title, "draft": draft}
    return {"title": "", "draft": str(item)}


def _split_markdown(markdown: str) -> tuple[str, list[dict[str, str]]]:
    """Split a full manuscript on ``##`` headings into ``(title, sections)``.

    A leading ``# Title`` becomes the document title; each ``## Heading`` starts a
    new section whose body is the lines until the next ``##``. Content before the
    first ``##`` (after any title) is collected into a leading untitled section.
    """
    title = ""
    sections: list[dict[str, str]] = []
    current_title: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        if current_title is not None or current_body:
            body = "\n".join(current_body).strip("\n")
            sections.append({"title": current_title or "", "draft": body})

    for line in markdown.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            flush()
            current_title = _strip_leading_number(stripped[3:].strip())
            current_body = []
        elif not title and stripped.startswith("# ") and current_title is None:
            title = _strip_leading_number(stripped[2:].strip())
        else:
            current_body.append(line)
    flush()

    sections = [s for s in sections if s["title"] or s["draft"].strip()]
    return title, sections


def _persist(files: SafeFiles, latex: str, bibtex: str | None) -> list[str]:
    """Write ``paper.tex`` (+ ``references.bib``) via ``write_new``. Best-effort."""
    wrote: list[str] = []
    try:
        wrote.append(str(files.write_new("paper.tex", latex)))
    except FileToolError:
        pass
    if bibtex:
        try:
            wrote.append(str(files.write_new("references.bib", bibtex.rstrip("\n") + "\n")))
        except FileToolError:
            pass
    return wrote


def _error(session: SessionContext | None, message: str) -> AgentOutput:
    """Build (and record) an error-flagged export output."""
    out = AgentOutput(agent="export", content="", metadata={"error": message})
    if session is not None:
        session.add(out)
    return out


__all__ = ["escape_latex", "markdown_to_latex", "to_latex_document", "run_export"]

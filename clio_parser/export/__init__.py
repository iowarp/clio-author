"""LaTeX export for composed manuscripts.

Pure-stdlib Markdown -> LaTeX conversion plus a small orchestration entry
(:func:`run_export`) that turns a composed manuscript (compose's ``sections``
shape, or a full Markdown string) into a standalone, compilable ``.tex``
document and an optional ``references.bib``. No external tools (no pandoc / no
LaTeX install) and no new dependencies; conversion is string-based and
deterministic.
"""

from __future__ import annotations

from clio_parser.export.latex import (
    escape_latex,
    markdown_to_latex,
    run_export,
    to_latex_document,
)

__all__ = ["escape_latex", "markdown_to_latex", "run_export", "to_latex_document"]

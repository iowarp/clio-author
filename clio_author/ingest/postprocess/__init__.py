# Adapted from the paper-to-md project (MIT): https://github.com/JaimeCernuda/paper-to-md
"""Deterministic regex-only post-processing for extracted scientific Markdown.

This package layers an academic clean-up pass on top of raw (Docling/OCR)
Markdown. It is pure-Python and has no heavy dependencies, so it can be tested
hermetically. The passes run in a fixed order -- order matters:

    sections -> citations -> equations -> figures -> bibliography -> tables ->
    cleanup

The five passes ``sections``, ``citations``, ``figures``, ``bibliography`` and
``cleanup`` are adapted from the MIT-licensed paper-to-md project. The
``equations`` and ``tables`` passes are clean-room re-implementations (see
``equations.py`` and ``clio_author.ingest.tables``).
"""

from __future__ import annotations

from clio_author.ingest.postprocess.bibliography import (
    extract_reference_count,
    process_bibliography,
)
from clio_author.ingest.postprocess.citations import process_citations
from clio_author.ingest.postprocess.cleanup import cleanup_text
from clio_author.ingest.postprocess.equations import process_equations
from clio_author.ingest.postprocess.figures import (
    get_unembedded_figures,
    process_figures,
)
from clio_author.ingest.postprocess.sections import process_sections
from clio_author.ingest.tables import process_tables


def process_markdown(content: str, images: list[str] | None = None) -> str:
    """Apply every deterministic post-processing pass in the fixed order.

    Args:
        content: Raw Markdown produced by an extractor (e.g. Docling).
        images: Available image filenames (e.g. ``["figure1.png", ...]``) to
            embed at their captions. ``None`` is treated as an empty list.

    Returns:
        Cleaned scientific Markdown.
    """
    content = process_sections(content)
    content = process_citations(content)
    content = process_equations(content)
    content = process_figures(content, images or [])
    content = process_bibliography(content)
    content = process_tables(content)
    content = cleanup_text(content)
    return content


__all__ = [
    "process_markdown",
    "process_sections",
    "process_citations",
    "process_equations",
    "process_tables",
    "process_figures",
    "get_unembedded_figures",
    "process_bibliography",
    "extract_reference_count",
    "cleanup_text",
]

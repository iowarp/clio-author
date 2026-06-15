"""Processing-track ingest package: PDF -> clean scientific Markdown + memory blocks.

The hermetic, dependency-light core lives here:

- :mod:`clio_parser.ingest.postprocess` -- regex-only Markdown post-processing.
- :mod:`clio_parser.ingest.blocks` -- Pydantic v2 memory-block schemas.

Heavy PDF extraction (Docling/PyMuPDF) is a separate, dependency-gated module
added in a later pass and is intentionally NOT imported here.
"""

from __future__ import annotations

from clio_parser.ingest.postprocess import process_markdown

__all__ = ["process_markdown"]

#!/usr/bin/env python
"""Gated baseline report: run ingest on the reference PDFs and render metrics.

This script is **not** part of the default test suite. It needs the ``pdf``
extra (Docling/PyMuPDF) and may need network access (for arXiv-sourced PDFs),
so it is kept out of the hermetic path. Run it manually:

    uv sync --extra pdf
    uv run python scripts/run_baseline_report.py

It processes the two PDFs under ``artifact/papers/``, computes per-paper
fidelity metrics with :func:`clio_parser.eval.compute_md_metrics`, and writes a
Markdown report via :func:`clio_parser.eval.build_report`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clio_parser.eval import build_report, compute_md_metrics

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PAPERS_DIR = _REPO_ROOT / "artifact" / "papers"
_DEFAULT_PDFS = (
    _PAPERS_DIR / "2601.23265-paperbanana.pdf",
    _PAPERS_DIR / "2604.05018-paperorchestra.pdf",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pdfs",
        nargs="*",
        type=Path,
        default=list(_DEFAULT_PDFS),
        help="PDF files to process (defaults to the two reference papers).",
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=_REPO_ROOT / "artifact" / "notes" / "baseline-report.md",
        help="Where to write the Markdown report.",
    )
    args = parser.parse_args(argv)

    try:
        from clio_parser.ingest.docling_extract import PdfConfig, process_pdf
    except ImportError as exc:  # pragma: no cover - gated path
        print(f"pdf extra not installed ({exc}); run: uv sync --extra pdf", file=sys.stderr)
        return 1

    results: dict[str, dict[str, int]] = {}
    for pdf in args.pdfs:
        if not pdf.exists():
            print(f"skipping missing PDF: {pdf}", file=sys.stderr)
            continue
        out_dir = args.out.parent / f"_extract_{pdf.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)
        result = process_pdf(pdf, out_dir=out_dir, config=PdfConfig())
        results[pdf.name] = compute_md_metrics(result.markdown)

    report = build_report(results, title="clio-parser baseline fidelity report")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nwrote report to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())

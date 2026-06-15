"""Gated baseline harness for PDF -> Markdown processing.

Two kinds of check, both deselected by default (``baseline`` / ``live``):

(a) Port-equivalence -- run phagocyte's ``process_markdown`` and ours on
    identical raw-Markdown fixtures and assert equality. This isolates the
    deterministic post-process port from Docling nondeterminism. Skips when the
    phagocyte reference repo is not importable.

(b) Coarse full-pipeline metrics -- run our ``process_pdf`` on the two
    reference PDFs and record section / citation-link / embedded-figure /
    reference counts. These are printed and sanity-checked within loose
    tolerance, not hard-asserted (Docling output drifts across versions).
    Requires the ``pdf`` extra and (for arXiv) network -- skips otherwise.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from clio_parser.ingest import process_markdown

# Raw-Markdown fixtures exercising the shared passes (sections, citations,
# figures, bibliography, cleanup). Equation-specific input is intentionally
# avoided: our equations pass is a clean-room reimplementation and domain fixes
# are opt-in, so it is not expected to byte-match phagocyte's.
SHARED_PASS_FIXTURES: list[tuple[str, str, list[str]]] = [
    (
        "citations_and_sections",
        "## 1. Introduction\n\n"
        "Prior work [1] and others [2, 3] motivate this study [4-6].\n\n"
        "## References\n\n"
        "[1] A. Author. A paper. 2024.\n"
        "[2] B. Author. Another. 2023.\n",
        [],
    ),
    (
        "figures",
        "Figure 1: A diagram of the system.\n\nSome body text.\n",
        ["figure1.png"],
    ),
    (
        "ligatures_cleanup",
        "The ﬁrst eﬃcient workﬂow.\n\n\n\nTrailing space here.   \n",
        [],
    ),
]


@pytest.mark.baseline
@pytest.mark.parametrize(
    "name,raw,images", SHARED_PASS_FIXTURES, ids=lambda v: v if isinstance(v, str) else ""
)
def test_port_equivalence_shared_passes(
    phagocyte_postprocess: Any,
    name: str,
    raw: str,
    images: list[str],
) -> None:
    """Our post-process matches phagocyte's on identical raw Markdown."""
    ours = process_markdown(raw, images)
    theirs = phagocyte_postprocess.process_markdown(raw, images)
    assert ours == theirs, f"port divergence on fixture {name!r}"


def _count_sections(md: str) -> int:
    return len(re.findall(r"(?m)^#{1,6}\s+\S", md))


def _count_citation_links(md: str) -> int:
    return len(re.findall(r"\]\(#ref-\d+\)", md))


def _count_embedded_figures(md: str) -> int:
    return len(re.findall(r"!\[[^\]]*\]\([^)]+\)", md))


def _count_references(md: str) -> int:
    return len(re.findall(r"(?m)^\s*\[\d+\]", md))


@pytest.mark.baseline
@pytest.mark.live
@pytest.mark.parametrize("pdf_fixture", ["paperbanana_pdf", "paperorchestra_pdf"])
def test_full_pipeline_metrics(
    request: pytest.FixtureRequest,
    pdf_deps: None,
    pdf_fixture: str,
    tmp_path: Path,
) -> None:
    """Run the real pipeline on a reference PDF and record coarse metrics.

    Counts are printed and loosely sanity-checked, not hard-asserted: Docling
    output drifts across versions, so this is an M7-eval signal, not a gate.
    """
    pdf_path: Path = request.getfixturevalue(pdf_fixture)

    from clio_parser.ingest.docling_extract import PdfConfig, process_pdf

    result = process_pdf(pdf_path, out_dir=tmp_path, config=PdfConfig())
    md = result.markdown

    metrics = {
        "extractor": result.extractor,
        "sections": _count_sections(md),
        "citation_links": _count_citation_links(md),
        "embedded_figures": _count_embedded_figures(md),
        "references": _count_references(md),
        "saved_images": len(result.images),
        "markdown_chars": len(md),
    }
    print(f"\n[baseline metrics] {pdf_path.name}: {metrics}")

    # Coarse sanity within tolerance -- a real paper has some structure and body.
    assert metrics["markdown_chars"] > 1000
    assert metrics["sections"] >= 1

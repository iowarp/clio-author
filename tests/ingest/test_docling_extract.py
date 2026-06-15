"""Hermetic tests for the pure logic in :mod:`clio_parser.ingest.docling_extract`.

These cover :func:`resolve_arxiv_url` and :class:`PdfConfig` defaults only --
no Docling, PyMuPDF, network, or filesystem extraction. Importing the module
must succeed without the ``pdf`` extra installed.
"""

from __future__ import annotations

import pytest

from clio_parser.ingest.docling_extract import (
    ExtractionDependencyError,
    ExtractionError,
    PdfConfig,
    resolve_arxiv_url,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("2601.23265", "https://arxiv.org/pdf/2601.23265.pdf"),
        ("2601.23265v2", "https://arxiv.org/pdf/2601.23265v2.pdf"),
        ("  2604.05018  ", "https://arxiv.org/pdf/2604.05018.pdf"),
        ("https://arxiv.org/abs/2601.23265", "https://arxiv.org/pdf/2601.23265.pdf"),
        ("https://arxiv.org/abs/2601.23265v3", "https://arxiv.org/pdf/2601.23265v3.pdf"),
        ("http://arxiv.org/pdf/2601.23265", "https://arxiv.org/pdf/2601.23265.pdf"),
        ("https://arxiv.org/pdf/2601.23265.pdf", "https://arxiv.org/pdf/2601.23265.pdf"),
    ],
)
def test_resolve_arxiv_url_canonicalises(source: str, expected: str) -> None:
    assert resolve_arxiv_url(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "https://example.com/paper.pdf",
        "https://example.org/some/path",
        "/local/path/to/paper.pdf",
        "paper.pdf",
        "relative/dir/file.pdf",
        # Lookalike host: must NOT be treated as arxiv even though it contains
        # "arxiv.org" as a substring and an arxiv-shaped id in the path.
        "https://arxiv.org.evil.com/pdf/2601.23265",
    ],
)
def test_resolve_arxiv_url_passthrough(source: str) -> None:
    assert resolve_arxiv_url(source) == source


def test_resolve_arxiv_url_subdomain_is_arxiv() -> None:
    assert (
        resolve_arxiv_url("https://export.arxiv.org/abs/2601.23265")
        == "https://arxiv.org/pdf/2601.23265.pdf"
    )


def test_pdf_config_defaults() -> None:
    config = PdfConfig()
    assert config.images_scale == 2.0
    assert config.min_image_width == 200
    assert config.min_image_height == 150
    assert config.min_image_area == 40000
    assert config.use_postprocess is True
    assert config.use_ocr_fallback is True
    assert config.extract_equations is True


def test_pdf_config_is_frozen() -> None:
    config = PdfConfig()
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
        config.images_scale = 3.0  # type: ignore[misc]


def test_error_hierarchy() -> None:
    assert issubclass(ExtractionDependencyError, ExtractionError)
    assert issubclass(ExtractionError, RuntimeError)

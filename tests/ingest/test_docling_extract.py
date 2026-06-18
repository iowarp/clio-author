"""Hermetic tests for the pure logic in :mod:`clio_author.ingest.docling_extract`.

These cover :func:`resolve_arxiv_url` and :class:`PdfConfig` defaults only --
no Docling, PyMuPDF, network, or filesystem extraction. Importing the module
must succeed without the ``pdf`` extra installed.
"""

from __future__ import annotations

import pytest

from clio_author.ingest.docling_extract import (
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


# --- resolve_source: title / topic support (hermetic; search is mocked) --------
from clio_author.ingest import docling_extract as _dx  # noqa: E402


def test_resolve_source_arxiv_id() -> None:
    assert _dx.resolve_source("2601.23265") == "https://arxiv.org/pdf/2601.23265.pdf"


def test_resolve_source_local_pdf_path(tmp_path) -> None:
    p = tmp_path / "paper.pdf"
    p.write_bytes(b"%PDF-1.4")
    assert _dx.resolve_source(str(p)) == str(p)


def test_resolve_source_pdf_name_treated_as_path() -> None:
    assert _dx.resolve_source("some-paper.pdf") == "some-paper.pdf"


def test_resolve_source_title_uses_arxiv_search(monkeypatch) -> None:
    monkeypatch.setattr(
        _dx, "search_arxiv_pdf", lambda q, **k: "https://arxiv.org/pdf/1706.03762.pdf"
    )
    assert _dx.resolve_source("Attention Is All You Need") == "https://arxiv.org/pdf/1706.03762.pdf"


def test_resolve_source_unresolvable_title_raises(monkeypatch) -> None:
    monkeypatch.setattr(_dx, "search_arxiv_pdf", lambda q, **k: None)
    with pytest.raises(ExtractionError, match="could not resolve"):
        _dx.resolve_source("zzz definitely not a real paper title qqq")


@pytest.mark.live
def test_search_arxiv_pdf_live() -> None:
    url = _dx.search_arxiv_pdf("Attention Is All You Need")
    assert url is not None and url.startswith("https://arxiv.org/pdf/")

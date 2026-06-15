# Clean-room re-implementation from behavior described in the phagocyte ingestor
# (license unspecified): src/ingestor/.../extractors/pdf/pdf_extractor.py.
# Docling / PyMuPDF / httpx usage is generic public-API code, not copied source.
"""Dependency-gated PDF -> Markdown extraction (Docling primary, PyMuPDF fallback).

The heavy extraction stack (``docling``, ``pymupdf``, ``pillow``, ``httpx``) is
the optional ``pdf`` extra. Every heavy import is performed lazily *inside* a
function, so importing this module is always cheap and hermetic -- the default
test suite never touches Docling or the network.

Pipeline (synchronous, to match the M0 harness):

    resolve_arxiv_url -> download_pdf (if a URL) -> extract -> process_markdown

``extract`` prefers Docling (with formula enrichment and size-filtered figure
export); on a missing-Docling import or any extraction failure it falls back to
a PyMuPDF page-text pass when :attr:`PdfConfig.use_ocr_fallback` is set. The
chosen path is recorded on :attr:`ExtractionResult.extractor` so consumers can
detect the degraded OCR mode.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # pragma: no cover - typing only, no heavy import at runtime
    pass


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class ExtractionError(RuntimeError):
    """Base class for PDF extraction failures."""


class ExtractionDependencyError(ExtractionError):
    """A required optional dependency (Docling / PyMuPDF / httpx) is missing.

    The ``pdf`` extra installs the extraction stack::

        uv sync --extra pdf

    (Docling additionally downloads ~500MB of ML models on first use.)
    """


class DownloadError(ExtractionError):
    """Downloading a PDF from a URL failed."""


# --------------------------------------------------------------------------- #
# Config + result
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PdfConfig:
    """Configuration for PDF extraction.

    Attributes:
        images_scale: Resolution multiplier for extracted figure images.
        min_image_width: Minimum kept figure width in pixels.
        min_image_height: Minimum kept figure height in pixels.
        min_image_area: Minimum kept figure area in pixels.
        use_postprocess: Run the deterministic Markdown post-process pass.
        use_ocr_fallback: Fall back to PyMuPDF when Docling is missing/fails.
        extract_equations: Enable Docling formula enrichment.
    """

    images_scale: float = 2.0
    min_image_width: int = 200
    min_image_height: int = 150
    min_image_area: int = 40000
    use_postprocess: bool = True
    use_ocr_fallback: bool = True
    extract_equations: bool = True


class ExtractionResult(BaseModel):
    """The outcome of extracting one PDF.

    ``extractor`` records which path produced the Markdown so callers can detect
    the degraded PyMuPDF/OCR mode.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    markdown: str
    images: list[Path] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    extractor: Literal["docling", "pymupdf"]
    source_url: str | None = None


# --------------------------------------------------------------------------- #
# URL handling
# --------------------------------------------------------------------------- #
_ARXIV_ID_RE = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?")
_BARE_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")


def _is_url(source: str) -> bool:
    """True when ``source`` looks like an http(s) URL."""
    return source.lower().startswith(("http://", "https://"))


def resolve_arxiv_url(source: str) -> str:
    """Resolve an arXiv reference to a canonical PDF URL.

    Handles a bare id (``2601.23265``), an ``arxiv.org/abs/<id>`` landing URL,
    or an ``arxiv.org/pdf/<id>`` URL, mapping all of them to
    ``https://arxiv.org/pdf/<id>.pdf``. Non-arxiv http(s) URLs and local paths
    pass through unchanged.

    Args:
        source: A bare arXiv id, an arXiv URL, another http(s) URL, or a path.

    Returns:
        The canonical arXiv PDF URL, or ``source`` unchanged.
    """
    stripped = source.strip()

    # Bare arXiv id, e.g. "2601.23265" or "2601.23265v2".
    if _BARE_ARXIV_RE.match(stripped):
        return f"https://arxiv.org/pdf/{stripped}.pdf"

    if _is_url(stripped):
        host = urlparse(stripped).netloc.lower()
        if host == "arxiv.org" or host.endswith(".arxiv.org"):
            match = _ARXIV_ID_RE.search(stripped)
            if match:
                return f"https://arxiv.org/pdf/{match.group(0)}.pdf"
        # Non-arxiv (or unrecognised arxiv) URL: pass through unchanged.
        return stripped

    # Local path or anything else: unchanged.
    return source


def search_arxiv_pdf(query: str, *, max_results: int = 1, timeout: int = 15) -> str | None:
    """Resolve a paper title or topic to an arXiv PDF URL via the arXiv API.

    Queries the public arXiv Atom API and returns the canonical PDF URL of the
    top match, or ``None`` if there is no match or the request fails. Network
    call; uses only the standard library (lazily imported).

    Args:
        query: A paper title or free-text topic, e.g. ``"Attention Is All You Need"``.
        max_results: How many results to request (the first is used).
        timeout: Request timeout in seconds.

    Returns:
        ``https://arxiv.org/pdf/<id>.pdf`` for the top hit, or ``None``.
    """
    import urllib.parse
    import urllib.request
    import xml.etree.ElementTree as ET

    ns = {"a": "http://www.w3.org/2005/Atom"}

    def _first(search_query: str) -> str | None:
        params = urllib.parse.urlencode(
            {"search_query": search_query, "start": 0, "max_results": max_results}
        )
        url = f"http://export.arxiv.org/api/query?{params}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
                root = ET.fromstring(resp.read())
        except Exception:  # noqa: BLE001 - any failure -> unresolved
            return None
        entry = root.find("a:entry", ns)
        id_el = entry.find("a:id", ns) if entry is not None else None
        if id_el is None or not id_el.text:
            return None
        match = _ARXIV_ID_RE.search(id_el.text)
        return f"https://arxiv.org/pdf/{match.group(0)}.pdf" if match else None

    # Prefer an exact title-phrase match; fall back to a general topic search.
    return _first(f'ti:"{query}"') or _first(f"all:{query}")


def resolve_source(source: str) -> str:
    """Resolve any ingest source to a fetchable URL or local path.

    Accepts an arXiv id, an arXiv/http(s) URL, a local PDF path, **or a paper
    title / topic** (resolved to an arXiv PDF via :func:`search_arxiv_pdf`).

    Args:
        source: arXiv id, URL, local path, or a paper title/topic string.

    Returns:
        A canonical arXiv PDF URL, the original URL/path, or the title's resolved
        arXiv PDF URL.

    Raises:
        ExtractionError: A title/topic that matched nothing on arXiv.
    """
    stripped = source.strip()
    # arXiv id or any URL -> the pure mapping handles these.
    if _BARE_ARXIV_RE.match(stripped) or _is_url(stripped):
        return resolve_arxiv_url(stripped)
    # Path-like (existing file, a ``.pdf`` name, or contains a separator) -> path.
    if (
        Path(stripped).exists()
        or stripped.lower().endswith(".pdf")
        or "/" in stripped
        or os.sep in stripped
    ):
        return stripped
    # Otherwise treat the text as a paper title / topic and search arXiv.
    found = search_arxiv_pdf(stripped)
    if found is not None:
        return found
    raise ExtractionError(
        f"could not resolve source {source!r}: not an arXiv id/URL or local PDF, "
        "and no arXiv result for that title/topic"
    )


def download_pdf(url: str, dest_dir: Path) -> Path:
    """Download a PDF from ``url`` into ``dest_dir``.

    Lazily imports ``httpx`` (part of the ``pdf`` extra), follows redirects, and
    writes the body to a ``.pdf`` file named after the URL path.

    Args:
        url: The PDF URL to fetch.
        dest_dir: Directory to write the downloaded file into (created if absent).

    Returns:
        Path to the downloaded PDF.

    Raises:
        ExtractionDependencyError: ``httpx`` is not installed.
        DownloadError: The request failed or returned a non-success status.
    """
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ExtractionDependencyError(
            "httpx is required to download PDFs. Install with: uv sync --extra pdf"
        ) from exc

    dest_dir.mkdir(parents=True, exist_ok=True)
    path_part = urlparse(url).path.split("?")[0].split("#")[0]
    filename = Path(path_part).name or "downloaded.pdf"
    if not filename.endswith(".pdf"):
        filename = f"{filename}.pdf"
    dest = dest_dir / filename

    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            dest.write_bytes(response.content)
    except Exception as exc:  # noqa: BLE001 - normalize any httpx/network error
        raise DownloadError(f"Failed to download PDF from {url}: {exc}") from exc

    return dest


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def _extract_with_docling(path: Path, out_dir: Path, config: PdfConfig) -> ExtractionResult:
    """Run Docling extraction, saving size-filtered figures to ``out_dir/img``.

    Raises:
        ExtractionDependencyError: Docling is not installed.
        ExtractionError: Docling reported a failed conversion.
    """
    try:
        from docling.datamodel.base_models import ConversionStatus, InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise ExtractionDependencyError(
            "Docling is not installed. Install with: uv sync --extra pdf "
            "(Docling downloads ~500MB of ML models on first use)."
        ) from exc

    # Normalize any unexpected Docling-internal failure (convert, get_image,
    # save, export_to_markdown, ...) to ExtractionError so callers only ever see
    # the extraction error hierarchy. ExtractionError raised inside (e.g. a
    # failed-conversion status) propagates unchanged.
    try:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.images_scale = config.images_scale
        pipeline_options.generate_picture_images = True
        pipeline_options.do_formula_enrichment = config.extract_equations

        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        result = converter.convert(str(path))

        ok = (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS)
        if result.status not in ok:
            errors = getattr(result, "errors", [])
            detail = "; ".join(str(e) for e in errors) if errors else "unknown error"
            raise ExtractionError(f"Docling conversion failed ({result.status}): {detail}")

        document = result.document
        img_dir = out_dir / "img"
        images: list[Path] = []
        figure_num = 1

        for picture in getattr(document, "pictures", []) or []:
            try:
                pil_image = picture.get_image(document)
            except Exception:  # noqa: BLE001 - skip images that fail to render
                continue
            if pil_image is None:
                continue
            width, height = pil_image.size
            if (
                width < config.min_image_width
                or height < config.min_image_height
                or width * height < config.min_image_area
            ):
                continue
            img_dir.mkdir(parents=True, exist_ok=True)
            dest = img_dir / f"figure{figure_num}.png"
            pil_image.save(dest, format="PNG")
            images.append(dest)
            figure_num += 1

        markdown = document.export_to_markdown()
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize any Docling-internal failure
        raise ExtractionError(f"Docling extraction failed: {exc}") from exc

    metadata: dict[str, Any] = {
        "extractor": "docling",
        "image_count": len(images),
        "page_count": getattr(document, "page_count", None),
    }
    return ExtractionResult(
        markdown=markdown,
        images=images,
        metadata=metadata,
        extractor="docling",
    )


def _extract_with_pymupdf(path: Path, out_dir: Path, config: PdfConfig) -> ExtractionResult:
    """Fallback page-text extraction via PyMuPDF (``fitz``).

    Produces lower-fidelity Markdown (no structure recognition) and stamps
    ``extractor="pymupdf"`` so consumers can flag the degraded mode.

    Raises:
        ExtractionDependencyError: PyMuPDF is not installed.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ExtractionDependencyError(
            "PyMuPDF is not installed. Install with: uv sync --extra pdf"
        ) from exc

    # Normalize any unexpected PyMuPDF-internal failure to ExtractionError so
    # callers only ever see the extraction error hierarchy.
    try:
        doc = fitz.open(str(path))
        try:
            title = path.stem
            meta = doc.metadata or {}
            if meta.get("title"):
                title = meta["title"]

            parts: list[str] = [f"# {title}\n"]
            for page in doc:
                text = page.get_text("text")
                if text.strip():
                    parts.append(text)
                    parts.append("")
            page_count = doc.page_count
        finally:
            doc.close()
    except Exception as exc:  # noqa: BLE001 - normalize any PyMuPDF-internal failure
        raise ExtractionError(f"PyMuPDF extraction failed: {exc}") from exc

    markdown = "\n".join(parts)
    metadata: dict[str, Any] = {
        "extractor": "pymupdf",
        "image_count": 0,
        "page_count": page_count,
        "note": "Fallback extraction - reduced structure quality.",
    }
    return ExtractionResult(
        markdown=markdown,
        images=[],
        metadata=metadata,
        extractor="pymupdf",
    )


def extract(source: str | Path, out_dir: Path, config: PdfConfig) -> ExtractionResult:
    """Extract a local PDF to an :class:`ExtractionResult` (synchronous).

    Tries Docling first; on a missing-Docling import or any extraction failure,
    falls back to PyMuPDF when :attr:`PdfConfig.use_ocr_fallback` is set.

    Args:
        source: Path to a local PDF file.
        out_dir: Directory for extraction artifacts (figures land in ``out_dir/img``).
        config: Extraction configuration.

    Returns:
        The extraction result, with ``extractor`` stamped to the path taken.

    Raises:
        ExtractionError: The PDF is missing, or all available extractors failed.
        ExtractionDependencyError: No extractor dependency is installed.
    """
    path = Path(source)
    if not path.exists():
        raise ExtractionError(f"File not found: {path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        return _extract_with_docling(path, out_dir, config)
    except ExtractionDependencyError:
        if not config.use_ocr_fallback:
            raise
        return _extract_with_pymupdf(path, out_dir, config)
    except ExtractionError:
        if not config.use_ocr_fallback:
            raise
        try:
            return _extract_with_pymupdf(path, out_dir, config)
        except ExtractionDependencyError as exc:
            raise ExtractionError(
                "Docling extraction failed and PyMuPDF fallback is unavailable. "
                "Install with: uv sync --extra pdf"
            ) from exc


def process_pdf(
    source: str | Path,
    out_dir: Path | None = None,
    config: PdfConfig | None = None,
) -> ExtractionResult:
    """Resolve, (download,) extract and post-process a PDF end-to-end.

    Orchestration: :func:`resolve_arxiv_url` -> :func:`download_pdf` (when the
    resolved source is a URL) -> :func:`extract` -> ``process_markdown`` (when
    :attr:`PdfConfig.use_postprocess` is set).

    Args:
        source: An arXiv id, an arXiv/http(s) URL, a local PDF path, or a paper
            title/topic (resolved to an arXiv PDF via :func:`search_arxiv_pdf`).
        out_dir: Working directory for downloads and figures; a temporary
            directory is used when ``None``.
        config: Extraction configuration.

    Returns:
        The extraction result, with post-processed Markdown when enabled.
    """
    config = config or PdfConfig()
    work_dir = Path(out_dir) if out_dir is not None else Path(tempfile.mkdtemp(prefix="clio-pdf-"))
    work_dir.mkdir(parents=True, exist_ok=True)

    resolved = resolve_source(str(source))
    source_url: str | None = None
    if _is_url(resolved):
        source_url = resolved
        local_path: Path = download_pdf(resolved, work_dir)
    else:
        local_path = Path(resolved)

    result = extract(local_path, work_dir, config)
    result.source_url = source_url
    if source_url is not None:
        result.metadata.setdefault("source_url", source_url)

    if config.use_postprocess:
        from clio_parser.ingest import process_markdown

        image_names = [p.name for p in result.images]
        result.markdown = process_markdown(result.markdown, image_names)

    return result


__all__ = [
    "PdfConfig",
    "ExtractionResult",
    "ExtractionError",
    "ExtractionDependencyError",
    "DownloadError",
    "resolve_arxiv_url",
    "search_arxiv_pdf",
    "resolve_source",
    "download_pdf",
    "extract",
    "process_pdf",
]

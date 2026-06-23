"""Multi-source context gathering: files / folders / globs / git repos / PDFs.

:func:`gather_context` takes a heterogeneous list of *sources* and ingests every
one into a single merged :class:`~clio_author.ingest.blocks.MemoryBlocks`, so the
writing path (``plan`` / ``write`` / ``compose`` / ``ask`` / ``research`` /
``kg``) can be grounded in a whole working set -- a repository, a folder of
notes, several PDFs -- rather than one pre-ingested file.

Each source is classified and routed:

* **arXiv id / PDF URL / ``*.pdf`` path** -> the Docling extraction pipeline
  (:func:`~clio_author.ingest.docling_extract.process_pdf`), reusing the
  ingestor's section + figure block building.
* **git repo** (``*.git``, ``git@...``, or a GitHub/GitLab/Bitbucket URL) ->
  shallow-cloned, then its docs (``.md`` / ``.rst`` / ``.txt`` / ``.tex``) are
  ingested.
* **directory** -> its docs are ingested (recursively, hidden/vendor dirs skipped).
* **glob** (contains ``*``/``?``/``[``) -> each match is ingested.
* **``.md`` / ``.markdown`` file** -> split into section blocks by header.
* **other text file** -> one section block holding the file's text.

Heavy/optional work is lazy: Docling/PyMuPDF imports live inside the PDF helper
and ``git`` is invoked via :mod:`subprocess` only for git sources, so importing
this module is hermetic. The function never raises for a single bad source -- it
records the failure in :attr:`GatherResult.skipped` and continues -- mirroring the
expert "never raise" contract. A merged section's ``section_path`` is prefixed
with a per-source label (e.g. ``[paper.pdf] Methods > Setup``) so blocks from
different sources stay distinguishable, and figures are re-indexed to keep
``figure_id`` unique across the merged set.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from clio_author.ingest.blocks import FigureInfo, MemoryBlocks, SectionBlock, build_section_blocks

if TYPE_CHECKING:  # pragma: no cover - typing only, no heavy import at runtime
    from clio_author.ingest.docling_extract import PdfConfig

# Documentation/prose file types ingested when walking a directory or git repo.
_DOC_EXT = {".md", ".markdown", ".rst", ".txt", ".tex"}
# Markdown extensions get header-split into multiple section blocks.
_MD_EXT = {".md", ".markdown"}
# Plain-text file types accepted as an *explicit* single-file source (a directory
# walk is restricted to _DOC_EXT to avoid dumping an entire code tree as context).
_TEXT_EXT = _DOC_EXT | {
    ".py",
    ".js",
    ".ts",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".csv",
    ".sh",
    ".sql",
}
# Directories never descended into during a walk.
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "site-packages",
    ".tox",
    ".idea",
    ".vscode",
}
_GIT_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}

# arXiv id / URL detection mirrors clio_author.ingest.docling_extract (kept local
# so this module imports nothing heavy).
_BARE_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")

# Default bounds: how many files a single gather pulls in, and the per-text-file
# character cap (keeps an over-large file from dominating the injected context).
DEFAULT_MAX_FILES = 50
DEFAULT_MAX_TEXT_CHARS = 200_000


@dataclass
class _Contribution:
    """One ingested unit (a file or a PDF) contributing blocks to the merge."""

    label: str
    sections: list[SectionBlock] = field(default_factory=list)
    figures: list[FigureInfo] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatherResult:
    """The outcome of gathering several sources into one block set.

    Attributes:
        blocks: The merged :class:`MemoryBlocks` (a drop-in ``blocks`` payload).
        ingested: One dict per successfully ingested source/unit, recording its
            ``source`` / ``label`` / ``kind`` and the block counts produced.
        skipped: One dict per skipped source, with a ``reason``.
    """

    blocks: MemoryBlocks
    ingested: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Source classification
# --------------------------------------------------------------------------- #
def _is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def _is_git_url(source: str) -> bool:
    """True when ``source`` looks like a clonable git repository."""
    s = source.strip()
    if s.endswith(".git") or s.startswith("git@"):
        return True
    if _is_url(s):
        parsed = urlparse(s)
        host = parsed.netloc.lower()
        is_host = host in _GIT_HOSTS or any(host.endswith("." + h) for h in _GIT_HOSTS)
        if is_host:
            parts = [p for p in parsed.path.split("/") if p]
            # owner/repo (or deeper) and not a file blob -> treat as a repo.
            return len(parts) >= 2 and not parsed.path.lower().endswith(".pdf")
    return False


def _is_pdf_source(source: str) -> bool:
    """True when ``source`` is an arXiv id, an arXiv URL, or a PDF URL/path."""
    s = source.strip()
    if _BARE_ARXIV_RE.match(s):
        return True
    if s.lower().endswith(".pdf"):
        return True
    if _is_url(s):
        parsed = urlparse(s)
        host = parsed.netloc.lower()
        if host == "arxiv.org" or host.endswith(".arxiv.org"):
            return True
        if parsed.path.lower().endswith(".pdf"):
            return True
    return False


def _classify(source: str) -> str:
    """Classify a source string into a routing ``kind``."""
    s = source.strip()
    if _is_git_url(s):
        return "git"
    if _is_pdf_source(s):
        return "pdf"
    if any(ch in s for ch in "*?[") and not Path(s).exists():
        return "glob"
    path = Path(s)
    if path.is_dir():
        return "dir"
    if path.is_file():
        return "md" if path.suffix.lower() in _MD_EXT else "text"
    if _is_url(s):
        return "url"  # unsupported (non-PDF, non-git) URL
    return "unknown"


# --------------------------------------------------------------------------- #
# Per-source ingest helpers (each returns a list of _Contribution)
# --------------------------------------------------------------------------- #
def _short_label(source: str) -> str:
    """A compact, human label for a source (file name, arXiv id, or repo name)."""
    s = source.strip()
    if _BARE_ARXIV_RE.match(s):
        return f"arXiv:{s}"
    if _is_url(s):
        name = Path(urlparse(s).path).name
        return name or urlparse(s).netloc
    return Path(s).name or s


def _read_text(path: Path, *, max_chars: int) -> tuple[str, bool]:
    """Read ``path`` as UTF-8, truncated to ``max_chars``; ``(text, truncated)``."""
    text = path.read_text(encoding="utf-8")  # may raise UnicodeDecodeError -> skipped
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n\n[... truncated ...]", True
    return text, False


def _ingest_pdf(
    source: str, *, out_dir: Path | None, config: PdfConfig | None
) -> list[_Contribution]:
    """Ingest a PDF/arXiv source into section + figure blocks (reuses the pipeline)."""
    from clio_author.ingest.docling_extract import PdfConfig as _PdfConfig
    from clio_author.ingest.docling_extract import process_pdf

    result = process_pdf(source, out_dir=out_dir, config=config or _PdfConfig())
    sections = build_section_blocks(result.markdown)
    figures = [
        FigureInfo(figure_id=i, image_path=path.name)
        for i, path in enumerate(result.images, start=1)
    ]
    title = str(result.metadata.get("title") or "").strip()
    label = title or _short_label(source)
    return [
        _Contribution(
            label=label,
            sections=sections,
            figures=figures,
            meta={"extractor": result.extractor, "source_url": result.source_url},
        )
    ]


def _ingest_markdown_file(path: Path, label: str, *, max_chars: int) -> list[_Contribution]:
    """Ingest one Markdown file, header-split into section blocks."""
    text, truncated = _read_text(path, max_chars=max_chars)
    sections = build_section_blocks(text)
    if not sections:
        sections = [SectionBlock(section_path="", title=path.stem, text=text.strip())]
    return [_Contribution(label=label, sections=sections, meta={"truncated": truncated})]


def _ingest_text_file(path: Path, label: str, *, max_chars: int) -> list[_Contribution]:
    """Ingest one plain-text/code file as a single section block."""
    text, truncated = _read_text(path, max_chars=max_chars)
    section = SectionBlock(section_path="", title=path.stem, text=text.strip())
    return [_Contribution(label=label, sections=[section], meta={"truncated": truncated})]


def _ingest_one_file(path: Path, label: str, *, max_chars: int) -> list[_Contribution]:
    """Dispatch a single file path to the markdown or text ingester."""
    if path.suffix.lower() in _MD_EXT:
        return _ingest_markdown_file(path, label, max_chars=max_chars)
    return _ingest_text_file(path, label, max_chars=max_chars)


def _walk_docs(root: Path, *, max_files: int) -> list[Path]:
    """Collect doc files under ``root`` (README first), skipping vendor dirs.

    Bounded to ``max_files`` and sorted deterministically: any ``README*`` first,
    then the rest by relative path.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped/hidden directories in place so os.walk does not descend.
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
        for name in filenames:
            # Doc extensions, plus a bare/extensionless README (e.g. `README`,
            # `README.rst`) which many repos use as their primary doc.
            if Path(name).suffix.lower() in _DOC_EXT or name.lower().startswith("readme"):
                found.append(Path(dirpath) / name)

    def _key(p: Path) -> tuple[int, str]:
        rel = p.relative_to(root).as_posix()
        return (0 if p.name.lower().startswith("readme") else 1, rel)

    found.sort(key=_key)
    return found[:max_files]


def _ingest_dir(
    root: Path, *, max_files: int, max_chars: int, label_root: str | None = None
) -> list[_Contribution]:
    """Ingest the doc files under a directory; label each by its relative path."""
    contribs: list[_Contribution] = []
    for path in _walk_docs(root, max_files=max_files):
        rel = path.relative_to(root).as_posix()
        label = f"{label_root}/{rel}" if label_root else rel
        try:
            contribs.extend(_ingest_one_file(path, label, max_chars=max_chars))
        except (OSError, UnicodeDecodeError):
            continue  # unreadable/binary doc -> skip silently within a dir walk
    return contribs


def _ingest_glob(pattern: str, *, max_files: int, max_chars: int) -> list[_Contribution]:
    """Ingest each file matching a glob ``pattern`` (relative to CWD)."""
    base = Path()
    matches = sorted(p for p in base.glob(pattern) if p.is_file())
    contribs: list[_Contribution] = []
    for path in matches[:max_files]:
        try:
            contribs.extend(_ingest_one_file(path, path.as_posix(), max_chars=max_chars))
        except (OSError, UnicodeDecodeError):
            continue
    return contribs


def _repo_name(url: str) -> str:
    """Derive a short repo name from a git URL."""
    s = url.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[: -len(".git")]
    return Path(s).name or s


def _ingest_git(
    url: str, *, max_files: int, max_chars: int, timeout: int = 120
) -> list[_Contribution]:
    """Shallow-clone a git repo to a temp dir and ingest its docs."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is not available on PATH; cannot clone repository")
    tmp = Path(tempfile.mkdtemp(prefix="clio-gather-git-"))
    repo_dir = tmp / "repo"
    try:
        subprocess.run(  # noqa: S603 - git path from shutil.which, fixed argv
            [git, "clone", "--depth", "1", "--quiet", url, str(repo_dir)],
            check=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip() or "clone failed"
        raise RuntimeError(f"git clone failed: {detail}") from exc
    return _ingest_dir(
        repo_dir, max_files=max_files, max_chars=max_chars, label_root=_repo_name(url)
    )


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def _normalize_sources(sources: str | list[str] | tuple[str, ...]) -> list[str]:
    """Coerce the ``sources`` input to a clean list of non-empty strings."""
    if isinstance(sources, str):
        items = [sources]
    else:
        items = [str(s) for s in sources]
    return [s.strip() for s in items if str(s).strip()]


def gather_context(
    sources: str | list[str] | tuple[str, ...],
    *,
    out_dir: Path | str | None = None,
    config: PdfConfig | None = None,
    max_files: int = DEFAULT_MAX_FILES,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
) -> GatherResult:
    """Ingest many sources into one merged :class:`MemoryBlocks`.

    Args:
        sources: A source string or a list of them. Each may be an arXiv id, a
            PDF/arXiv URL, a local ``.pdf``, a git repo URL, a directory, a glob,
            a Markdown file, or another text/code file.
        out_dir: Working directory passed to the PDF pipeline (figures land in
            ``out_dir/img``); a temp dir is used per PDF when ``None``.
        config: Optional :class:`PdfConfig` for the PDF pipeline.
        max_files: Upper bound on files pulled from directories/globs/repos in
            total across this call.
        max_text_chars: Per-text-file character cap (longer files are truncated).

    Returns:
        A :class:`GatherResult` with the merged blocks plus ``ingested`` /
        ``skipped`` provenance. Never raises for a single bad source: the failure
        is recorded in ``skipped`` and gathering continues.
    """
    items = _normalize_sources(sources)
    out_path = Path(out_dir) if out_dir is not None else None
    max_files = max(1, int(max_files))
    max_text_chars = max(1, int(max_text_chars))

    blocks = MemoryBlocks(metadata={"sources": []})
    ingested: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    fig_counter = 0
    remaining = max_files

    for src in items:
        if remaining <= 0:
            skipped.append({"source": src, "reason": f"file budget ({max_files}) exhausted"})
            continue
        kind = _classify(src)
        try:
            if kind == "git":
                contribs = _ingest_git(src, max_files=remaining, max_chars=max_text_chars)
            elif kind == "dir":
                contribs = _ingest_dir(Path(src), max_files=remaining, max_chars=max_text_chars)
            elif kind == "glob":
                contribs = _ingest_glob(src, max_files=remaining, max_chars=max_text_chars)
            elif kind == "pdf":
                contribs = _ingest_pdf(src, out_dir=out_path, config=config)
            elif kind in ("md", "text"):
                contribs = _ingest_one_file(Path(src), _short_label(src), max_chars=max_text_chars)
            elif kind == "url":
                skipped.append(
                    {"source": src, "reason": "unsupported URL (only PDF/arXiv URLs and git repos)"}
                )
                continue
            else:
                skipped.append({"source": src, "reason": "not a known file, folder, glob, or URL"})
                continue
        except Exception as exc:  # noqa: BLE001 - one bad source must not abort the gather
            skipped.append({"source": src, "reason": str(exc)})
            continue

        if not contribs:
            skipped.append({"source": src, "reason": "no ingestible content found"})
            continue

        for contrib in contribs:
            for section in contrib.sections:
                prefix = f"[{contrib.label}]"
                new_path = f"{prefix} {section.section_path}" if section.section_path else prefix
                blocks.sections.append(section.model_copy(update={"section_path": new_path}))
            for figure in contrib.figures:
                fig_counter += 1
                blocks.figures.append(figure.model_copy(update={"figure_id": fig_counter}))
            ingested.append(
                {
                    "source": src,
                    "label": contrib.label,
                    "kind": kind,
                    "sections": len(contrib.sections),
                    "figures": len(contrib.figures),
                    **contrib.meta,
                }
            )
            remaining -= 1

    blocks.metadata["sources"] = [
        {k: v for k, v in entry.items() if k in ("source", "label", "kind")} for entry in ingested
    ]
    return GatherResult(blocks=blocks, ingested=ingested, skipped=skipped)


def render_context_markdown(blocks: MemoryBlocks) -> str:
    """Render merged blocks as a single Markdown document (for ``context.md``)."""
    parts: list[str] = []
    for section in blocks.sections:
        parts.append(section.to_context("full"))
    return "\n\n".join(parts).strip() + "\n" if parts else ""


__all__ = [
    "GatherResult",
    "gather_context",
    "render_context_markdown",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_TEXT_CHARS",
]

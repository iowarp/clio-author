"""Fixtures for the gated baseline harness.

Resolves the two reference PDFs and the optional ``pdf`` extra / phagocyte
reference repo. Every fixture skips (does not fail) when its dependency is
missing, so ``pytest -m 'baseline or live'`` is green-or-skipped in a hermetic
environment.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Repo root: tests/baselines/conftest.py -> repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAPERS_DIR = _REPO_ROOT / "artifact" / "papers"
_PHAGOCYTE_POSTPROCESS = (
    _REPO_ROOT
    / "artifact"
    / "repos"
    / "phagocyte"
    / "src"
    / "ingestor"
    / "src"
    / "ingestor"
    / "extractors"
    / "pdf"
    / "postprocess"
)


@pytest.fixture
def paperbanana_pdf() -> Path:
    """Path to the PaperBanana reference PDF, or skip if absent."""
    path = _PAPERS_DIR / "2601.23265-paperbanana.pdf"
    if not path.exists():
        pytest.skip(f"reference PDF missing: {path}")
    return path


@pytest.fixture
def paperorchestra_pdf() -> Path:
    """Path to the PaperOrchestra reference PDF, or skip if absent."""
    path = _PAPERS_DIR / "2604.05018-paperorchestra.pdf"
    if not path.exists():
        pytest.skip(f"reference PDF missing: {path}")
    return path


@pytest.fixture
def pdf_deps() -> None:
    """Skip unless the ``pdf`` extra (Docling + PyMuPDF) is importable."""
    if importlib.util.find_spec("docling") is None and importlib.util.find_spec("fitz") is None:
        pytest.skip("pdf extra not installed (need docling or pymupdf); uv sync --extra pdf")


@pytest.fixture
def phagocyte_postprocess():  # type: ignore[no-untyped-def]
    """Import phagocyte's ``process_markdown`` from the cloned repo, or skip.

    The phagocyte postprocess package lives under a nested namespace
    (``ingestor.extractors.pdf.postprocess``); we load it directly from its
    ``__init__.py`` path so it is importable standalone. Skips gracefully when
    the repo is absent or the import fails.
    """
    init = _PHAGOCYTE_POSTPROCESS / "__init__.py"
    if not init.exists():
        pytest.skip(f"phagocyte reference repo not found at {_PHAGOCYTE_POSTPROCESS}")

    mod_name = "_phagocyte_postprocess_ref"
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    # The package's __init__ uses relative imports, so load it as a package
    # whose submodules live in the same directory.
    spec = importlib.util.spec_from_file_location(
        mod_name,
        init,
        submodule_search_locations=[str(_PHAGOCYTE_POSTPROCESS)],
    )
    if spec is None or spec.loader is None:
        pytest.skip("could not build import spec for phagocyte postprocess")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - any import failure -> skip, not fail
        del sys.modules[mod_name]
        pytest.skip(f"phagocyte postprocess not importable: {exc}")
    return module

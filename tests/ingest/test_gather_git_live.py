"""Gated test: gather_context actually shallow-clones and ingests a git repo.

Marked ``live`` (deselected by default; needs network + ``git`` on PATH). It
clones a tiny public repo and asserts its README turned into section blocks,
exercising the ``_ingest_git`` path the hermetic suite stubs out.
"""

from __future__ import annotations

import shutil

import pytest

from clio_author.ingest.gather import gather_context

pytestmark = pytest.mark.live

# A tiny, stable public repo with a README (the canonical git "hello world").
_REPO = "https://github.com/octocat/Hello-World"


def test_gather_clones_and_ingests_repo() -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available on PATH")
    result = gather_context([_REPO])
    # The clone should produce at least one ingested doc, labelled under the repo.
    assert result.ingested, f"nothing ingested (skipped={result.skipped})"
    assert all(entry["kind"] == "git" for entry in result.ingested)
    assert any(entry["label"].startswith("Hello-World/") for entry in result.ingested)
    assert result.blocks.sections

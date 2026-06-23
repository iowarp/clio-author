"""Hermetic tests for multi-source context gathering.

:func:`~clio_author.ingest.gather.gather_context` is exercised entirely on the
local filesystem -- Markdown/text files, directory walks, globs -- so the suite
touches no network, no git, and no PDF/Docling path. The source-classification
helpers (git/PDF/URL detection) are unit-tested directly, and the never-raise
contract is checked with a deliberately bad source.
"""

from __future__ import annotations

from pathlib import Path

from clio_author.ingest.gather import (
    GatherResult,
    _classify,
    _is_git_url,
    _is_pdf_source,
    gather_context,
    render_context_markdown,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def test_classify_git_urls() -> None:
    assert _is_git_url("https://github.com/owner/repo")
    assert _is_git_url("https://gitlab.com/owner/repo.git")
    assert _is_git_url("git@github.com:owner/repo.git")
    # owner-only / file blob / non-host URLs are not repos.
    assert not _is_git_url("https://github.com/owner")
    assert not _is_git_url("https://example.com/owner/repo")


def test_classify_pdf_sources() -> None:
    assert _is_pdf_source("2601.23265")
    assert _is_pdf_source("https://arxiv.org/abs/2601.23265")
    assert _is_pdf_source("https://example.com/paper.pdf")
    assert _is_pdf_source("/tmp/local.pdf")
    assert not _is_pdf_source("https://example.com/page.html")


def test_classify_paths(tmp_path: Path) -> None:
    md = _write(tmp_path / "a.md", "# Hi\n")
    txt = _write(tmp_path / "a.txt", "plain\n")
    assert _classify(str(md)) == "md"
    assert _classify(str(txt)) == "text"
    assert _classify(str(tmp_path)) == "dir"
    assert _classify(str(tmp_path / "*.md")) == "glob"
    assert _classify("https://github.com/owner/repo") == "git"
    assert _classify("2601.23265") == "pdf"
    assert _classify("https://example.com/page.html") == "url"
    assert _classify("not-a-thing-xyz") == "unknown"


# --------------------------------------------------------------------------- #
# gather_context
# --------------------------------------------------------------------------- #
def test_gather_markdown_header_split(tmp_path: Path) -> None:
    _write(tmp_path / "doc.md", "# Title\n\nintro\n\n## Methods\n\nbody\n")
    result = gather_context([str(tmp_path / "doc.md")])
    assert isinstance(result, GatherResult)
    # Two headers -> two section blocks, each labelled with the file name.
    assert len(result.blocks.sections) == 2
    paths = [s.section_path for s in result.blocks.sections]
    assert paths[0] == "[doc.md] Title"
    assert paths[1] == "[doc.md] Title > Methods"
    assert result.ingested[0]["kind"] == "md"
    assert not result.skipped


def test_gather_plain_text_single_block(tmp_path: Path) -> None:
    _write(tmp_path / "code.py", "def f():\n    return 1\n")
    result = gather_context([str(tmp_path / "code.py")])
    assert len(result.blocks.sections) == 1
    assert result.blocks.sections[0].section_path == "[code.py]"
    assert "return 1" in result.blocks.sections[0].text


def test_gather_directory_walk_readme_first(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "notes.md", "# Notes\n\nn\n")
    _write(tmp_path / "README.md", "# Readme\n\nr\n")
    _write(tmp_path / "main.py", "x = 1\n")  # code files are skipped in a dir walk
    result = gather_context([str(tmp_path)])
    labels = [e["label"] for e in result.ingested]
    # README sorts first; the .py file is not collected by the doc walk.
    assert labels[0] == "README.md"
    assert "docs/notes.md" in labels
    assert all(not lbl.endswith(".py") for lbl in labels)


def test_gather_glob(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _write(tmp_path / "a.md", "# A\n")
    _write(tmp_path / "b.md", "# B\n")
    _write(tmp_path / "c.txt", "c\n")
    monkeypatch.chdir(tmp_path)
    result = gather_context(["*.md"])
    labels = sorted(e["label"] for e in result.ingested)
    assert labels == ["a.md", "b.md"]


def test_gather_merges_and_reindexes(tmp_path: Path) -> None:
    _write(tmp_path / "one.md", "# One\n\na\n")
    _write(tmp_path / "two.md", "# Two\n\nb\n")
    result = gather_context([str(tmp_path / "one.md"), str(tmp_path / "two.md")])
    assert len(result.blocks.sections) == 2
    # Source provenance is recorded on the merged blocks' metadata.
    assert len(result.blocks.metadata["sources"]) == 2


def test_gather_unsupported_url_is_skipped_not_raised() -> None:
    result = gather_context(["https://example.com/page.html"])
    assert result.blocks.sections == []
    assert result.skipped and "unsupported URL" in result.skipped[0]["reason"]


def test_gather_unknown_source_is_skipped() -> None:
    result = gather_context(["definitely-not-a-real-path-xyz"])
    assert result.skipped and result.skipped[0]["source"] == "definitely-not-a-real-path-xyz"


def test_gather_string_source_is_normalized(tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "# A\n\nx\n")
    result = gather_context(str(tmp_path / "a.md"))  # bare string, not a list
    assert len(result.blocks.sections) == 1


def test_gather_file_budget_caps_total(tmp_path: Path) -> None:
    for i in range(5):
        _write(tmp_path / f"f{i}.md", f"# F{i}\n")
    result = gather_context([str(tmp_path)], max_files=2)
    assert len(result.ingested) == 2


def test_gather_truncates_long_text(tmp_path: Path) -> None:
    _write(tmp_path / "big.txt", "x" * 5000)
    result = gather_context([str(tmp_path / "big.txt")], max_text_chars=100)
    assert result.ingested[0]["truncated"] is True
    assert "truncated" in result.blocks.sections[0].text


def test_render_context_markdown(tmp_path: Path) -> None:
    _write(tmp_path / "doc.md", "# Title\n\nbody text\n")
    result = gather_context([str(tmp_path / "doc.md")])
    rendered = render_context_markdown(result.blocks)
    assert "[doc.md] Title" in rendered
    assert "body text" in rendered

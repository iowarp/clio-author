"""Hermetic tests for :class:`SafeFiles` (all I/O under a ``tmp_path`` root)."""

from __future__ import annotations

from pathlib import Path

import pytest

from clio_author.tools.files import (
    EditNotApplicableError,
    FileOutsideRootError,
    RefusedWriteError,
    SafeFiles,
    SymlinkRefusedError,
)


def test_write_new_then_read_round_trip(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    path = files.write_new("draft.md", "hello world")

    assert path == tmp_path / "draft.md"
    assert path.read_text(encoding="utf-8") == "hello world"
    assert files.read("draft.md") == "hello world"


def test_write_new_creates_nested_dirs_not_implicitly(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    # The parent must exist; SafeFiles does not mkdir intermediate dirs.
    (tmp_path / "sub").mkdir()
    path = files.write_new("sub/note.md", "x")
    assert path == tmp_path / "sub" / "note.md"


def test_write_new_refuses_overwrite(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    files.write_new("draft.md", "first")

    with pytest.raises(RefusedWriteError):
        files.write_new("draft.md", "second")
    assert (tmp_path / "draft.md").read_text(encoding="utf-8") == "first"


def test_write_refuses_symlink_pointing_outside(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    files = SafeFiles(root)

    link = root / "link.md"
    link.symlink_to(outside)

    with pytest.raises(SymlinkRefusedError):
        files.write_new("link.md", "should not write through")
    with pytest.raises(SymlinkRefusedError):
        files.read("link.md")
    # The outside file is untouched.
    assert outside.read_text(encoding="utf-8") == "secret"


def test_resolve_rejects_absolute_path(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    with pytest.raises(FileOutsideRootError):
        files.write_new("/etc/passwd", "nope")


def test_resolve_rejects_parent_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    files = SafeFiles(root)
    with pytest.raises(FileOutsideRootError):
        files.read("../outside.txt")
    with pytest.raises(FileOutsideRootError):
        files.write_new("../escape.md", "nope")


def test_resolve_rejects_symlinked_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    files = SafeFiles(root)

    (root / "bridge").symlink_to(outside_dir, target_is_directory=True)
    with pytest.raises(FileOutsideRootError):
        files.write_new("bridge/escape.md", "nope")


def test_apply_edit_success(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    files.write_new("draft.md", "the quick brown fox")

    path = files.apply_edit("draft.md", "quick", "slow")
    assert path.read_text(encoding="utf-8") == "the slow brown fox"


def test_apply_edit_zero_match_raises(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    files.write_new("draft.md", "no match here")

    with pytest.raises(EditNotApplicableError):
        files.apply_edit("draft.md", "absent", "x")
    assert (tmp_path / "draft.md").read_text(encoding="utf-8") == "no match here"


def test_apply_edit_multi_match_raises(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    files.write_new("draft.md", "ab ab ab")

    with pytest.raises(EditNotApplicableError):
        files.apply_edit("draft.md", "ab", "cd", count=1)
    assert (tmp_path / "draft.md").read_text(encoding="utf-8") == "ab ab ab"


def test_apply_edit_explicit_count(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    files.write_new("draft.md", "ab ab ab")

    path = files.apply_edit("draft.md", "ab", "cd", count=3)
    assert path.read_text(encoding="utf-8") == "cd cd cd"


def test_apply_edit_no_stray_temp_files(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    files.write_new("draft.md", "x")
    files.apply_edit("draft.md", "x", "y")

    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".")]
    assert leftovers == []

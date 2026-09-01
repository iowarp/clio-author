"""Safe, root-confined file I/O for the writer/editor experts.

:class:`SafeFiles` is a trust boundary: every read, write, and edit it performs is
confined to a single ``root`` directory. It refuses to follow symlinks, to clobber
existing files on a fresh write, and to resolve any path that escapes ``root`` via
an absolute path or ``..`` traversal.

The atomic, ``O_EXCL | O_NOFOLLOW`` write pattern generalises the one used by the
citation expert (:func:`clio_author.experts.citation._atomic_write_text`); the
safety logic lives here so callers do not fork it.
"""

from __future__ import annotations

import errno
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


class FileToolError(RuntimeError):
    """Base class for all :class:`SafeFiles` refusals/failures."""


class FileOutsideRootError(FileToolError):
    """Raised when a relative path resolves outside the confined ``root``."""


class RefusedWriteError(FileToolError):
    """Raised when a write is refused (clobber, symlink, or OS-level failure)."""


class EditNotApplicableError(FileToolError):
    """Raised when ``apply_edit``'s ``old`` text does not match ``count`` times."""


class SymlinkRefusedError(FileToolError):
    """Raised when a path component is a symlink and following it is refused."""


class SafeFiles:
    """Read/write/edit file tools confined to a single ``root`` directory.

    All public methods take a *relative* path and confine I/O to ``root``.
    Absolute paths and ``..`` traversal are rejected; symlinks are never
    followed; a fresh write never clobbers an existing file.
    """

    def __init__(self, root: Path) -> None:
        """Confine all I/O to ``root`` (created if missing).

        ``root`` itself is resolved once (following any symlinks on the way to
        it); subsequent per-call resolution checks containment against this
        canonical root.
        """
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)

    def _resolve(self, rel: str | os.PathLike[str]) -> Path:
        """Resolve ``rel`` against ``root``, rejecting escapes.

        Rejects absolute paths and any path whose resolved parent escapes
        ``root`` (via ``..`` or a symlinked ancestor). The leaf itself is *not*
        required to exist; its parent's ``realpath`` must stay within ``root``.
        Returns the (non-resolved) joined path for use with ``O_NOFOLLOW`` opens.
        """
        rel_path = Path(rel)
        if rel_path.is_absolute():
            raise FileOutsideRootError(f"absolute paths are not allowed: {rel!r}")
        if not rel_path.parts:
            raise FileOutsideRootError("empty path is not allowed")

        target = self.root / rel_path
        # Resolve the parent directory (realpath) and confirm containment. The
        # leaf is appended afterwards so a non-existent target is still allowed,
        # while a symlinked ancestor that escapes root is caught here.
        resolved_parent = target.parent.resolve()
        if resolved_parent != self.root and not resolved_parent.is_relative_to(self.root):
            raise FileOutsideRootError(f"path escapes root: {rel!r}")
        return resolved_parent / target.name

    def read(self, rel: str | os.PathLike[str]) -> str:
        """Read ``rel`` as UTF-8 text without following a symlink at the leaf.

        Opens with ``O_RDONLY | O_NOFOLLOW`` so a symlink at the path raises
        :class:`SymlinkRefusedError` (``ELOOP``) rather than reading through it.
        """
        path = self._resolve(rel)
        flags = os.O_RDONLY | _O_NOFOLLOW
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            if exc.errno in _SYMLINK_ERRNOS:
                raise SymlinkRefusedError(f"refusing to follow symlink: {path}") from exc
            raise FileToolError(f"cannot read {path}: {exc}") from exc
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            return handle.read()

    def write_new(self, rel: str | os.PathLike[str], text: str, *, overwrite: bool = False) -> Path:
        """Create ``rel`` with ``text``; never follow a symlink.

        Opens with ``O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW`` so an existing
        file or a symlink at the path causes an ``OSError`` that is re-raised as
        :class:`RefusedWriteError` (or :class:`SymlinkRefusedError`).

        With ``overwrite=True`` the ``O_EXCL`` guard is swapped for ``O_TRUNC``, so
        an existing regular file is replaced. The symlink refusal is **not**
        relaxed: ``O_NOFOLLOW`` plus the explicit ``is_symlink`` check still apply,
        so overwriting can never be redirected outside ``root``.
        """
        path = self._resolve(rel)
        # ``O_EXCL`` makes a symlink fail with ``EEXIST`` (not ``ELOOP``), so the
        # link is reported explicitly here before the open, mirroring the
        # citation expert's ``is_symlink()`` guard. ``lstat``-based check does not
        # follow the link, so a dangling link is also caught.
        if path.is_symlink():
            raise SymlinkRefusedError(f"refusing to follow symlink: {path}")
        exclusivity = os.O_TRUNC if overwrite else os.O_EXCL
        flags = os.O_CREAT | exclusivity | os.O_WRONLY | _O_NOFOLLOW
        try:
            fd = os.open(path, flags, 0o644)
        except OSError as exc:
            if exc.errno in _SYMLINK_ERRNOS:
                raise SymlinkRefusedError(f"refusing to follow symlink: {path}") from exc
            raise RefusedWriteError(f"refusing to write {path}: {exc}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def apply_edit(
        self,
        rel: str | os.PathLike[str],
        old: str,
        new: str,
        *,
        count: int = 1,
    ) -> Path:
        """Replace ``old`` with ``new`` in ``rel``, requiring an exact match count.

        Reads the file (``O_NOFOLLOW``); ``old`` must occur exactly ``count``
        times, else :class:`EditNotApplicableError`. The replacement is written
        atomically: a fresh temp file (``O_EXCL | O_NOFOLLOW``) in ``root`` is
        written then ``os.replace``-d over the target.
        """
        path = self._resolve(rel)
        current = self.read(rel)
        occurrences = current.count(old)
        if occurrences != count:
            raise EditNotApplicableError(
                f"expected {count} occurrence(s) of the target text in {path}, found {occurrences}"
            )
        updated = current.replace(old, new, count)
        self._atomic_overwrite(path, updated)
        return path

    def _atomic_overwrite(self, path: Path, text: str) -> None:
        """Write ``text`` over ``path`` atomically via a temp file + ``os.replace``.

        ``tempfile.mkstemp`` mints a unique, per-call temp name (so concurrent
        edits in the same process never collide) *inside* ``root`` -- keeping it
        on the same filesystem so ``os.replace`` is atomic. The fd it returns is
        opened by ``mkstemp`` itself with ``O_EXCL | O_NOFOLLOW`` semantics, so no
        symlink is followed; on any failure the temp file is removed and the error
        surfaces as a :class:`RefusedWriteError`.
        """
        try:
            fd, tmp_name = tempfile.mkstemp(dir=self.root, prefix=f".{path.name}.", suffix=".tmp")
        except OSError as exc:
            raise RefusedWriteError(f"refusing to create temp file in {self.root}: {exc}") from exc
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise RefusedWriteError(f"refusing to complete write of {path}: {exc}") from exc


# ``O_NOFOLLOW`` is POSIX; guard for portability (it always exists on Linux).
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

# errno values an ``O_NOFOLLOW`` open raises when the leaf is a symlink.
_SYMLINK_ERRNOS = {getattr(errno, name) for name in ("ELOOP", "EMLINK") if hasattr(errno, name)}


def write_artifacts(
    files: SafeFiles,
    items: Iterable[tuple[str, str]],
    *,
    overwrite: bool = False,
) -> tuple[list[str], list[str]]:
    """Write ``(relative_path, text)`` pairs; return ``(wrote, skipped)``.

    The shared persist helper for every action that has an ``out_dir``. A refused
    write (an existing file, without ``overwrite``) lands in ``skipped`` as
    ``"<rel>: <reason>"`` instead of vanishing, so the caller can surface it in
    ``metadata["write_skipped"]`` -- a silently empty ``wrote`` list is
    indistinguishable from a successful run, which is exactly the failure this
    helper exists to prevent.

    Never raises: every refusal is captured. Writes are attempted for every item,
    so one refusal does not hide the rest.
    """
    wrote: list[str] = []
    skipped: list[str] = []
    for rel, text in items:
        try:
            wrote.append(str(files.write_new(rel, text, overwrite=overwrite)))
        except FileToolError as exc:
            skipped.append(f"{rel}: {_refusal_reason(exc)}")
    return wrote, skipped


def _refusal_reason(exc: FileToolError) -> str:
    """A short, path-free reason for a refused write (paths are already in ``rel``)."""
    if isinstance(exc, SymlinkRefusedError):
        return "refused: path is a symlink"
    cause = exc.__cause__
    if isinstance(cause, OSError) and cause.errno == errno.EEXIST:
        return "already exists"
    return str(exc)


def wants_overwrite(payload: Mapping[str, Any]) -> bool:
    """Read the ``overwrite`` (alias ``force``) flag out of an action payload."""
    return bool(payload.get("overwrite") or payload.get("force"))


__all__ = [
    "SafeFiles",
    "FileToolError",
    "FileOutsideRootError",
    "RefusedWriteError",
    "EditNotApplicableError",
    "SymlinkRefusedError",
    "write_artifacts",
    "wants_overwrite",
]

"""File tools confined to a trusted root.

:mod:`clio_parser.tools.files` provides :class:`SafeFiles`, a small read/write/edit
surface whose I/O is confined to a single ``root`` directory. It generalises the
atomic, symlink- and clobber-refusing write pattern used by the citation expert
(see :func:`clio_parser.experts.citation._atomic_write_text`).
"""

from clio_parser.tools.files import (
    EditNotApplicableError,
    FileOutsideRootError,
    FileToolError,
    RefusedWriteError,
    SafeFiles,
    SymlinkRefusedError,
)

__all__ = [
    "SafeFiles",
    "FileToolError",
    "FileOutsideRootError",
    "RefusedWriteError",
    "EditNotApplicableError",
    "SymlinkRefusedError",
]

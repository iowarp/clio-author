"""Project memory: a file-backed blackboard shared by role-agents.

A :class:`ProjectMemory` is a directory of JSON slots under a project root
(e.g. ``clio-out/<project>/memory/``). Role-agents read and write named slots so
they hand off without re-deriving: the **writer** writes ``outline`` / ``plan`` /
``drafts``; the **verifier** reads them and writes ``reports``; ``decisions``
holds the locked decisions injected into every write/revise; ``argument_map``
holds the claim→section map. Slots are free-form strings (the canonical set is
documented in :data:`CANONICAL_SLOTS`), values are any JSON-serialisable object.

Pure and dependency-light. Best-effort and **never raises**: an unreadable or
corrupt slot reads back as the supplied default rather than throwing, so a role
degrades gracefully instead of aborting.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# The canonical slots role-agents use. Not enforced — any string is a valid slot
# — but documented so roles agree on names.
CANONICAL_SLOTS: tuple[str, ...] = (
    "outline",
    "plan",
    "plan_check",
    "decisions",
    "argument_map",
    "drafts",
    "bib",
    "citations",
    "reports",
)

_SAFE_SLOT = re.compile(r"^[A-Za-z0-9_.-]+$")


class ProjectMemory:
    """A directory of JSON slots shared across role-agent calls."""

    def __init__(self, root: str | Path) -> None:
        """Open (creating if needed) the memory directory at ``root``."""
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, slot: str) -> Path:
        """Map a slot name to its JSON file, rejecting unsafe names."""
        if not _SAFE_SLOT.match(slot):
            raise ValueError(f"invalid slot name: {slot!r}")
        return self.root / f"{slot}.json"

    def put(self, slot: str, value: Any) -> None:
        """Write ``value`` (any JSON-serialisable object) to ``slot``.

        Best-effort: a serialisation or write failure is swallowed (the slot is
        simply not persisted) so a role never crashes on a memory write.
        """
        try:
            self._path(slot).write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
        except (OSError, TypeError, ValueError):
            return

    def get(self, slot: str, default: Any = None) -> Any:
        """Return the value stored in ``slot``, or ``default`` when absent/corrupt."""
        try:
            path = self._path(slot)
        except ValueError:
            return default
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def has(self, slot: str) -> bool:
        """True when ``slot`` is present and readable."""
        try:
            return self._path(slot).is_file()
        except ValueError:
            return False

    def slots(self) -> list[str]:
        """Return the present slot names (sorted), without the ``.json`` suffix."""
        try:
            return sorted(p.stem for p in self.root.glob("*.json") if p.is_file())
        except OSError:
            return []

    def update(self, slot: str, **fields: Any) -> dict[str, Any]:
        """Merge ``fields`` into a dict-valued ``slot`` and persist; return the merged dict.

        A non-dict (or absent) current value is replaced by ``fields``.
        """
        current = self.get(slot, {})
        merged: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
        merged.update(fields)
        self.put(slot, merged)
        return merged


__all__ = ["ProjectMemory", "CANONICAL_SLOTS"]

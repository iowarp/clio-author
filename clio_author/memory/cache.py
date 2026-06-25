"""Result cache: skip re-running an unchanged action.

A :class:`ResultCache` stores an action's result keyed on the content of the call
— ``(action, payload, model)`` — so that re-running the *same* step (common in
refine loops like writer ↔ reviewer) returns instantly instead of spending tokens
again. Keys are a SHA-256 over a canonical JSON encoding, so equal inputs hit
regardless of dict ordering.

Pure, file-backed, and **never raises**: a miss, an unreadable entry, or a
non-serialisable payload all degrade to "no cache" (the caller just recomputes).
Conservative by design — a stale hit is worse than a recompute, so the key
includes the model id and the full payload.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ResultCache:
    """A content-addressed cache of action results under a directory."""

    def __init__(self, root: str | Path) -> None:
        """Open (creating if needed) the cache directory at ``root``."""
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(action: str, payload: dict[str, Any], model: str | None) -> str | None:
        """Stable hash of the call; ``None`` when the payload is not serialisable."""
        try:
            blob = json.dumps(
                {"action": action, "payload": payload, "model": model or ""},
                sort_keys=True,
                default=str,
            )
        except (TypeError, ValueError):
            return None
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def get(
        self, action: str, payload: dict[str, Any], model: str | None = None
    ) -> dict[str, Any] | None:
        """Return the cached result for this call, or ``None`` on a miss."""
        key = self._key(action, payload, model)
        if key is None:
            return None
        path = self.root / f"{key}.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def put(
        self,
        action: str,
        payload: dict[str, Any],
        result: dict[str, Any],
        model: str | None = None,
    ) -> None:
        """Store ``result`` for this call. Best-effort: failures are swallowed."""
        key = self._key(action, payload, model)
        if key is None:
            return
        try:
            (self.root / f"{key}.json").write_text(
                json.dumps(result, default=str), encoding="utf-8"
            )
        except (OSError, TypeError, ValueError):
            return


__all__ = ["ResultCache"]

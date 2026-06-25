"""The refiner role: apply feedback / polish existing prose, then re-check it."""

from __future__ import annotations

from typing import Any

from clio_author.harness.types import AgentOutput
from clio_author.roles.base import RoleAgent


class RefinerRole(RoleAgent):
    """Revise prose (feedback or style), then re-check cross-section coherence."""

    name = "refiner"
    description = "Revise prose to address feedback or polish voice, then re-check coherence."

    def run(self, payload: dict[str, Any], memory: Any = None) -> AgentOutput:  # noqa: ANN401
        try:
            reports: dict[str, Any] = {}
            has_text = bool(payload.get("text") or payload.get("draft") or payload.get("markdown"))
            if not has_text:
                return self._error("refiner needs 'text'/'draft'/'markdown' to revise")

            # feedback mode when a review/critique is supplied; otherwise style polish.
            mode = "feedback" if (payload.get("review") or payload.get("critic_notes")) else "style"
            rv = self.call("revise", {**payload, "mode": mode})
            reports["revise"] = {"mode": mode, "content": rv.content}

            # re-check consistency over the (revised) manuscript when there is structure.
            if payload.get("markdown") or payload.get("sections"):
                co = self.call("coherence", payload)
                reports["coherence"] = co.structured or {}
            if memory is not None:
                memory.put("drafts", {"revised": rv.content})
        except Exception as exc:  # noqa: BLE001 - roles never raise
            return self._error(str(exc))

        return self._ok(
            f"Refiner revised ({mode})"
            + (" and re-checked coherence." if "coherence" in reports else "."),
            reports,
            {"mode": mode, "steps": sorted(reports)},
            next_role="reviewer",
            next_why="re-review the revised draft",
        )


__all__ = ["RefinerRole"]

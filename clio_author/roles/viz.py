"""The viz role: everything visual — figures, their refinement, and captions."""

from __future__ import annotations

from typing import Any

from clio_author.harness.types import AgentOutput
from clio_author.roles.base import RoleAgent


class VizRole(RoleAgent):
    """Generate a figure (optionally refined by a critic) or caption figures."""

    name = "viz"
    description = "Make a figure (with optional critic refinement) or caption figures."

    def run(self, payload: dict[str, Any], memory: Any = None) -> AgentOutput:  # noqa: ANN401
        try:
            reports: dict[str, Any] = {}

            if payload.get("spec"):
                if payload.get("loop") or payload.get("refine"):
                    fr = self.call("figure_refine", payload)
                    reports["figure_refine"] = {"content": fr.content, **fr.metadata}
                else:
                    p = self.call("plot", payload)
                    reports["plot"] = {"content": p.content, **p.metadata}

            if payload.get("blocks") or payload.get("figures"):
                d = self.call("describe_figures", payload)
                reports["describe_figures"] = d.metadata

            if not reports:
                return self._error(
                    "viz needs a 'spec' (to plot) or 'blocks'/'figures' (to caption)"
                )
            if memory is not None:
                memory.update("reports", viz=reports)
        except Exception as exc:  # noqa: BLE001 - roles never raise
            return self._error(str(exc))

        return self._ok(
            f"Viz ran: {', '.join(sorted(reports))}.",
            reports,
            {"steps": sorted(reports)},
        )


__all__ = ["VizRole"]

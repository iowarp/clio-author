"""The scholar role: find + verify the literature and design the evaluation."""

from __future__ import annotations

from typing import Any

from clio_author.harness.types import AgentOutput
from clio_author.roles.base import RoleAgent


class ScholarRole(RoleAgent):
    """Discover real papers, write a grounded brief, verify citations, plan the eval."""

    name = "scholar"
    description = "Find + verify literature (discover/research/cite) and design the evaluation."

    def run(self, payload: dict[str, Any], memory: Any = None) -> AgentOutput:  # noqa: ANN401
        try:
            reports: dict[str, Any] = {}

            if payload.get("query") or payload.get("topic"):
                d = self.call("discover", payload)
                reports["discover"] = d.metadata
                if payload.get("topic"):
                    r = self.call("research", payload)
                    reports["research"] = r.structured or {}

            if payload.get("candidates"):
                c = self.call("cite", payload)
                reports["cite"] = c.structured or {}
                if memory is not None and c.structured:
                    memory.put("bib", c.structured.get("suggested_bibtex", ""))
                    memory.put("citations", c.structured.get("verified", []))

            if payload.get("idea") and (payload.get("sources") or payload.get("blocks")):
                e = self.call("experiment", payload)
                reports["experiment"] = e.metadata

            if not reports:
                return self._error("scholar needs a topic/query, candidates, or an idea + sources")
        except Exception as exc:  # noqa: BLE001 - roles never raise
            return self._error(str(exc))

        return self._ok(
            f"Scholar ran: {', '.join(sorted(reports))}.",
            reports,
            {"steps": sorted(reports)},
            next_role="writer",
            next_why="turn the grounded literature into a planned draft",
        )


__all__ = ["ScholarRole"]

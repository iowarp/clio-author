"""The writer role: idea → validated plan → drafted prose."""

from __future__ import annotations

from typing import Any

from clio_author.harness.types import AgentOutput
from clio_author.roles.base import RoleAgent


class WriterRole(RoleAgent):
    """Plan the paper, validate the plan, then draft it (deterministic gate first)."""

    name = "writer"
    description = "Plan → validate the plan (plan_check) → draft the whole paper."

    def run(self, payload: dict[str, Any], memory: Any = None) -> AgentOutput:  # noqa: ANN401
        try:
            reports: dict[str, Any] = {}

            # 1 · plan the sections.
            plan_out = self.call("plan", payload)
            plan = plan_out.structured or {}
            reports["plan"] = {"num_sections": len(plan.get("plans", []))}
            if memory is not None:
                memory.put("plan", plan)
                memory.put("outline", plan.get("outline"))

            # 2 · validate the plan BEFORE writing (cheap; no LLM).
            if plan.get("plans"):
                pc = self.call("plan_check", {"plan": plan})
                reports["plan_check"] = {"content": pc.content, **pc.metadata}

            # 3 · draft, reusing the validated outline (so compose does not re-plan).
            compose_payload = dict(payload)
            if plan.get("outline"):
                compose_payload["outline"] = plan["outline"]
            drafted = self.call("compose", compose_payload)
            reports["compose"] = {
                k: v for k, v in drafted.metadata.items() if k != "suggested_next"
            }
            if memory is not None and drafted.structured is not None:
                memory.put("drafts", drafted.structured)
        except Exception as exc:  # noqa: BLE001 - roles never raise
            return self._error(str(exc))

        pc_report: dict[str, Any] = reports.get("plan_check") or {}
        summary = (
            f"Writer planned {reports['plan']['num_sections']} section(s)"
            + (", plan " + ("OK" if pc_report.get("passed") else "has issues") if pc_report else "")
            + ", and drafted the paper."
        )
        return self._ok(
            summary,
            reports,
            {"num_sections": reports["plan"]["num_sections"], "plan_ok": pc_report.get("passed")},
            next_role="verifier",
            next_why="check the draft is grounded and complete",
        )


__all__ = ["WriterRole"]

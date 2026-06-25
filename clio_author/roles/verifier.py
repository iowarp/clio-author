"""The verifier role: "is it correct and grounded?" in one pass.

Owns the verification sub-domain. Runs a deterministic-first policy over the
verification tools and returns one consolidated report:

1. ``plan_check`` — if a plan is supplied (pre-write validation; no LLM),
2. ``ground`` — citation + claim + source-support integrity (the rolled-up score),
3. ``audit`` — manuscript completeness (no LLM),
4. ``coherence`` — cross-section consistency.

Cheap deterministic checks run first; the model-backed steps run only when their
inputs are present. The consolidated grounding-integrity number is the headline.
Writes its report to ``ProjectMemory['reports']`` so the refiner can pick it up.
"""

from __future__ import annotations

from typing import Any

from clio_author.harness.types import AgentOutput
from clio_author.roles.base import RoleAgent


class VerifierRole(RoleAgent):
    """Role that consolidates plan/citation/claim/coherence/completeness checks."""

    name = "verifier"
    description = "Check a plan or manuscript for correctness and grounding, in one pass."

    def run(self, payload: dict[str, Any], memory: Any = None) -> AgentOutput:  # noqa: ANN401
        try:
            reports: dict[str, Any] = {}
            has_prose = bool(
                payload.get("markdown") or payload.get("text") or payload.get("sections")
            )

            # 1 · pre-write plan validation (deterministic) — if a plan is given.
            if payload.get("plan") or payload.get("plans"):
                pc = self.call("plan_check", payload)
                reports["plan_check"] = {"content": pc.content, **pc.metadata}

            # 2 · grounding integrity (citations + claims + source support).
            if (
                payload.get("bibtex")
                or payload.get("claims")
                or payload.get("section_plan")
                or payload.get("citations")
            ):
                g = self.call("ground", payload)
                reports["grounding"] = g.structured or {}

            # 3 · completeness audit (deterministic) — if there is prose.
            if has_prose:
                a = self.call("audit", payload)
                reports["audit"] = a.structured or {}

            # 4 · cross-section coherence — if there is prose.
            if has_prose:
                c = self.call("coherence", payload)
                reports["coherence"] = c.structured or {}

            if not reports:
                return self._error(
                    "verifier needs a plan, a bibliography/claims/citations, or a manuscript"
                )
        except Exception as exc:  # noqa: BLE001 - roles never raise
            return self._error(str(exc))

        gi = (reports.get("grounding") or {}).get("grounding_integrity")
        if memory is not None:
            memory.put("reports", reports)

        summary = self._summary(reports, gi)
        return self._ok(
            summary,
            reports,
            {
                "grounding_integrity": gi,
                "checks_run": sorted(reports),
                "plan_ok": (reports.get("plan_check") or {}).get("passed"),
                "audit_passed": (reports.get("audit") or {}).get("passed")
                if "audit" in reports
                else None,
            },
            next_role="refiner",
            next_why="fix the weak spots verification surfaced",
        )

    @staticmethod
    def _summary(reports: dict[str, Any], gi: float | None) -> str:
        parts = [f"Verifier ran: {', '.join(sorted(reports))}."]
        if gi is not None:
            parts.append(f"Grounding integrity {round(gi * 100)}%.")
        pc = reports.get("plan_check")
        if pc is not None:
            parts.append("Plan check " + ("PASSED" if pc.get("passed") else "FOUND ISSUES") + ".")
        return " ".join(parts)


__all__ = ["VerifierRole"]

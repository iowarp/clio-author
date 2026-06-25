"""The reviewer role: referee the paper (whole or per-section) and aggregate."""

from __future__ import annotations

from typing import Any

from clio_author.harness.types import AgentOutput
from clio_author.roles.base import RoleAgent


class ReviewerRole(RoleAgent):
    """Peer-review a manuscript or a single section, and aggregate supplied reviews."""

    name = "reviewer"
    description = "Referee the paper (whole or per-section); aggregate reviews into a decision."

    def run(self, payload: dict[str, Any], memory: Any = None) -> AgentOutput:  # noqa: ANN401
        try:
            reports: dict[str, Any] = {}

            # already-collected reviews -> area-chair aggregation.
            if payload.get("reviews"):
                m = self.call("meta_review", payload)
                reports["meta_review"] = m.structured or {}

            # a single section -> the layered section review.
            if payload.get("section") or str(payload.get("scope") or "") == "section":
                sr = self.call("section_review", payload)
                reports["section_review"] = sr.structured or {}
            # a whole paper -> a full peer review.
            elif payload.get("paper") or payload.get("markdown") or payload.get("text"):
                rv = self.call("review", payload)
                reports["review"] = rv.structured or {"content": rv.content}

            if not reports:
                return self._error(
                    "reviewer needs a paper/section to review, or reviews to aggregate"
                )
            if memory is not None:
                memory.update("reports", reviewer=reports)
        except Exception as exc:  # noqa: BLE001 - roles never raise
            return self._error(str(exc))

        return self._ok(
            f"Reviewer ran: {', '.join(sorted(reports))}.",
            reports,
            {"steps": sorted(reports)},
            next_role="refiner",
            next_why="address the review's points",
        )


__all__ = ["ReviewerRole"]

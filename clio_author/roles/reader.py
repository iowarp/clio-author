"""The reader role: turn sources into understood, queryable memory."""

from __future__ import annotations

from typing import Any

from clio_author.harness.types import AgentOutput
from clio_author.roles.base import RoleAgent


class ReaderRole(RoleAgent):
    """Ingest source(s) and build understanding (blocks → graph; or answer a question)."""

    name = "reader"
    description = "Ingest sources and understand them: blocks, a content graph, or an answer."

    def run(self, payload: dict[str, Any], memory: Any = None) -> AgentOutput:  # noqa: ANN401
        try:
            reports: dict[str, Any] = {}
            blocks: Any = payload.get("blocks")

            if payload.get("sources"):
                g = self.call("gather", payload)
                reports["gather"] = g.metadata
                blocks = blocks or g.structured
            elif payload.get("source"):
                ing = self.call("ingest", payload)
                reports["ingest"] = ing.metadata
                blocks = blocks or ing.structured

            if payload.get("question"):
                a = self.call("ask", {**payload, "blocks": blocks} if blocks else payload)
                reports["ask"] = {"content": a.content, **a.metadata}
            elif blocks:
                kg = self.call("kg", {**payload, "blocks": blocks})
                reports["kg"] = kg.metadata

            if not reports:
                return self._error("reader needs a source/sources, blocks, or a question")
            if memory is not None and blocks:
                memory.put("blocks", blocks)
        except Exception as exc:  # noqa: BLE001 - roles never raise
            return self._error(str(exc))

        return self._ok(
            f"Reader ran: {', '.join(sorted(reports))}.",
            reports,
            {"steps": sorted(reports)},
            next_role="scholar",
            next_why="find and verify the related literature",
        )


__all__ = ["ReaderRole"]

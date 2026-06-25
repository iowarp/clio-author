"""The role-agent base: a fixed policy that delegates *down* to tools.

A **role-agent** owns a sub-domain (writing, verification, review, …) and runs a
**fixed policy** over the tools — it does not plan with a model the way
``orchestrate`` does, so it spends no tokens deciding what to do. It delegates to
tools through an injected ``dispatch`` callable (the agent wires this to its own
router), reads/writes a shared :class:`~clio_author.memory.ProjectMemory` so roles
hand off without re-deriving, and returns one consolidated
:class:`~clio_author.harness.types.AgentOutput`.

Like every expert, a role **never raises**: any failure becomes an error-flagged
output. Roles are *peers* — they must not call other roles (only ``orchestrate``
or the host sequences peers); they delegate only to tools.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from clio_author.harness.types import AgentOutput

# A dispatch runs one *tool* action and returns its output. Injected by the agent.
Dispatch = Callable[[str, dict[str, Any]], AgentOutput]


class RoleAgent:
    """Base class for a role-agent (a fixed policy over tools)."""

    name: str = "role"
    description: str = ""

    def __init__(self, dispatch: Dispatch) -> None:
        """Build the role with a tool ``dispatch`` ``(action, payload) -> AgentOutput``."""
        self._dispatch = dispatch

    def call(self, action: str, payload: dict[str, Any]) -> AgentOutput:
        """Delegate to one tool action and return its output."""
        return self._dispatch(action, payload)

    def run(self, payload: dict[str, Any], memory: Any = None) -> AgentOutput:  # noqa: ANN401
        """Execute the role's policy. Override in subclasses; never raise."""
        raise NotImplementedError

    # --- helpers for subclasses ------------------------------------------- #
    def _error(self, message: str) -> AgentOutput:
        return AgentOutput(agent=self.name, content="", metadata={"error": message})

    def _ok(
        self,
        content: str,
        structured: dict[str, Any] | None,
        metadata: dict[str, Any],
        *,
        next_role: str | None = None,
        next_why: str = "",
    ) -> AgentOutput:
        """Build a successful consolidated output, with an optional next-role hint."""
        meta = dict(metadata)
        if next_role:
            meta.setdefault("suggested_next", [{"action": f"role:{next_role}", "why": next_why}])
        return AgentOutput(agent=self.name, content=content, structured=structured, metadata=meta)


__all__ = ["RoleAgent", "Dispatch"]

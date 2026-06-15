"""Shared session state threaded through a harness run.

A :class:`SessionContext` accumulates the outputs produced by each agent and
carries an arbitrary ``data`` bag for cross-agent state. Later milestones extend
this with checkpoints for resumable runs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from clio_parser.harness.types import AgentOutput


class SessionContext(BaseModel):
    """Mutable, shared state for a single harness run."""

    id: str
    history: list[AgentOutput] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    def add(self, output: AgentOutput) -> None:
        """Append an agent output to the run history."""
        self.history.append(output)

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable snapshot of the current session state."""
        return self.model_dump()

"""The agent interface contract.

Every expert subagent implements :class:`AgentProtocol`. Keeping this as a
``runtime_checkable`` ``Protocol`` lets patterns and the engine accept any
conforming object without inheritance coupling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from clio_parser.harness.types import AgentOutput, Task

if TYPE_CHECKING:
    from clio_parser.harness.session import SessionContext


@runtime_checkable
class AgentProtocol(Protocol):
    """Interface implemented by all expert subagents."""

    @property
    def name(self) -> str:
        """The agent's role/identifier."""
        ...

    def run(self, task: Task, session: "SessionContext") -> AgentOutput:
        """Execute the task and return the agent's output."""
        ...

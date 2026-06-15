"""Hermetic tests for the :class:`Parallel` pattern.

Uses small local stub agents (no network) to assert input-order preservation,
single ``session.add`` per agent, and an Engine-driven run.
"""

from __future__ import annotations

from clio_parser.harness.engine import Engine
from clio_parser.harness.patterns import Parallel
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Task


class StubAgent:
    """Minimal :class:`AgentProtocol` agent that records each ``run`` once."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.calls = 0

    @property
    def name(self) -> str:
        return self.label

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        self.calls += 1
        output = AgentOutput(agent=self.label, content=f"{self.label}:{task.description}")
        session.add(output)
        return output


def test_parallel_preserves_input_order() -> None:
    agents = [StubAgent("a"), StubAgent("b"), StubAgent("c")]
    session = SessionContext(id="s")
    task = Task(id="t", description="task")

    outputs = Parallel().run(agents, task, session)

    assert [o.agent for o in outputs] == ["a", "b", "c"]


def test_parallel_appends_each_output_exactly_once() -> None:
    agents = [StubAgent("a"), StubAgent("b")]
    session = SessionContext(id="s")
    task = Task(id="t", description="task")

    outputs = Parallel().run(agents, task, session)

    assert session.history == outputs
    assert len(session.history) == 2
    assert all(agent.calls == 1 for agent in agents)


def test_parallel_runs_via_engine() -> None:
    agents = [StubAgent("x"), StubAgent("y")]
    task = Task(id="t", description="hello")

    outputs = Engine().run(agents, Parallel(), task)

    assert [o.content for o in outputs] == ["x:hello", "y:hello"]

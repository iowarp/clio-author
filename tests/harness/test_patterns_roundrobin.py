"""Hermetic tests for the :class:`RoundRobin` pattern.

Uses scripted local stub agents (no network) to assert that agents take turns
across ``rounds``: outputs land in turn order, the result length is
``agents * rounds``, each turn is appended to the session exactly once, a later
agent can read prior turns from ``session.history``, ``rounds`` is coerced
defensively, and the pattern runs through the :class:`Engine`.
"""

from __future__ import annotations

from clio_author.harness.engine import Engine
from clio_author.harness.patterns import RoundRobin
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task


class ScriptedAgent:
    """Agent that records how many prior turns it sees and labels its output."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.calls = 0
        self.seen_history_lengths: list[int] = []

    @property
    def name(self) -> str:
        return self.label

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        # Record how many prior turns are already in the shared history.
        self.seen_history_lengths.append(len(session.history))
        self.calls += 1
        output = AgentOutput(agent=self.label, content=f"{self.label}-turn{self.calls}")
        session.add(output)
        return output


def test_roundrobin_runs_in_turn_order_over_rounds() -> None:
    a = ScriptedAgent("a")
    b = ScriptedAgent("b")
    session = SessionContext(id="s")
    task = Task(id="t", description="deliberate", payload={"rounds": 2})

    outputs = RoundRobin().run([a, b], task, session)

    # agents * rounds == 4 outputs, in (round-major) turn order.
    assert [o.agent for o in outputs] == ["a", "b", "a", "b"]
    assert len(outputs) == 2 * 2
    assert a.calls == 2
    assert b.calls == 2


def test_roundrobin_appends_each_turn_once() -> None:
    a = ScriptedAgent("a")
    b = ScriptedAgent("b")
    session = SessionContext(id="s")
    task = Task(id="t", description="deliberate", payload={"rounds": 2})

    outputs = RoundRobin().run([a, b], task, session)

    # Each output appended exactly once -> history mirrors the returned list.
    assert session.history == outputs


def test_roundrobin_later_agent_sees_prior_turns() -> None:
    a = ScriptedAgent("a")
    b = ScriptedAgent("b")
    session = SessionContext(id="s")
    task = Task(id="t", description="deliberate", payload={"rounds": 2})

    RoundRobin().run([a, b], task, session)

    # a sees 0 then 2 prior turns; b sees 1 then 3 prior turns.
    assert a.seen_history_lengths == [0, 2]
    assert b.seen_history_lengths == [1, 3]


def test_roundrobin_default_rounds_is_one() -> None:
    a = ScriptedAgent("a")
    b = ScriptedAgent("b")
    session = SessionContext(id="s")
    task = Task(id="t", description="deliberate")

    outputs = RoundRobin().run([a, b], task, session)

    assert [o.agent for o in outputs] == ["a", "b"]


def test_roundrobin_coerces_non_int_rounds() -> None:
    a = ScriptedAgent("a")
    b = ScriptedAgent("b")
    session = SessionContext(id="s")
    task = Task(id="t", description="deliberate", payload={"rounds": "2"})

    outputs = RoundRobin().run([a, b], task, session)

    assert len(outputs) == 4

    # A non-numeric string falls back to the default of 1 round, never raising.
    session2 = SessionContext(id="s2")
    task2 = Task(id="t2", description="deliberate", payload={"rounds": "abc"})
    outputs2 = RoundRobin().run([a, b], task2, session2)
    assert len(outputs2) == 2


def test_roundrobin_no_agents_returns_empty() -> None:
    session = SessionContext(id="s")
    task = Task(id="t", description="deliberate", payload={"rounds": 3})

    assert RoundRobin().run([], task, session) == []


def test_roundrobin_runs_via_engine() -> None:
    a = ScriptedAgent("a")
    b = ScriptedAgent("b")
    task = Task(id="t", description="deliberate", payload={"rounds": 2})

    outputs = Engine().run([a, b], RoundRobin(), task)

    assert [o.agent for o in outputs] == ["a", "b", "a", "b"]

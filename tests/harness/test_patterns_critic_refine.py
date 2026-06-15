"""Hermetic tests for the :class:`CriticRefine` pattern.

Uses scripted local stub agents (no network) to assert the producer/critic loop:
running up to ``max_rounds``, short-circuiting on the no-changes sentinel,
returning the full ordered round history, stopping on an error-flagged output,
and degrading gracefully with fewer than two agents.
"""

from __future__ import annotations

from clio_parser.harness.patterns import NO_CHANGES_SENTINEL, CriticRefine
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Task


class ScriptedAgent:
    """Agent that returns canned ``content`` strings in sequence (cycling)."""

    def __init__(self, label: str, scripts: list[str], *, error_on: int | None = None) -> None:
        self.label = label
        self.scripts = scripts
        self.error_on = error_on
        self.calls = 0

    @property
    def name(self) -> str:
        return self.label

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        index = self.calls
        self.calls += 1
        metadata: dict[str, object] = {}
        if self.error_on is not None and index == self.error_on:
            metadata["error"] = "boom"
        content = self.scripts[min(index, len(self.scripts) - 1)]
        output = AgentOutput(agent=self.label, content=content, metadata=metadata)
        session.add(output)
        return output


def test_critic_refine_runs_up_to_max_rounds() -> None:
    producer = ScriptedAgent("producer", ["draft", "rev1", "rev2"])
    critic = ScriptedAgent("critic", ["needs work", "still", "more"])
    session = SessionContext(id="s")
    task = Task(id="t", description="write", payload={"max_rounds": 2})

    outputs = CriticRefine().run([producer, critic], task, session)

    # draft + (critic, revision) * 2 == 5 outputs.
    assert [o.agent for o in outputs] == [
        "producer",
        "critic",
        "producer",
        "critic",
        "producer",
    ]
    assert producer.calls == 3
    assert critic.calls == 2
    assert session.history == outputs


def test_critic_refine_short_circuits_on_sentinel() -> None:
    producer = ScriptedAgent("producer", ["draft", "rev1"])
    critic = ScriptedAgent("critic", [NO_CHANGES_SENTINEL])
    session = SessionContext(id="s")
    task = Task(id="t", description="write", payload={"max_rounds": 5})

    outputs = CriticRefine().run([producer, critic], task, session)

    assert [o.agent for o in outputs] == ["producer", "critic"]
    assert producer.calls == 1  # never revised
    assert outputs[-1].content.strip() == NO_CHANGES_SENTINEL


def test_critic_refine_returns_full_history_final_last() -> None:
    producer = ScriptedAgent("producer", ["d0", "d1"])
    critic = ScriptedAgent("critic", ["c0", NO_CHANGES_SENTINEL])
    session = SessionContext(id="s")
    task = Task(id="t", description="write", payload={"max_rounds": 3})

    outputs = CriticRefine().run([producer, critic], task, session)

    assert [o.content for o in outputs] == ["d0", "c0", "d1", NO_CHANGES_SENTINEL]
    assert outputs[-1] is outputs[-1]
    assert session.data["draft"] == "d1"
    assert session.data["critic_feedback"] == NO_CHANGES_SENTINEL


def test_critic_refine_stops_on_error_flagged_output() -> None:
    # Critic errors on its first call (index 0) -> loop stops after that output.
    producer = ScriptedAgent("producer", ["draft", "rev"])
    critic = ScriptedAgent("critic", ["review"], error_on=0)
    session = SessionContext(id="s")
    task = Task(id="t", description="write", payload={"max_rounds": 5})

    outputs = CriticRefine().run([producer, critic], task, session)

    assert [o.agent for o in outputs] == ["producer", "critic"]
    assert "error" in outputs[-1].metadata
    assert producer.calls == 1


def test_critic_refine_stops_when_producer_draft_errors() -> None:
    producer = ScriptedAgent("producer", ["draft"], error_on=0)
    critic = ScriptedAgent("critic", ["review"])
    session = SessionContext(id="s")
    task = Task(id="t", description="write")

    outputs = CriticRefine().run([producer, critic], task, session)

    assert [o.agent for o in outputs] == ["producer"]
    assert critic.calls == 0


def test_critic_refine_single_agent_degrades() -> None:
    producer = ScriptedAgent("producer", ["only"])
    session = SessionContext(id="s")
    task = Task(id="t", description="write")

    outputs = CriticRefine().run([producer], task, session)

    assert [o.content for o in outputs] == ["only"]
    assert producer.calls == 1


def test_critic_refine_coerces_string_max_rounds() -> None:
    # A string "2" must be coerced to int(2) and behave like 2 rounds.
    producer = ScriptedAgent("producer", ["draft", "rev1", "rev2"])
    critic = ScriptedAgent("critic", ["needs work", "still", "more"])
    session = SessionContext(id="s")
    task = Task(id="t", description="write", payload={"max_rounds": "2"})

    outputs = CriticRefine().run([producer, critic], task, session)

    # Identical shape to the int max_rounds=2 case: draft + (critic, revision) * 2.
    assert [o.agent for o in outputs] == [
        "producer",
        "critic",
        "producer",
        "critic",
        "producer",
    ]
    assert producer.calls == 3
    assert critic.calls == 2


def test_critic_refine_garbage_max_rounds_falls_back_to_default() -> None:
    # A non-numeric string must not raise; it falls back to the default of 3.
    producer = ScriptedAgent("producer", ["draft", "r1", "r2", "r3"])
    critic = ScriptedAgent("critic", ["c0", "c1", "c2"])
    session = SessionContext(id="s")
    task = Task(id="t", description="write", payload={"max_rounds": "abc"})

    outputs = CriticRefine().run([producer, critic], task, session)

    # default 3 rounds: draft + (critic, revision) * 3 == 7 outputs.
    assert [o.agent for o in outputs] == [
        "producer",
        "critic",
        "producer",
        "critic",
        "producer",
        "critic",
        "producer",
    ]
    assert critic.calls == 3
    assert producer.calls == 4


def test_critic_refine_no_agents_returns_empty() -> None:
    session = SessionContext(id="s")
    task = Task(id="t", description="write")

    outputs = CriticRefine().run([], task, session)

    assert outputs == []

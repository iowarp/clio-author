"""Hermetic M0 harness tests (EchoLLMClient, no network)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from clio_author import ClioAuthorAgent
from clio_author.harness.base import BaseAgent
from clio_author.harness.patterns import Sequential
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.llm.client import EchoLLMClient


def test_clio_author_agent_invoke() -> None:
    output = ClioAuthorAgent().invoke("hello world")
    assert isinstance(output, AgentOutput)
    assert output.agent == "echo"
    assert "hello world" in output.content


def test_base_agent_produces_output() -> None:
    agent = BaseAgent(role="tester", system_prompt="be helpful", llm=EchoLLMClient())
    session = SessionContext(id="s1")
    output = agent.run(Task(id="t1", description="ping"), session)
    assert isinstance(output, AgentOutput)
    assert output.agent == "tester"
    assert "ping" in output.content
    assert len(session.history) == 1


def test_sequential_runs_agents_in_order() -> None:
    llm = EchoLLMClient()
    first = BaseAgent(role="first", system_prompt="sp", llm=llm)
    second = BaseAgent(role="second", system_prompt="sp", llm=llm)
    session = SessionContext(id="s2")

    outputs = Sequential().run([first, second], Task(id="t2", description="go"), session)

    assert [o.agent for o in outputs] == ["first", "second"]
    assert len(session.history) == 2
    assert [o.agent for o in session.history] == ["first", "second"]


def test_sequential_threads_shared_session() -> None:
    """A later agent sees the prior agent's output already in session.history."""

    class RecordingAgent:
        """Tiny AgentProtocol impl that records the history it observes on run."""

        def __init__(self, role: str) -> None:
            self.role = role
            self.observed: list[str] = []

        @property
        def name(self) -> str:
            return self.role

        def run(self, task: Task, session: SessionContext) -> AgentOutput:
            self.observed = [o.agent for o in session.history]
            output = AgentOutput(agent=self.name, content=task.description)
            session.add(output)
            return output

    first = RecordingAgent("first")
    second = RecordingAgent("second")
    session = SessionContext(id="s3")

    Sequential().run([first, second], Task(id="t3", description="go"), session)

    # The first agent ran against an empty history.
    assert first.observed == []
    # The second agent observed the first agent's output already in the session.
    assert second.observed == ["first"]


def test_invalid_role_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        Message(role="not-a-role", content="x")  # type: ignore[arg-type]

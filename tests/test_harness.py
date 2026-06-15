"""Hermetic M0 harness tests (EchoLLMClient, no network)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from clio_parser import ClioParserAgent
from clio_parser.harness.base import BaseAgent
from clio_parser.harness.patterns import Sequential
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Message, Task
from clio_parser.llm.client import EchoLLMClient


def test_clio_parser_agent_invoke() -> None:
    output = ClioParserAgent().invoke("hello world")
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


def test_invalid_role_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        Message(role="not-a-role", content="x")  # type: ignore[arg-type]

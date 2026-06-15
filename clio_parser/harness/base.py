"""Base class for expert subagents.

:class:`BaseAgent` provides the common shape (role, system prompt, LLM client)
and a default :meth:`run` that builds a system+user conversation, calls the LLM,
and records the result on the session. Re-implemented from scratch (the protoneo
``BaseAgent`` concept is AGPL and is not copied).
"""

from __future__ import annotations

from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Message, Task
from clio_parser.llm.client import LLMClient


class BaseAgent:
    """A minimal expert agent implementing :class:`AgentProtocol`."""

    def __init__(self, role: str, system_prompt: str, llm: LLMClient) -> None:
        self.role = role
        self.system_prompt = system_prompt
        self.llm = llm

    @property
    def name(self) -> str:
        """The agent's role identifier."""
        return self.role

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Run the task through the LLM and append the output to the session."""
        messages = [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content=task.description),
        ]
        content = self.llm.complete(messages)
        output = AgentOutput(agent=self.name, content=content)
        session.add(output)
        return output

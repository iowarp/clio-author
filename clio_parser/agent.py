"""The main agent and entry surface for clio-parser.

:class:`ClioParserAgent` is the object the CLIO agent (and tests) invoke. For
M0 it wires a single :class:`EchoExpert` through the :class:`Engine` using the
:class:`Sequential` pattern. Later milestones add planning, real experts, and
critic-refine orchestration (see ``artifact/notes/DESIGN.md`` §5).
"""

from __future__ import annotations

from uuid import uuid4

from clio_parser.experts.echo import EchoExpert
from clio_parser.harness.engine import Engine
from clio_parser.harness.patterns import Sequential
from clio_parser.harness.types import AgentOutput, Task
from clio_parser.llm.client import EchoLLMClient, LLMClient


class ClioParserAgent:
    """Main orchestrator agent and primary entry point."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm: LLMClient = llm if llm is not None else EchoLLMClient()
        self.echo_expert = EchoExpert(self.llm)
        self.engine = Engine()
        self.pattern = Sequential()

    def invoke(self, task: str) -> AgentOutput:
        """Run ``task`` through the harness and return the final output."""
        task_obj = Task(id=uuid4().hex, description=task)
        outputs = self.engine.run([self.echo_expert], self.pattern, task_obj)
        return outputs[-1]

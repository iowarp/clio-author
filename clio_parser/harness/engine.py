"""The orchestration engine.

The :class:`Engine` is intentionally thin: it provisions a
:class:`SessionContext` and delegates execution to a :class:`Pattern`. The
main agent (see :mod:`clio_parser.agent`) owns planning and pattern selection.
"""

from __future__ import annotations

from uuid import uuid4

from clio_parser.harness.patterns import Pattern
from clio_parser.harness.protocol import AgentProtocol
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Task


class Engine:
    """Runs a pattern over a set of agents within a session."""

    def run(
        self,
        agents: list[AgentProtocol],
        pattern: Pattern,
        task: Task,
        session: SessionContext | None = None,
    ) -> list[AgentOutput]:
        """Execute ``pattern`` over ``agents`` for ``task``.

        A fresh :class:`SessionContext` is created when one is not supplied.
        """
        if session is None:
            session = SessionContext(id=uuid4().hex)
        return pattern.run(agents, task, session)

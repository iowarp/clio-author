"""Orchestration patterns for running expert subagents.

A :class:`Pattern` defines *how* a set of agents are run against a task and how
their outputs thread through the shared session. M0 ships :class:`Sequential`;
the remaining patterns are documented stubs for later milestones (see
``artifact/notes/DESIGN.md`` §1).
"""

from __future__ import annotations

from clio_parser.harness.protocol import AgentProtocol
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Task


class Pattern:
    """Base orchestration pattern."""

    def run(
        self,
        agents: list[AgentProtocol],
        task: Task,
        session: SessionContext,
    ) -> list[AgentOutput]:
        """Run ``agents`` against ``task`` and return their outputs."""
        raise NotImplementedError


class Sequential(Pattern):
    """Run agents one after another, each appended to the session in order.

    Each agent receives the same task and the same shared
    :class:`~clio_parser.harness.session.SessionContext`, which is threaded
    through every agent. Because the session grows as agents run, a later agent
    *may* read earlier agents' outputs from ``session.history``. No M0 expert
    does so yet (:meth:`BaseAgent.run` ignores ``session.history``); the wiring
    is in place for later milestones.
    """

    def run(
        self,
        agents: list[AgentProtocol],
        task: Task,
        session: SessionContext,
    ) -> list[AgentOutput]:
        outputs: list[AgentOutput] = []
        for agent in agents:
            outputs.append(agent.run(task, session))
        return outputs


class Parallel(Pattern):
    """Run agents concurrently on the same task and collect all outputs.

    Planned: dispatch each agent independently (async/threaded once the LLM
    client gains an async path), preserving input order in the returned list,
    then append all outputs to the session.
    """

    def run(
        self,
        agents: list[AgentProtocol],
        task: Task,
        session: SessionContext,
    ) -> list[AgentOutput]:
        raise NotImplementedError("planned for a later milestone")


class RoundRobin(Pattern):
    """Cycle through agents for a fixed number of turns.

    Planned: iterate over agents in rounds, threading each turn's output back
    into the session as context for the next agent, until a turn budget or
    convergence condition is met.
    """

    def run(
        self,
        agents: list[AgentProtocol],
        task: Task,
        session: SessionContext,
    ) -> list[AgentOutput]:
        raise NotImplementedError("planned for a later milestone")


class CriticRefine(Pattern):
    """Generator/critic refinement loop (independent synthesis).

    Planned: a primary agent drafts, one or more critic agents review against a
    rubric, and the draft is revised until quality passes or a max-iteration
    budget is reached. Mirrors the PaperBanana/papervizagent critic-refine loop
    (Apache-2.0; adapted, not copied).
    """

    def run(
        self,
        agents: list[AgentProtocol],
        task: Task,
        session: SessionContext,
    ) -> list[AgentOutput]:
        raise NotImplementedError("planned for a later milestone")

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

NO_CHANGES_SENTINEL = "No changes needed."
"""Critic sentinel signalling the current draft needs no further revision."""


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
    """Run agents on the same task and collect outputs in input order.

    Every agent receives the *same* task and the same shared
    :class:`~clio_parser.harness.session.SessionContext`. Outputs are collected
    in the order the agents were supplied, regardless of when they would
    complete under true concurrency.

    Execution is **sequential-collect**, not threaded: the :class:`LLMClient`
    protocol is synchronous and ``SessionContext`` is unlocked, so a thread pool
    would only add contention without a thread-safe client. A threaded dispatch
    path awaits a thread-safe / async ``LLMClient`` (and likely per-agent child
    sessions for true blind isolation); the public contract -- input-order
    results, single ``session.add`` per agent -- is designed to survive that
    change.

    Like :class:`Sequential`, this pattern does **not** add outputs to the
    session itself: each agent owns its own :meth:`session.add`, so every output
    is appended exactly once.
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


class RoundRobin(Pattern):
    """Cycle through agents for a fixed number of turns (protoneo round-robin).

    Agents take turns across ``task.payload["rounds"]`` (default ``1``) rounds:
    in each round every agent runs once, in input order. Each turn's output is
    appended to the shared :class:`~clio_parser.harness.session.SessionContext`
    (each agent owns its own :meth:`session.add`, exactly once), so a later agent
    -- in the same round or a subsequent one -- can read every prior turn from
    ``session.history``. This is the same session-threading discipline as
    :class:`Sequential` / :class:`Parallel`.

    Returns the **full ordered list** of outputs across all turns; its length is
    ``len(agents) * rounds``. With no agents the result is empty. Never raises;
    ``rounds`` is coerced defensively (mirroring :class:`CriticRefine`'s
    ``max_rounds`` handling) and clamped to ``>= 0``. Re-implemented from scratch
    from protoneo's round-robin deliberation concept (AGPL-3.0; no code copied).
    """

    def run(
        self,
        agents: list[AgentProtocol],
        task: Task,
        session: SessionContext,
    ) -> list[AgentOutput]:
        outputs: list[AgentOutput] = []
        if not agents:
            return outputs

        try:
            rounds = int(task.payload.get("rounds", 1))
        except (TypeError, ValueError):
            rounds = 1
        rounds = max(0, rounds)

        for _ in range(rounds):
            for agent in agents:
                outputs.append(agent.run(task, session))
        return outputs


class CriticRefine(Pattern):
    """Producer/critic refinement loop (independent synthesis).

    ``agents[0]`` is the *producer*; ``agents[1]`` is the *critic*. The producer
    drafts once, then for up to ``task.payload["max_rounds"]`` (default ``3``)
    rounds the critic reviews the current draft and the producer revises in
    response. State is threaded through ``session.data``:

    * ``session.data["draft"]`` -- the producer's latest ``content``.
    * ``session.data["critic_feedback"]`` -- the critic's latest ``content``.

    A round short-circuits when the critic's ``content.strip()`` equals
    :data:`NO_CHANGES_SENTINEL`. The loop also stops as soon as any output is
    error-flagged (``metadata["error"]`` present), so a degraded agent does not
    spin the budget. With fewer than two agents the single agent runs once.

    Returns the **full ordered history** of this run's outputs
    (``list[AgentOutput]``); the final element is the last output produced. Never
    raises -- agents are expected to flag failures on their output. Mirrors the
    PaperBanana/papervizagent critic-refine loop (Apache-2.0; adapted, not
    copied).
    """

    def run(
        self,
        agents: list[AgentProtocol],
        task: Task,
        session: SessionContext,
    ) -> list[AgentOutput]:
        outputs: list[AgentOutput] = []
        if not agents:
            return outputs

        if len(agents) < 2:
            outputs.append(agents[0].run(task, session))
            return outputs

        producer, critic = agents[0], agents[1]
        try:
            max_rounds = int(task.payload.get("max_rounds", 3))
        except (TypeError, ValueError):
            max_rounds = 3
        max_rounds = max(0, max_rounds)

        draft = producer.run(task, session)
        outputs.append(draft)
        if _is_error(draft):
            return outputs
        session.data["draft"] = draft.content

        for _ in range(max_rounds):
            review = critic.run(task, session)
            outputs.append(review)
            if _is_error(review):
                break
            session.data["critic_feedback"] = review.content
            if review.content.strip() == NO_CHANGES_SENTINEL:
                break

            revision = producer.run(task, session)
            outputs.append(revision)
            if _is_error(revision):
                break
            session.data["draft"] = revision.content

        return outputs


def _is_error(output: AgentOutput) -> bool:
    """True when ``output`` carries an ``error`` flag in its metadata."""
    return "error" in output.metadata

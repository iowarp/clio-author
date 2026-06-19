"""Hermetic tests for :func:`clio_author.experts.orchestrate.run_orchestrate`.

A canned planner LLM returns a fixed plan; ``execute`` is either a recording fake
or a thin wrapper over a real :class:`ClioAuthorAgent` so the steps run through the
existing router. The default :class:`EchoLLMClient` planner does not parse, which
exercises the "could not plan" error path. No network.
"""

from __future__ import annotations

import json
from typing import Any

from clio_author.agent import ClioAuthorAgent
from clio_author.experts.orchestrate import run_orchestrate
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.integration.manifest import ACTIONS
from clio_author.llm.client import EchoLLMClient
from clio_author.tools.files import SafeFiles


class CannedLLMClient:
    """Returns a fixed string regardless of the prompt."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        return self._response


def _plan_json(plan: list[dict[str, Any]]) -> str:
    return "```json\n" + json.dumps({"plan": plan}) + "\n```"


def _task(**payload: Any) -> Task:
    return Task(id="t", description="orchestrate", payload=dict(payload))


def _session() -> SessionContext:
    return SessionContext(id="s")


class _Recorder:
    """A fake ``execute`` that records calls and returns scripted outputs."""

    def __init__(self, outputs: dict[str, AgentOutput] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._outputs = outputs or {}

    def __call__(self, action: str, payload: dict[str, Any]) -> AgentOutput:
        self.calls.append((action, payload))
        if action in self._outputs:
            return self._outputs[action]
        return AgentOutput(agent=action, content=f"ran {action}", structured={"action": action})


def test_runs_planned_steps_in_order() -> None:
    plan = [
        {"action": "ask", "payload": {"question": "q1"}},
        {"action": "meta_review", "payload": {"reviews": []}},
    ]
    rec = _Recorder()
    out = run_orchestrate(
        _task(goal="answer then aggregate"),
        execute=rec,
        manifest=ACTIONS,
        llm=CannedLLMClient(_plan_json(plan)),
        session=_session(),
    )

    assert out.agent == "orchestrate"
    assert [a for a, _ in rec.calls] == ["ask", "meta_review"]
    assert out.metadata["num_steps"] == 2
    assert out.metadata["actions"] == ["ask", "meta_review"]
    assert out.metadata["errors"] == []
    assert len(out.structured["steps"]) == 2
    assert out.structured["steps"][0] == {
        "action": "ask",
        "ok": True,
        "summary": "ran ask",
        "error": None,
    }
    assert out.structured["goal"] == "answer then aggregate"
    assert out.structured["plan"] == plan


def test_reference_resolution_from_inputs_and_prior_step() -> None:
    plan = [
        {"action": "ingest", "payload": {"source": "@source"}, "save_as": "ing"},
        {"action": "ask", "payload": {"question": "what?", "blocks": "@ing"}},
    ]
    rec = _Recorder(
        {"ingest": AgentOutput(agent="ingest", content="paper md", structured={"blocks": 1})}
    )
    out = run_orchestrate(
        _task(goal="g", inputs={"source": "2601.0001"}),
        execute=rec,
        manifest=ACTIONS,
        llm=CannedLLMClient(_plan_json(plan)),
        session=_session(),
    )

    # @source resolved from inputs.
    assert rec.calls[0] == ("ingest", {"source": "2601.0001"})
    # @ing resolved from the prior step's save_as -> structured output.
    assert rec.calls[1] == ("ask", {"question": "what?", "blocks": {"blocks": 1}})
    assert out.metadata["num_steps"] == 2
    assert "ing" in out.structured["context_keys"]


def test_unknown_action_is_dropped() -> None:
    plan = [
        {"action": "nope", "payload": {}},
        {"action": "ask", "payload": {"question": "q"}},
    ]
    rec = _Recorder()
    out = run_orchestrate(
        _task(goal="g"),
        execute=rec,
        manifest=ACTIONS,
        llm=CannedLLMClient(_plan_json(plan)),
        session=_session(),
    )

    assert [a for a, _ in rec.calls] == ["ask"]
    assert out.metadata["num_steps"] == 1
    assert [s["action"] for s in out.structured["plan"]] == ["ask"]


def test_echo_planner_cannot_plan() -> None:
    rec = _Recorder()
    out = run_orchestrate(
        _task(goal="do something"),
        execute=rec,
        manifest=ACTIONS,
        llm=EchoLLMClient(),
        session=_session(),
    )

    assert out.metadata["error"] == "could not plan for goal"
    assert rec.calls == []


def test_missing_goal_errors() -> None:
    out = run_orchestrate(
        _task(),
        execute=_Recorder(),
        manifest=ACTIONS,
        llm=CannedLLMClient(_plan_json([{"action": "ask", "payload": {}}])),
        session=_session(),
    )
    assert "error" in out.metadata


def test_failing_step_recorded_and_continues() -> None:
    plan = [
        {"action": "ask", "payload": {"question": "q"}},
        {"action": "review", "payload": {"paper": "p"}},
    ]
    rec = _Recorder(
        {
            "ask": AgentOutput(agent="ask", content="", metadata={"error": "boom"}),
        }
    )
    out = run_orchestrate(
        _task(goal="g"),
        execute=rec,
        manifest=ACTIONS,
        llm=CannedLLMClient(_plan_json(plan)),
        session=_session(),
    )

    # Both steps ran even though the first errored.
    assert [a for a, _ in rec.calls] == ["ask", "review"]
    assert out.metadata["errors"] == ["ask"]
    assert out.metadata["num_steps"] == 2
    assert out.structured["steps"][0]["ok"] is False
    assert out.structured["steps"][0]["error"] == "boom"
    assert "ERROR" in out.content


def test_max_steps_caps_execution() -> None:
    plan = [{"action": "ask", "payload": {"question": f"q{i}"}} for i in range(5)]
    rec = _Recorder()
    out = run_orchestrate(
        _task(goal="g", max_steps=2),
        execute=rec,
        manifest=ACTIONS,
        llm=CannedLLMClient(_plan_json(plan)),
        session=_session(),
    )
    assert out.metadata["num_steps"] == 2
    assert len(rec.calls) == 2


def test_out_dir_writes_orchestrate_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    plan = [{"action": "ask", "payload": {"question": "q"}}]
    out = run_orchestrate(
        _task(goal="g", out_dir=str(tmp_path)),
        execute=_Recorder(),
        manifest=ACTIONS,
        llm=CannedLLMClient(_plan_json(plan)),
        session=_session(),
    )
    written = out.metadata["wrote"]
    assert len(written) == 1
    path = tmp_path / "orchestrate.json"
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["goal"] == "g"
    assert str(path) in written


def test_out_dir_subdir_under_injected_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    files = SafeFiles(tmp_path)
    plan = [{"action": "ask", "payload": {"question": "q"}}]
    run_orchestrate(
        _task(goal="g", out_dir="run1"),
        execute=_Recorder(),
        manifest=ACTIONS,
        llm=CannedLLMClient(_plan_json(plan)),
        files=files,
        session=_session(),
    )
    assert (tmp_path / "run1" / "orchestrate.json").exists()


def test_via_real_agent_router() -> None:
    """The agent's _execute_step wrapper runs each action through _route."""
    plan = [
        {"action": "ask", "payload": {"question": "what is x?"}},
    ]
    agent = ClioAuthorAgent(CannedLLMClient(_plan_json(plan)))
    out = agent.invoke(_task(goal="answer x", action="orchestrate"))
    assert out.agent == "orchestrate"
    assert out.metadata["num_steps"] == 1
    assert out.metadata["actions"] == ["ask"]


def test_orchestrate_cannot_recurse() -> None:
    """A plan that tries to call orchestrate is dropped (not in the planner menu)."""
    agent = ClioAuthorAgent()
    # Directly probe the wrapper: orchestrate is refused.
    refused = agent._execute_step("orchestrate", {"goal": "loop"})
    assert refused.metadata["error"] == "orchestrate cannot call itself"


def test_structured_is_json_serializable() -> None:
    plan = [{"action": "ask", "payload": {"question": "q"}}]
    out = run_orchestrate(
        _task(goal="g"),
        execute=_Recorder(),
        manifest=ACTIONS,
        llm=CannedLLMClient(_plan_json(plan)),
        session=_session(),
    )
    json.dumps({"structured": out.structured, "metadata": out.metadata})

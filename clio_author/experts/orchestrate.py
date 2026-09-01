"""The dynamic orchestrator: plan an action sequence for a goal, then run it.

:func:`run_orchestrate` is the ``orchestrate`` action. Given a natural-language
``goal`` and the capability manifest (the list of available actions and their
payload keys), it asks the LLM for a *minimal ordered plan* of action calls, then
executes that plan through the agent's existing router -- one action per step,
threading a small ``context`` dict so a later step can reference an earlier
step's output via an ``"@name"`` reference.

The orchestrator never does the work itself; it only chooses actions and their
payloads. Execution is delegated through an ``execute`` callable supplied by the
caller (a thin wrapper around :meth:`ClioAuthorAgent._route`), so this module
imports **no** experts and cannot recurse into ``orchestrate``.

Like the other composition helpers (:mod:`clio_author.experts.compose`), this is
a plain helper, not a :class:`~clio_author.harness.base.BaseAgent`, and it never
raises: a missing/unparseable plan or any unexpected failure becomes an
error-flagged :class:`AgentOutput`. A failing step is recorded and execution
continues to the next step. With the default
:class:`~clio_author.llm.client.EchoLLMClient` the planner response will not
parse, so the offline path exercises the "could not plan" branch.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clio_author.experts.reviewer import _extract_json_object
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.llm.client import LLMClient
from clio_author.tools.files import SafeFiles, wants_overwrite, write_artifacts

ORCHESTRATE_SYSTEM_PROMPT = (
    "You are the orchestrator. Given a goal and the available actions, output a "
    "MINIMAL ordered plan of action calls as JSON. Do not do the work yourself; "
    "only choose actions and their payloads."
)

_DEFAULT_MAX_STEPS = 6

# A callable that runs ONE routed action and returns its output. The agent passes
# a wrapper around its own single-action router so the orchestrator can invoke any
# existing action without importing experts (and without recursing into orchestrate).
ExecuteFn = Callable[[str, dict[str, Any]], AgentOutput]


def run_orchestrate(
    task: Task,
    *,
    execute: ExecuteFn,
    manifest: list[dict[str, Any]],
    llm: LLMClient,
    files: SafeFiles | None = None,
    session: SessionContext | None = None,
) -> AgentOutput:
    """Plan and run an action sequence to achieve ``task.payload["goal"]``.

    Reads ``goal`` (required), ``inputs`` (optional dict of named values seeding
    the execution context, e.g. ``{"source": "2601.23265"}``), ``max_steps``
    (int, default 6), and ``out_dir`` (optional). Asks ``llm`` once for an ordered
    plan over the actions in ``manifest``, drops steps whose action is unknown,
    then runs each remaining step (capped at ``max_steps``) through ``execute``,
    resolving ``"@name"`` references in the payload from the running context.

    Returns one :class:`AgentOutput` (``agent="orchestrate"``). Error-flags the
    whole output only when no plan could be produced. Never raises.
    """
    try:
        return _run_orchestrate(
            task,
            execute=execute,
            manifest=manifest,
            llm=llm,
            files=files,
            session=session,
        )
    except Exception as exc:  # noqa: BLE001 - never raise; flag error on the output
        out = AgentOutput(agent="orchestrate", content="", metadata={"error": str(exc)})
        if session is not None:
            session.add(out)
        return out


def _run_orchestrate(
    task: Task,
    *,
    execute: ExecuteFn,
    manifest: list[dict[str, Any]],
    llm: LLMClient,
    files: SafeFiles | None,
    session: SessionContext | None,
) -> AgentOutput:
    payload = task.payload
    goal = str(payload.get("goal") or "").strip()
    if not goal:
        return _error(session, "no 'goal' provided in task.payload")

    inputs = payload.get("inputs")
    inputs = dict(inputs) if isinstance(inputs, dict) else {}
    max_steps = int(payload.get("max_steps", _DEFAULT_MAX_STEPS))
    out_dir = payload.get("out_dir")

    known = {str(entry.get("action")) for entry in manifest}

    # --- Plan --------------------------------------------------------------- #
    plan = _plan(goal, inputs, manifest, llm)
    # Drop steps whose action is not in the manifest (or is not well-formed).
    plan = [step for step in plan if isinstance(step, dict) and step.get("action") in known]
    if not plan:
        return _error(session, "could not plan for goal")

    # --- Execute ------------------------------------------------------------ #
    context: dict[str, Any] = dict(inputs)
    steps: list[dict[str, Any]] = []
    for step in plan[:max_steps]:
        action = str(step["action"])
        raw_payload = step.get("payload")
        resolved = _resolve_refs(raw_payload if isinstance(raw_payload, dict) else {}, context)
        out = execute(action, resolved)

        error = (out.metadata or {}).get("error")
        steps.append(
            {
                "action": action,
                "ok": error is None,
                "summary": (out.content or "")[:200],
                "error": error,
            }
        )

        # Update the running context for downstream @references.
        value = out.structured if out.structured is not None else out.content
        save_as = step.get("save_as")
        context[str(save_as) if save_as else action] = value
        # Convenience keys so a plan can reference an ingest result naturally.
        if action == "ingest":
            context["paper"] = out.content
            context["blocks"] = out.structured

    errors = [s["action"] for s in steps if not s["ok"]]
    structured: dict[str, Any] = {
        "goal": goal,
        "plan": plan,
        "steps": steps,
        "context_keys": sorted(context),
    }
    metadata: dict[str, Any] = {
        "num_steps": len(steps),
        "actions": [s["action"] for s in steps],
        "errors": errors,
    }

    wrote, write_skipped = _maybe_write(
        out_dir, files, structured, overwrite=wants_overwrite(payload)
    )
    if wrote:
        metadata["wrote"] = wrote
    if write_skipped:
        metadata["write_skipped"] = write_skipped

    out = AgentOutput(
        agent="orchestrate",
        content=_summary(goal, steps),
        structured=structured,
        metadata=metadata,
    )
    if session is not None:
        session.add(out)
    return out


def _plan(
    goal: str,
    inputs: dict[str, Any],
    manifest: list[dict[str, Any]],
    llm: LLMClient,
) -> list[dict[str, Any]]:
    """Ask the LLM once for an ordered plan; return the parsed step list (maybe empty)."""
    user = "\n\n".join(
        part
        for part in (
            f"GOAL:\n{goal}",
            "AVAILABLE ACTIONS:\n" + _render_manifest(manifest),
            _render_inputs(inputs),
            _PLAN_INSTRUCTIONS,
        )
        if part
    )
    messages = [
        Message(role="system", content=ORCHESTRATE_SYSTEM_PROMPT),
        Message(role="user", content=user),
    ]
    parsed = _extract_json_object(llm.complete(messages))
    if parsed is None:
        return []
    plan = parsed.get("plan")
    if not isinstance(plan, list):
        return []
    return [step for step in plan if isinstance(step, dict)]


_PLAN_INSTRUCTIONS = (
    "Respond with a fenced JSON block and nothing else:\n"
    "```json\n"
    '{"plan": [{"action": "<name from the available actions>", '
    '"payload": {<keys for that action>}, "save_as": "<optional name>"}]}\n'
    "```\n"
    "Use only action names listed above. Keep the plan minimal. To pass an "
    "earlier step's output (or a provided input) into a later payload, use the "
    'string "@name" as the value -- e.g. "blocks": "@ingest" or "source": '
    '"@source". The JSON is parsed automatically.'
)


def _render_manifest(manifest: list[dict[str, Any]]) -> str:
    """One compact line per action: ``name — description — payload_keys``."""
    lines: list[str] = []
    for entry in manifest:
        name = entry.get("action")
        if name == "orchestrate":
            # The orchestrator must not plan to call itself.
            continue
        desc = entry.get("description", "")
        keys = ", ".join(entry.get("payload_keys", []))
        lines.append(f"{name} — {desc} — payload_keys: [{keys}]")
    return "\n".join(lines)


def _render_inputs(inputs: dict[str, Any]) -> str:
    """Describe the provided named inputs (names + keys) for the planner, or ''."""
    if not inputs:
        return ""
    names = ", ".join(sorted(inputs))
    return f"PROVIDED INPUTS (reference with @name): {names}"


def _resolve_refs(value: Any, context: dict[str, Any]) -> Any:
    """Recursively replace any ``"@name"`` string with ``context["name"]``.

    A string of exactly the form ``"@name"`` whose ``name`` is present in the
    context is substituted by that value; every other string (and any non-string
    leaf) is left untouched. Dicts and lists are recursed into.
    """
    if isinstance(value, str):
        if value.startswith("@") and len(value) > 1:
            name = value[1:]
            if name in context:
                return context[name]
        return value
    if isinstance(value, dict):
        return {key: _resolve_refs(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(item, context) for item in value]
    return value


def _summary(goal: str, steps: list[dict[str, Any]]) -> str:
    """Render a readable summary: the goal, then a numbered line per step."""
    lines = [f"Goal: {goal}"]
    for index, step in enumerate(steps, start=1):
        status = "ok" if step["ok"] else "ERROR"
        lines.append(f"{index}. {step['action']} → {status}: {step['summary']}")
    return "\n".join(lines)


def _maybe_write(
    out_dir: Any,
    files: SafeFiles | None,
    structured: dict[str, Any],
    *,
    overwrite: bool = False,
) -> tuple[list[str], list[str]]:
    """Persist ``orchestrate.json`` under ``out_dir`` when given (mirrors kg).

    When a :class:`SafeFiles` was injected, ``out_dir`` is a subdirectory under
    its sandbox root; otherwise ``out_dir`` is taken as the output root directly
    (the CLI/adapter path). Best-effort/never-raise: the folder is minted once and
    a refused or failed write is skipped.
    """
    if not out_dir:
        return [], []

    if files is not None:
        prefix = f"{out_dir}/"
    else:
        files = SafeFiles(Path(str(out_dir)))
        prefix = ""

    try:
        (files.root / prefix).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return [], [f"{out_dir}: {exc}"]

    return write_artifacts(
        files,
        ((f"{prefix}orchestrate.json", json.dumps(structured, indent=2)),),
        overwrite=overwrite,
    )


def _error(session: SessionContext | None, message: str) -> AgentOutput:
    """Build (and record) an error-flagged orchestrate output."""
    out = AgentOutput(agent="orchestrate", content="", metadata={"error": message})
    if session is not None:
        session.add(out)
    return out


__all__ = ["run_orchestrate"]

"""Hermetic tests for :class:`ClioAuthorSubagent`.

The adapter must expose a discovery manifest covering every routed action and a
``run`` method whose result always round-trips through ``json.dumps`` -- for a
happy action, an error action, and a defensive bad-input case -- without ever
raising.
"""

from __future__ import annotations

import json

from clio_author.integration import ClioAuthorSubagent

_ROUTED_ACTIONS = {
    "ingest",
    "ask",
    "review",
    "meta_review",
    "cite",
    "write",
    "compose",
    "edit",
    "describe_figures",
    "plot",
    "write_review",
    "figure_refine",
    "export",
    "polish",
    "coherence",
    "kg",
}


def test_capabilities_shape_lists_all_actions() -> None:
    caps = ClioAuthorSubagent().capabilities()
    assert caps["name"] == "clio-author"
    assert isinstance(caps["version"], str) and caps["version"]
    actions = {entry["action"] for entry in caps["actions"]}
    assert actions == _ROUTED_ACTIONS
    assert {"polish", "coherence", "kg"} <= actions
    assert len(caps["actions"]) == 16
    for entry in caps["actions"]:
        assert {"action", "description", "payload_keys"} <= entry.keys()
        assert isinstance(entry["payload_keys"], list)
    # The manifest is JSON-serializable.
    json.dumps(caps)


def test_run_happy_action_is_json_serializable() -> None:
    result = ClioAuthorSubagent().run("review", {"paper": "# Paper\nSome content."})
    assert result["action"] == "review"
    assert set(result) == {"action", "content", "structured", "metadata"}
    # Round-trips cleanly through json.
    assert json.loads(json.dumps(result)) == result


def test_run_error_action_is_json_serializable_and_no_raise() -> None:
    # Missing required inputs -> the expert flags an error rather than raising.
    result = ClioAuthorSubagent().run("cite", {})
    assert result["action"] == "cite"
    assert "error" in result["metadata"]
    json.dumps(result)


def test_run_unknown_action_falls_through_to_echo() -> None:
    result = ClioAuthorSubagent().run("totally-unknown", {"foo": "bar"})
    assert result["action"] == "totally-unknown"
    assert result["metadata"].get("agent", None) is None  # echo output has no error
    json.dumps(result)


def test_run_none_payload_does_not_raise() -> None:
    result = ClioAuthorSubagent().run("ingest", None)
    assert result["action"] == "ingest"
    json.dumps(result)

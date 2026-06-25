"""Hermetic tests for the A2A agent card + JSON-RPC handler (no sockets)."""

from __future__ import annotations

import json

from clio_author.integration.a2a_card import build_agent_card
from clio_author.integration.a2a_server import handle_jsonrpc
from clio_author.integration.manifest import ACTIONS
from clio_author.roles import ROLE_CLASSES


def test_card_has_one_skill_per_tool_and_role() -> None:
    card = build_agent_card()
    skill_ids = {s["id"] for s in card["skills"]}
    # every tool action is a skill
    for a in ACTIONS:
        assert a["action"] in skill_ids
    # every role is a `role:<name>` skill
    for r in ROLE_CLASSES:
        assert f"role:{r.name}" in skill_ids
    assert len(card["skills"]) == len(ACTIONS) + len(ROLE_CLASSES)
    assert card["name"] == "clio-author"
    json.dumps(card)  # serializable


def test_message_send_runs_a_tool() -> None:
    req = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
            "skillId": "cite_support",
            "payload": {
                "text": "A claim \\cite{k}.",
                "citations": [{"citation_key": "k", "record": {"abstract": "some abstract"}}],
            },
        },
    }
    resp = handle_jsonrpc(req)
    assert resp["id"] == "1"
    task = resp["result"]
    assert task["status"]["state"] == "completed"
    # the structured result rides in a data part
    kinds = {p["kind"] for p in task["artifacts"][0]["parts"]}
    assert "data" in kinds


def test_message_send_runs_a_role() -> None:
    req = {
        "jsonrpc": "2.0",
        "id": "2",
        "method": "message/send",
        "params": {
            "skillId": "role:verifier",
            "payload": {"text": "X \\cite{k}.", "bibtex": "@article{k,title={T},year={2020}}"},
        },
    }
    task = handle_jsonrpc(req)["result"]
    assert task["status"]["state"] == "completed"
    assert task["artifacts"][0]["name"] == "role"


def test_domain_error_is_a_failed_task_not_an_exception() -> None:
    req = {
        "jsonrpc": "2.0",
        "id": "3",
        "method": "message/send",
        "params": {"skillId": "cite_support", "payload": {}},  # missing inputs
    }
    task = handle_jsonrpc(req)["result"]
    assert task["status"]["state"] == "failed"


def test_unknown_method_is_jsonrpc_error() -> None:
    resp = handle_jsonrpc({"jsonrpc": "2.0", "id": "4", "method": "tasks/cancel"})
    assert resp["error"]["code"] == -32601


def test_datapart_message_form() -> None:
    req = {
        "jsonrpc": "2.0",
        "id": "5",
        "method": "message/send",
        "params": {
            "message": {
                "parts": [
                    {
                        "kind": "data",
                        "data": {"skillId": "audit", "payload": {"markdown": "## A\n\nx"}},
                    }
                ]
            }
        },
    }
    task = handle_jsonrpc(req)["result"]
    assert task["status"]["state"] == "completed"

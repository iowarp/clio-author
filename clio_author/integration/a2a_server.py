"""A minimal A2A (Agent-to-Agent) server for clio-author.

A thin protocol adapter — like :mod:`clio_author.integration.mcp_bridge`, but
speaking A2A — that lets any A2A host discover and invoke clio-author's tools and
roles over HTTP. It wraps :class:`~clio_author.integration.clio_adapter.ClioAuthorSubagent`;
no expert changes.

- A2A protocol — https://github.com/a2aproject/A2A (Apache-2.0).

The core is :func:`handle_jsonrpc` — a pure, hermetic function mapping a JSON-RPC
request dict to a response dict (testable without sockets). :func:`serve` wraps it
in a stdlib ``http.server`` (no third-party dependency) exposing the Agent Card at
``/.well-known/agent-card.json`` and JSON-RPC at ``/``.

Skill → action mapping: a skill id ``"role:<name>"`` runs the role; any other
skill id runs that tool action. The request carries the payload as
``params.payload`` (or a ``DataPart`` in ``params.message.parts``). A result whose
``metadata.error`` is set becomes a ``failed`` task; otherwise ``completed``.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from clio_author.integration.a2a_card import build_agent_card
from clio_author.integration.clio_adapter import ClioAuthorSubagent

_METHODS_SEND = {"message/send", "tasks/send", "message/stream"}


def _skill_and_payload(params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Resolve ``(action, payload)`` from A2A request ``params``.

    Accepts ``{"skillId": "...", "payload": {...}}`` (the simple form) or a
    ``message`` with a ``DataPart`` (``{"action"/"skillId", "payload"}``). A skill
    id ``"role:<name>"`` maps to the ``role`` action with ``role`` in the payload.
    """
    skill = params.get("skillId") or params.get("skill") or ""
    payload: dict[str, Any] = dict(params.get("payload") or {})

    if not skill:
        message = params.get("message") or {}
        for part in message.get("parts") or []:
            if isinstance(part, dict) and part.get("kind") in (None, "data"):
                data = part.get("data")
                if isinstance(data, dict):
                    skill = str(data.get("skillId") or data.get("action") or skill)
                    if isinstance(data.get("payload"), dict):
                        payload = dict(data["payload"])

    skill = str(skill)
    if skill.startswith("role:"):
        return "role", {**payload, "role": skill.split(":", 1)[1]}
    return skill, payload


def _task_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """Wrap an adapter result dict as a completed/failed A2A Task."""
    meta = result.get("metadata") or {}
    failed = bool(result.get("error") or (isinstance(meta, dict) and meta.get("error")))
    parts: list[dict[str, Any]] = [{"kind": "text", "text": result.get("content") or ""}]
    if result.get("structured") is not None:
        parts.append({"kind": "data", "data": result["structured"]})
    return {
        "id": uuid4().hex,
        "kind": "task",
        "status": {"state": "failed" if failed else "completed"},
        "artifacts": [{"name": result.get("action", "result"), "parts": parts, "metadata": meta}],
    }


def handle_jsonrpc(
    request: dict[str, Any], *, subagent: ClioAuthorSubagent | None = None
) -> dict[str, Any]:
    """Map one JSON-RPC request to its response. Pure and hermetic.

    Supports ``message/send`` (and the ``tasks/send`` / ``message/stream``
    aliases): resolves the skill, runs the action through the adapter, and returns
    the result as a Task artifact. Unknown methods return a JSON-RPC method-not-found
    error. The adapter never raises, so this never throws on a domain error.
    """
    sub = subagent or ClioAuthorSubagent()
    rid = request.get("id")
    method = request.get("method")
    if method in _METHODS_SEND:
        action, payload = _skill_and_payload(request.get("params") or {})
        if not action:
            return _error(rid, -32602, "no skillId/action in params")
        result = sub.run(action, payload)
        return {"jsonrpc": "2.0", "id": rid, "result": _task_from_result(result)}
    return _error(rid, -32601, f"method not found: {method}")


def _error(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:  # pragma: no cover - I/O loop
    """Serve the Agent Card + JSON-RPC over a stdlib HTTP server (no deps)."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    subagent = ClioAuthorSubagent()
    card = build_agent_card(url=f"http://{host}:{port}/")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - stdlib signature
            if self.path.rstrip("/").endswith(".well-known/agent-card.json") or self.path in (
                "/.well-known/agent-card.json",
                "/agent-card.json",
            ):
                self._send(200, card)
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802 - stdlib signature
            length = int(self.headers.get("Content-Length") or 0)
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send(400, _error(None, -32700, "parse error"))
                return
            self._send(200, handle_jsonrpc(request, subagent=subagent))

        def log_message(self, *args: Any) -> None:  # silence default logging
            return

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main() -> None:  # pragma: no cover - entry point
    """Console entry point: ``CLIO_A2A_HOST`` / ``CLIO_A2A_PORT`` configure binding."""
    import os

    serve(
        os.environ.get("CLIO_A2A_HOST", "127.0.0.1"), int(os.environ.get("CLIO_A2A_PORT", "8080"))
    )


__all__ = ["handle_jsonrpc", "build_agent_card", "serve", "main"]

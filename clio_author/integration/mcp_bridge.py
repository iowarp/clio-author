"""Thin MCP bridge so an MCP host (e.g. the CLIO agent) can invoke clio-author.

This is the *integration shim*, not the harness: the clio-author package stays a
plain Python library (NOT an MCP server). This module is an optional, separate
adapter that exposes the existing :class:`ClioAuthorSubagent` over the Model
Context Protocol via FastMCP, so a host whose only external-capability surface is
MCP (CLIO's tool gateway spawns declared MCP servers over stdio) can reach all of
clio-author's actions.

Run it as a stdio MCP server:
    uv run --with fastmcp python -m clio_author.integration.mcp_bridge

Declare it to an MCP host (CLIO ``AGENT.md`` / ``mcp.yaml``):
    mcp_servers:
      clio_author: "uv run --with fastmcp python -m clio_author.integration.mcp_bridge"

It exposes two tools:
  - ``capabilities()`` -> the action manifest
  - ``run(action, payload)`` -> dispatch any clio-author action (JSON in/out)

``fastmcp`` is an optional dependency (the ``mcp`` extra); importing the rest of
clio-author never requires it.
"""

from __future__ import annotations

import json
import os
from typing import Any

from clio_author.env_file import load_env
from clio_author.integration.clio_adapter import ClioAuthorSubagent
from clio_author.llm.providers import resolve_llm
from clio_author.llm.vision import resolve_vision_client
from clio_author.retrieval.rag import resolve_rag_retriever
from clio_author.retrieval.scholar import resolve_scholar_client


def build_subagent() -> ClioAuthorSubagent:
    """Build a subagent configured from the same env vars the CLI reads.

    The host selects models via ``CLIO_LLM``; ``CLIO_SCHOLAR``, ``CLIO_VISION``, and
    ``CLIO_RAG`` select the citation backend, the figure-agent image route, and the
    retriever. A bridge is a separate process launched by the host, so it loads the
    env file itself -- the operator's shell never reaches it -- and a key kept in
    ``.env.local`` would otherwise be invisible to every action that needs one.

    Kept separate from :func:`build_server` so the wiring is testable without
    ``fastmcp`` installed.
    """
    load_env()
    return ClioAuthorSubagent(
        llm=resolve_llm(os.environ.get("CLIO_LLM")),
        scholar_client=resolve_scholar_client(os.environ.get("CLIO_SCHOLAR")),
        vision=resolve_vision_client(os.environ.get("CLIO_VISION")),
        retriever=resolve_rag_retriever(os.environ.get("CLIO_RAG")),
    )


def build_server() -> Any:
    """Build the FastMCP server exposing clio-author (lazy-imports ``fastmcp``)."""
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - only without the extra
        raise RuntimeError(
            "fastmcp is required for the MCP bridge. Run with: "
            "uv run --with fastmcp python -m clio_author.integration.mcp_bridge"
        ) from exc

    subagent = build_subagent()

    server = FastMCP(name="clio-author")

    @server.tool
    def capabilities() -> dict[str, Any]:
        """List the clio-author actions and their payload keys."""
        return subagent.capabilities()

    @server.tool
    def run(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run one clio-author action with a JSON payload; returns its result dict."""
        return subagent.run(action, payload or {})

    return server


def main() -> None:
    """Entry point: serve the bridge.

    Transport is chosen by ``CLIO_MCP_TRANSPORT`` (default ``stdio`` — what a
    gateway like CLIO's spawns per call). Set it to ``http`` to run one
    long-lived server shared across sessions/hosts; ``CLIO_MCP_HOST`` (default
    ``127.0.0.1``) and ``CLIO_MCP_PORT`` (default ``8000``) configure the
    listener. Register an HTTP bridge with, e.g.,
    ``claude mcp add --transport http clioauthor http://127.0.0.1:8000/mcp``.
    """
    server = build_server()
    transport = os.environ.get("CLIO_MCP_TRANSPORT", "stdio").strip().lower()
    if transport in ("http", "streamable-http", "sse"):
        host = os.environ.get("CLIO_MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("CLIO_MCP_PORT", "8000"))
        server.run(transport="http", host=host, port=port)
    else:
        server.run()  # default stdio transport


if __name__ == "__main__":  # pragma: no cover - process entry
    # Allow `python -m clio_author.integration.mcp_bridge --selfcheck` to verify
    # the server builds (and tools register) without needing an MCP client.
    import sys

    if "--selfcheck" in sys.argv:
        srv = build_server()
        print(json.dumps({"ok": True, "server": "clio-author"}))
    else:
        main()

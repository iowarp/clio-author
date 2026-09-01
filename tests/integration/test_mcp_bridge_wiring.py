"""The MCP bridge must configure its subagent the way the CLI does.

The bridge already resolved the llm, scholar, and vision clients, but it never loaded
the env file and never passed a retriever. A host launches the bridge as its own
process, so a key kept in ``.env.local`` was invisible to every action needing one.
"""

from __future__ import annotations

from pathlib import Path

import clio_author.integration.mcp_bridge as bridge
from clio_author.integration.mcp_bridge import build_subagent


def test_build_subagent_resolves_every_client_from_the_environment(monkeypatch) -> None:
    """Every CLIO_* var reaches its resolver, including the retriever."""
    seen: dict[str, object] = {}

    # The bridge binds these at module scope, so patch them where they are used.
    monkeypatch.setattr(bridge, "resolve_llm", lambda spec: seen.setdefault("llm", spec))
    monkeypatch.setattr(
        bridge, "resolve_scholar_client", lambda spec: seen.setdefault("scholar", spec)
    )
    monkeypatch.setattr(
        bridge, "resolve_vision_client", lambda spec: seen.setdefault("vision", spec)
    )
    monkeypatch.setattr(bridge, "resolve_rag_retriever", lambda spec: seen.setdefault("rag", spec))

    monkeypatch.setenv("CLIO_ENV_FILE", str(Path("/nonexistent-env-file")))
    monkeypatch.setenv("CLIO_LLM", "echo")
    monkeypatch.setenv("CLIO_SCHOLAR", "crossref")
    monkeypatch.setenv("CLIO_VISION", "off")
    monkeypatch.setenv("CLIO_RAG", "off")

    build_subagent()

    assert seen == {"llm": "echo", "scholar": "crossref", "vision": "off", "rag": "off"}


def test_build_subagent_loads_the_env_file(monkeypatch, tmp_path: Path) -> None:
    """A bridge process reads .env.local itself; the host never hands it the shell."""
    env_file = tmp_path / "keys.env"
    env_file.write_text("GEMINI_API_KEY=from-the-file\n", encoding="utf-8")

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CLIO_ENV_FILE", str(env_file))
    monkeypatch.setenv("CLIO_LLM", "echo")
    monkeypatch.setenv("CLIO_SCHOLAR", "off")
    monkeypatch.setenv("CLIO_VISION", "off")
    monkeypatch.setenv("CLIO_RAG", "off")

    import os

    build_subagent()

    assert os.environ["GEMINI_API_KEY"] == "from-the-file"


def test_build_subagent_needs_no_fastmcp() -> None:
    """The wiring is separable from the server so it is testable without the extra."""
    assert callable(bridge.build_subagent)

"""The A2A server must configure its subagent the way the CLI does.

Regression for a defect where ``serve()`` built a bare ``ClioAuthorSubagent()``: over
A2A every scholar action failed with ``no scholar client configured`` and every text
action returned an ``[echo]`` placeholder, while the identical CLI call succeeded.
"""

from __future__ import annotations

from pathlib import Path

import clio_author.llm.providers as providers
import clio_author.llm.vision as vision_mod
import clio_author.retrieval.rag as rag_mod
import clio_author.retrieval.scholar as scholar_mod
from clio_author.integration.a2a_server import build_subagent, handle_jsonrpc


def test_build_subagent_resolves_every_client_from_the_environment(monkeypatch) -> None:
    """Each CLIO_* var reaches its resolver, so no client is silently left unset."""
    seen: dict[str, object] = {}

    monkeypatch.setattr(providers, "resolve_llm", lambda spec: seen.setdefault("llm", spec))
    monkeypatch.setattr(
        scholar_mod, "resolve_scholar_client", lambda spec: seen.setdefault("scholar", spec)
    )
    monkeypatch.setattr(
        vision_mod, "resolve_vision_client", lambda spec: seen.setdefault("vision", spec)
    )
    monkeypatch.setattr(rag_mod, "resolve_rag_retriever", lambda spec: seen.setdefault("rag", spec))

    monkeypatch.setenv("CLIO_ENV_FILE", str(Path("/nonexistent-env-file")))
    monkeypatch.setenv("CLIO_LLM", "echo")
    monkeypatch.setenv("CLIO_SCHOLAR", "openalex")
    monkeypatch.setenv("CLIO_VISION", "gemini")
    monkeypatch.setenv("CLIO_RAG", "off")

    build_subagent()

    assert seen == {"llm": "echo", "scholar": "openalex", "vision": "gemini", "rag": "off"}


def test_build_subagent_loads_the_env_file(monkeypatch, tmp_path: Path) -> None:
    """A server process reads .env.local itself; a host never hands it the shell."""
    env_file = tmp_path / "keys.env"
    env_file.write_text('SEMANTIC_SCHOLAR_API_KEY="from-the-file"\n', encoding="utf-8")

    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.setenv("CLIO_ENV_FILE", str(env_file))
    monkeypatch.setenv("CLIO_SCHOLAR", "off")
    monkeypatch.setenv("CLIO_RAG", "off")
    monkeypatch.setenv("CLIO_VISION", "off")
    monkeypatch.setenv("CLIO_LLM", "echo")

    import os

    build_subagent()

    assert os.environ["SEMANTIC_SCHOLAR_API_KEY"] == "from-the-file"


def test_handle_jsonrpc_default_stays_bare_and_hermetic(monkeypatch) -> None:
    """The pure handler must not acquire network clients from the ambient env."""

    def explode(spec):  # pragma: no cover - only runs if the contract regresses
        raise AssertionError("handle_jsonrpc resolved a live client")

    monkeypatch.setattr(scholar_mod, "resolve_scholar_client", explode)
    monkeypatch.setenv("CLIO_SCHOLAR", "auto")

    task = handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {"skillId": "audit", "payload": {"markdown": "## A\n\nx"}},
        }
    )["result"]

    assert task["status"]["state"] == "completed"

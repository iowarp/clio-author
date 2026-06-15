"""Hermetic tests for the real `LLMClient` providers.

The providers shell out to external CLIs / a local server, so only the
pure/guard logic is tested here (no subprocess or network is invoked).
"""

from __future__ import annotations

import pytest

from clio_parser.harness.types import Message
from clio_parser.llm import providers


def test_flatten_messages_system_preamble_and_labels() -> None:
    msgs = [
        Message(role="system", content="SYS"),
        Message(role="user", content="hello"),
        Message(role="assistant", content="prior"),
    ]
    out = providers.flatten_messages(msgs)
    assert out.startswith("SYS")
    assert "hello" in out
    assert "[assistant]" in out  # non-user turns are labelled


def test_flatten_messages_no_system() -> None:
    out = providers.flatten_messages([Message(role="user", content="just this")])
    assert out == "just this"


@pytest.mark.parametrize("cls", [providers.ClaudeCliLLMClient, providers.CodexCliLLMClient])
def test_cli_clients_raise_clear_error_when_binary_missing(monkeypatch, cls) -> None:
    monkeypatch.setattr(providers.shutil, "which", lambda _binary: None)
    with pytest.raises(RuntimeError, match="not found on PATH"):
        cls().complete([Message(role="user", content="x")])


def test_clients_expose_complete() -> None:
    for client in (
        providers.ClaudeCliLLMClient(),
        providers.CodexCliLLMClient(),
        providers.OllamaLLMClient(),
    ):
        assert callable(client.complete)

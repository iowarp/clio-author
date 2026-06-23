"""Hermetic tests for the real `LLMClient` providers.

The providers shell out to external CLIs / a local server, so only the
pure/guard logic is tested here (no subprocess or network is invoked).
"""

from __future__ import annotations

import pytest

from clio_author.harness.types import Message
from clio_author.llm import providers


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


def test_resolve_llm_default_and_echo() -> None:
    from clio_author.llm.client import EchoLLMClient

    assert isinstance(providers.resolve_llm(None), EchoLLMClient)
    assert isinstance(providers.resolve_llm("echo"), EchoLLMClient)
    assert isinstance(providers.resolve_llm("CLAUDE".lower()), providers.ClaudeCliLLMClient)


def test_resolve_llm_named_providers() -> None:
    assert isinstance(providers.resolve_llm("claude"), providers.ClaudeCliLLMClient)
    assert isinstance(providers.resolve_llm("codex"), providers.CodexCliLLMClient)
    assert isinstance(providers.resolve_llm("ollama"), providers.OllamaLLMClient)


def test_resolve_llm_openai_compatible_providers(monkeypatch) -> None:
    monkeypatch.delenv("CLIO_LLM_MODEL", raising=False)
    # LM Studio: local, no key, default base URL ends in /v1.
    lm = providers.resolve_llm("lmstudio")
    assert isinstance(lm, providers.OpenAICompatLLMClient)
    assert lm.provider == "lmstudio" and lm.base_url.endswith(":1234/v1")
    assert isinstance(providers.resolve_llm("lm-studio"), providers.OpenAICompatLLMClient)

    # OpenRouter: needs a key; carries it as bearer + attribution headers.
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    orr = providers.resolve_llm("openrouter")
    assert isinstance(orr, providers.OpenAICompatLLMClient)
    assert orr.api_key == "sk-test" and "openrouter.ai" in orr.base_url
    assert orr.extra_headers.get("X-Title") == "clio-author"

    # LiteLLM proxy: default localhost:4000/v1.
    lite = providers.resolve_llm("litellm")
    assert isinstance(lite, providers.OpenAICompatLLMClient)
    assert lite.provider == "litellm" and lite.base_url.endswith(":4000/v1")


def test_resolve_openrouter_without_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        providers.resolve_llm("openrouter")


def test_openai_compat_complete_builds_request_and_parses(monkeypatch) -> None:
    import json

    captured: dict[str, object] = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"hi there"}}]}'

    def _fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower() for k in dict(req.header_items())}
        captured["body"] = json.loads(req.data.decode())
        return _Resp()

    monkeypatch.setattr(providers.urllib.request, "urlopen", _fake_urlopen)
    client = providers.OpenAICompatLLMClient(
        model="m", base_url="http://x/v1", api_key="k", provider="lmstudio"
    )
    out = client.complete([Message(role="user", content="yo")])
    assert out == "hi there"
    assert captured["url"] == "http://x/v1/chat/completions"
    assert captured["body"]["model"] == "m"
    assert "authorization" in captured["headers"]  # bearer token sent


def test_resolve_llm_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown CLIO_LLM"):
        providers.resolve_llm("gpt-9000")

"""Real `LLMClient` providers (optional, stdlib-only, lazy).

These are not used by the hermetic test suite (that uses `EchoLLMClient`). They
let a host wire a real model into the same `LLMClient.complete(messages) -> str`
contract the experts call.

- ``ClaudeCliLLMClient`` shells out to the ``claude`` CLI (Claude Code / Claude
  Agent), which is session-based and needs no API key when Claude Code is
  authenticated. This is the strongest default.
- ``OllamaLLMClient`` talks to a local Ollama server over HTTP.
- ``OpenAICompatLLMClient`` talks to any OpenAI-compatible ``/chat/completions``
  endpoint and backs three specs: ``lmstudio`` (a local LM Studio server),
  ``openrouter`` (the hosted OpenRouter gateway), and ``litellm`` (a LiteLLM
  proxy). All three speak the same request/response shape.

All use only the standard library, so importing this module never pulls a
dependency.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence

from clio_author.harness.types import Message

__all__ = [
    "ClaudeCliLLMClient",
    "CodexCliLLMClient",
    "OllamaLLMClient",
    "OpenAICompatLLMClient",
    "flatten_messages",
    "resolve_llm",
]


def resolve_llm(spec: str | None = None):
    """Resolve an ``LLMClient`` from a short spec string (e.g. the ``CLIO_LLM`` env var).

    ``None``/``"echo"`` -> offline ``EchoLLMClient`` (the default, keeps things
    hermetic); ``"claude"`` -> :class:`ClaudeCliLLMClient`; ``"codex"`` ->
    :class:`CodexCliLLMClient`; ``"ollama"`` -> :class:`OllamaLLMClient`;
    ``"lmstudio"`` / ``"openrouter"`` / ``"litellm"`` -> :class:`OpenAICompatLLMClient`.
    The model is read from ``CLIO_LLM_MODEL``; per-provider URLs/keys are read from
    their own env vars (see each branch below).
    """
    name = (spec or "echo").strip().lower()
    if name in ("", "echo"):
        from clio_author.llm.client import EchoLLMClient

        return EchoLLMClient()
    model = os.environ.get("CLIO_LLM_MODEL") or None
    if name == "claude":
        return ClaudeCliLLMClient(model=model)
    if name == "codex":
        return CodexCliLLMClient(model=model)
    if name == "ollama":
        return OllamaLLMClient(
            model=model or "llama3.1:8b",
            url=os.environ.get("CLIO_OLLAMA_URL", "http://localhost:11434"),
        )
    if name in ("lmstudio", "lm_studio", "lm-studio"):
        # Local LM Studio server; model = whatever is loaded (any name is accepted),
        # no API key needed. Override the URL with CLIO_LMSTUDIO_URL.
        return OpenAICompatLLMClient(
            model=model or "local-model",
            base_url=os.environ.get("CLIO_LMSTUDIO_URL", "http://localhost:1234/v1"),
            api_key=os.environ.get("LMSTUDIO_API_KEY"),
            provider="lmstudio",
        )
    if name == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("CLIO_LLM=openrouter requires OPENROUTER_API_KEY in the environment")
        # Optional OpenRouter attribution headers (used only for their dashboard
        # ranking); referer is opt-in via env, title is a neutral constant.
        headers = {"X-Title": "clio-author"}
        referer = os.environ.get("CLIO_OPENROUTER_REFERER")
        if referer:
            headers["HTTP-Referer"] = referer
        return OpenAICompatLLMClient(
            model=model or "openai/gpt-4o-mini",
            base_url=os.environ.get("CLIO_OPENROUTER_URL", "https://openrouter.ai/api/v1"),
            api_key=key,
            extra_headers=headers,
            provider="openrouter",
        )
    if name == "litellm":
        # A LiteLLM proxy (OpenAI-compatible). Override URL with CLIO_LITELLM_URL;
        # pass LITELLM_API_KEY when the proxy enforces a master key.
        return OpenAICompatLLMClient(
            model=model or "gpt-3.5-turbo",
            base_url=os.environ.get("CLIO_LITELLM_URL", "http://localhost:4000/v1"),
            api_key=os.environ.get("LITELLM_API_KEY"),
            provider="litellm",
        )
    raise ValueError(
        f"unknown CLIO_LLM={spec!r} (use one of: claude, codex, ollama, lmstudio, "
        "openrouter, litellm, echo)"
    )


def flatten_messages(messages: Sequence[Message]) -> str:
    """Flatten a chat message list into a single prompt string.

    System messages become a preamble; remaining turns are labelled unless they
    are plain user turns. Used by single-shot CLI providers.
    """
    system = [m.content for m in messages if m.role == "system"]
    turns: list[str] = []
    for m in messages:
        if m.role == "system":
            continue
        turns.append(m.content if m.role == "user" else f"[{m.role}]\n{m.content}")
    preamble = ("\n\n".join(system) + "\n\n") if system else ""
    return preamble + "\n\n".join(turns)


class ClaudeCliLLMClient:
    """`LLMClient` backed by the ``claude`` CLI (Claude Code / Agent SDK).

    Session-based, no API key required when Claude Code is logged in. Each
    ``complete`` is a one-shot ``claude -p`` invocation (the experts already pass
    full context per call, so statelessness is fine).
    """

    def __init__(
        self, model: str | None = None, *, timeout: int = 300, binary: str = "claude"
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.binary = binary

    def complete(self, messages: Sequence[Message], **kwargs: object) -> str:
        exe = shutil.which(self.binary)
        if exe is None:
            raise RuntimeError(
                f"{self.binary!r} CLI not found on PATH; install Claude Code or use another provider"
            )
        prompt = flatten_messages(messages)
        cmd = [exe, "-p", prompt, "--output-format", "text"]
        if self.model:
            cmd += ["--model", self.model]
        proc = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, timeout=self.timeout
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI failed (exit {proc.returncode}): {proc.stderr[:300]}")
        return proc.stdout.strip()


class CodexCliLLMClient:
    """`LLMClient` backed by the ``codex`` CLI (Codex SDK), via ``codex exec``.

    Session-based and non-interactive. Runs read-only in a scratch directory and
    reads the agent's final message from ``--output-last-message`` so the result
    is just the completion text (no event noise).
    """

    def __init__(
        self, model: str | None = None, *, timeout: int = 600, binary: str = "codex"
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.binary = binary

    def complete(self, messages: Sequence[Message], **kwargs: object) -> str:
        exe = shutil.which(self.binary)
        if exe is None:
            raise RuntimeError(
                f"{self.binary!r} CLI not found on PATH; install Codex or use another provider"
            )
        prompt = flatten_messages(messages)
        with tempfile.TemporaryDirectory() as td:
            out_file = os.path.join(td, "last.txt")
            cmd = [
                exe,
                "exec",
                "--skip-git-repo-check",
                "-s",
                "read-only",
                "-C",
                td,
                "--output-last-message",
                out_file,
            ]
            if self.model:
                cmd += ["-m", self.model]
            cmd += [prompt]
            proc = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            try:
                with open(out_file, encoding="utf-8") as fh:
                    out = fh.read().strip()
            except FileNotFoundError:
                out = proc.stdout.strip()
        if not out and proc.returncode != 0:
            raise RuntimeError(f"codex exec failed (exit {proc.returncode}): {proc.stderr[:300]}")
        return out


class OllamaLLMClient:
    """`LLMClient` backed by a local Ollama server (`/api/chat`)."""

    def __init__(
        self,
        model: str = "llama3.1:8b",
        *,
        url: str = "http://localhost:11434",
        timeout: int = 300,
        temperature: float = 0.2,
    ) -> None:
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature

    def complete(self, messages: Sequence[Message], **kwargs: object) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        req = urllib.request.Request(  # noqa: S310
            f"{self.url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            data = json.loads(resp.read())
        return str(data["message"]["content"])


class OpenAICompatLLMClient:
    """`LLMClient` for any OpenAI-compatible ``/chat/completions`` endpoint.

    Backs LM Studio (local server), OpenRouter (hosted gateway), and a LiteLLM
    proxy -- all speak the OpenAI chat-completions request/response shape. Uses
    only the standard library (``urllib``). ``base_url`` should include any version
    prefix (e.g. ``.../v1``); ``/chat/completions`` is appended. ``api_key`` is sent
    as a bearer token when present (LM Studio usually needs none).
    """

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 300,
        temperature: float = 0.2,
        extra_headers: Mapping[str, str] | None = None,
        provider: str = "openai-compatible",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.extra_headers = dict(extra_headers or {})
        self.provider = provider

    def complete(self, messages: Sequence[Message], **kwargs: object) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
            "stream": False,
        }
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(  # noqa: S310
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:  # 4xx/5xx -> surface status + body snippet
            body = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"{self.provider} request failed (HTTP {exc.code}): {body}") from exc
        except urllib.error.URLError as exc:  # connection refused / DNS / timeout
            raise RuntimeError(
                f"{self.provider} request failed: {exc.reason} "
                f"(is the endpoint at {self.base_url} reachable?)"
            ) from exc
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"{self.provider} returned an unexpected response shape") from exc

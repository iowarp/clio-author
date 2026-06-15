"""Real `LLMClient` providers (optional, stdlib-only, lazy).

These are not used by the hermetic test suite (that uses `EchoLLMClient`). They
let a host wire a real model into the same `LLMClient.complete(messages) -> str`
contract the experts call.

- ``ClaudeCliLLMClient`` shells out to the ``claude`` CLI (Claude Code / Claude
  Agent), which is session-based and needs no API key when Claude Code is
  authenticated. This is the strongest default.
- ``OllamaLLMClient`` talks to a local Ollama server over HTTP.

Both use only the standard library, so importing this module never pulls a
dependency.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from collections.abc import Sequence

from clio_parser.harness.types import Message

__all__ = [
    "ClaudeCliLLMClient",
    "CodexCliLLMClient",
    "OllamaLLMClient",
    "flatten_messages",
    "resolve_llm",
]


def resolve_llm(spec: str | None = None):
    """Resolve an ``LLMClient`` from a short spec string (e.g. the ``CLIO_LLM`` env var).

    ``None``/``"echo"`` -> offline ``EchoLLMClient`` (the default, keeps things
    hermetic); ``"claude"`` -> :class:`ClaudeCliLLMClient`; ``"codex"`` ->
    :class:`CodexCliLLMClient`; ``"ollama"`` -> :class:`OllamaLLMClient`. The model
    is read from ``CLIO_LLM_MODEL`` and the Ollama URL from ``CLIO_OLLAMA_URL``.
    """
    name = (spec or "echo").strip().lower()
    if name in ("", "echo"):
        from clio_parser.llm.client import EchoLLMClient

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
    raise ValueError(f"unknown CLIO_LLM={spec!r} (use one of: claude, codex, ollama, echo)")


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

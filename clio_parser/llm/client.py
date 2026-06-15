"""Pluggable, synchronous LLM client abstraction.

The harness depends only on the :class:`LLMClient` protocol so that real
providers (Ollama, hosted APIs, local vision models) can be swapped in later
milestones. :class:`EchoLLMClient` is a deterministic, network-free stub used as
the default in development and tests.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from clio_parser.harness.types import Message


@runtime_checkable
class LLMClient(Protocol):
    """A synchronous text-completion client."""

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        """Return a completion string for the given conversation."""
        ...


class EchoLLMClient:
    """Deterministic stub that echoes the last message.

    Used as the default client so the whole harness runs offline with no API
    keys and tests stay hermetic.
    """

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        """Return ``"[echo] <last message content>"`` (empty string if none)."""
        if not messages:
            return "[echo] "
        return f"[echo] {messages[-1].content}"

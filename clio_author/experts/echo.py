"""A trivial expert demonstrating the expert contract.

:class:`EchoExpert` does no real work; it exists so the M0 harness can run
end-to-end and to model the shape every future expert follows.
"""

from __future__ import annotations

from clio_author.harness.base import BaseAgent
from clio_author.llm.client import LLMClient

ECHO_SYSTEM_PROMPT = "You are an echo expert. Repeat the user's request back to them."


class EchoExpert(BaseAgent):
    """A no-op expert that echoes the task via its LLM client."""

    def __init__(self, llm: LLMClient) -> None:
        super().__init__(role="echo", system_prompt=ECHO_SYSTEM_PROMPT, llm=llm)

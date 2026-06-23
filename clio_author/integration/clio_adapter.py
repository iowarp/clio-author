"""A thin, host-agnostic adapter exposing clio-author as a subagent.

:class:`ClioAuthorSubagent` wraps :class:`~clio_author.agent.ClioAuthorAgent`
behind two stable, JSON-serializable methods:

* :meth:`capabilities` -- a discovery manifest (name, version, and the routed
  actions with one-line descriptions and expected payload keys).
* :meth:`run` -- dispatch an ``(action, payload)`` to the agent and return a
  plain ``dict`` (``action`` / ``content`` / ``structured`` / ``metadata``).

It imports **nothing** from the ``clio-agent`` repo so the harness stays
standalone. Neither method raises: any failure is captured into an ``error``
field on the returned dict. ``structured`` already comes from a Pydantic
``model_dump()``, so every return value round-trips through ``json.dumps``.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any
from uuid import uuid4

from clio_author.agent import ClioAuthorAgent
from clio_author.harness.types import Task
from clio_author.integration.manifest import ACTIONS, lifecycle_overview
from clio_author.llm.client import LLMClient
from clio_author.llm.vision import VisionClient
from clio_author.retrieval.scholar import ScholarClient
from clio_author.tools.files import SafeFiles


def _package_version() -> str:
    """Return the installed package version (falls back to the pinned default)."""
    try:
        return version("clio-author")
    except PackageNotFoundError:  # pragma: no cover - editable/source checkout
        return "0.0.1"


# The discovery manifest lives in :mod:`clio_author.integration.manifest` so both
# the adapter and the agent's router can read it without a circular import.
_ACTIONS: list[dict[str, Any]] = ACTIONS


class ClioAuthorSubagent:
    """Stable, serializable wrapper around :class:`ClioAuthorAgent` for hosts."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        files: SafeFiles | None = None,
        scholar_client: ScholarClient | None = None,
        vision: VisionClient | None = None,
    ) -> None:
        """Build the subagent over a :class:`ClioAuthorAgent`.

        Args mirror the agent: an optional shared ``llm`` (default offline echo),
        ``files`` for write-capable experts, a ``scholar_client`` for citation
        grounding, and an optional ``vision`` client (e.g. Gemini) for the figure
        agent's real image describe/generate route.
        """
        self._agent = ClioAuthorAgent(
            llm,
            files=files,
            scholar_client=scholar_client,
            vision=vision,
        )

    def capabilities(self) -> dict[str, Any]:
        """Return a JSON-serializable discovery manifest of the supported actions.

        Each action carries author-lifecycle metadata (``phase`` list and
        ``needs_source``); ``lifecycle`` is the ordered phase catalog mapping each
        phase to the actions that serve it, so a host can route by what the author
        needs to do rather than by action name.
        """
        return {
            "name": "clio-author",
            "version": _package_version(),
            "actions": [dict(action) for action in _ACTIONS],
            "lifecycle": lifecycle_overview(),
        }

    def run(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch ``action`` with ``payload`` and return a serializable result dict.

        The agent is invoked with ``payload`` plus the ``action`` key. Returns
        ``{"action", "content", "structured", "metadata"}`` on success. Never
        raises: any failure is captured as ``{"action", "error", ...}``. The
        return value always round-trips through :func:`json.dumps`.
        """
        try:
            task = Task(
                id=uuid4().hex,
                description=action,
                payload={**(payload or {}), "action": action},
            )
            out = self._agent.invoke(task)
        except Exception as exc:  # noqa: BLE001 - never raise across the adapter boundary
            return {
                "action": action,
                "content": "",
                "structured": None,
                "metadata": {},
                "error": str(exc),
            }
        return {
            "action": action,
            "content": out.content,
            "structured": out.structured,
            "metadata": out.metadata,
        }


__all__ = ["ClioAuthorSubagent"]

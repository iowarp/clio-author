"""A thin, host-agnostic adapter exposing clio-parser as a subagent.

:class:`ClioParserSubagent` wraps :class:`~clio_parser.agent.ClioParserAgent`
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

from clio_parser.agent import ClioParserAgent
from clio_parser.harness.types import Task
from clio_parser.llm.client import LLMClient
from clio_parser.llm.vision import VisionClient
from clio_parser.retrieval.scholar import ScholarClient
from clio_parser.tools.files import SafeFiles


def _package_version() -> str:
    """Return the installed package version (falls back to the pinned default)."""
    try:
        return version("clio-parser")
    except PackageNotFoundError:  # pragma: no cover - editable/source checkout
        return "0.0.1"


# Discovery manifest for every routed action: a one-line description plus the
# payload keys a host is expected to supply. Kept in lock-step with the router in
# :meth:`ClioParserAgent._route`.
_ACTIONS: list[dict[str, Any]] = [
    {
        "action": "ingest",
        "description": "Convert an arXiv id / URL / PDF path into clean Markdown + memory blocks.",
        "payload_keys": ["source"],
    },
    {
        "action": "ask",
        "description": "Answer a question grounded only in the provided memory blocks.",
        "payload_keys": ["question", "blocks"],
    },
    {
        "action": "review",
        "description": "Produce a structured, persona-conditioned peer review of a paper.",
        "payload_keys": ["paper", "persona"],
    },
    {
        "action": "meta_review",
        "description": "Aggregate several reviews into a single area-chair meta-review.",
        "payload_keys": ["reviews"],
    },
    {
        "action": "cite",
        "description": "Verify citation candidates and emit suggestions only (never overwrites).",
        "payload_keys": ["candidates", "out_dir"],
    },
    {
        "action": "write",
        "description": "Draft a single paper section grounded in scoped source material.",
        "payload_keys": ["outline", "section_plan", "blocks", "source", "vision", "out_path"],
    },
    {
        "action": "edit",
        "description": "Revise existing prose to address reviewer feedback.",
        "payload_keys": ["draft", "review", "critic_notes", "target"],
    },
    {
        "action": "polish",
        "description": (
            "Polish prose for clarity, flow, and academic voice (preserves citations/claims)."
        ),
        "payload_keys": ["text", "draft", "voice", "target"],
    },
    {
        "action": "coherence",
        "description": (
            "Check cross-section consistency (terminology, contradictions, flow) "
            "across a manuscript."
        ),
        "payload_keys": ["sections", "markdown", "text"],
    },
    {
        "action": "describe_figures",
        "description": "Fill in descriptions/captions for the figures in memory blocks.",
        "payload_keys": ["blocks", "figures", "context"],
    },
    {
        "action": "plot",
        "description": "Generate matplotlib plot code (code text only; never executed).",
        "payload_keys": ["spec", "out_path"],
    },
    {
        "action": "compose",
        "description": "Draft a whole multi-section manuscript from an idea + experimental log.",
        "payload_keys": [
            "idea",
            "experimental_log",
            "outline",
            "candidates",
            "blocks",
            "review",
            "max_rounds",
            "out_dir",
        ],
    },
    {
        "action": "export",
        "description": "Export a composed manuscript to LaTeX (paper.tex + references.bib).",
        "payload_keys": ["title", "sections", "markdown", "outline", "bibtex", "out_dir"],
    },
    {
        "action": "write_review",
        "description": "Run a writer/reviewer critic-refine loop and return the final output.",
        "payload_keys": ["outline", "section_plan", "blocks", "source", "max_rounds"],
    },
    {
        "action": "figure_refine",
        "description": "Run a figure visualizer/critic refine loop and return the final output.",
        "payload_keys": ["spec", "out_path", "max_rounds"],
    },
]


class ClioParserSubagent:
    """Stable, serializable wrapper around :class:`ClioParserAgent` for hosts."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        files: SafeFiles | None = None,
        scholar_client: ScholarClient | None = None,
        vision: VisionClient | None = None,
    ) -> None:
        """Build the subagent over a :class:`ClioParserAgent`.

        Args mirror the agent: an optional shared ``llm`` (default offline echo),
        ``files`` for write-capable experts, a ``scholar_client`` for citation
        grounding, and an optional ``vision`` client (e.g. Gemini) for the figure
        agent's real image describe/generate route.
        """
        self._agent = ClioParserAgent(
            llm, files=files, scholar_client=scholar_client, vision=vision
        )

    def capabilities(self) -> dict[str, Any]:
        """Return a JSON-serializable discovery manifest of the supported actions."""
        return {
            "name": "clio-parser",
            "version": _package_version(),
            "actions": [dict(action) for action in _ACTIONS],
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


__all__ = ["ClioParserSubagent"]

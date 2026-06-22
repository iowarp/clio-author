"""The capability manifest for clio-author's routed actions.

``ACTIONS`` is the single source of truth describing every action the
:class:`~clio_author.agent.ClioAuthorAgent` router supports: a one-line
description plus the payload keys a host is expected to supply. It is kept in
lock-step with the router in :meth:`ClioAuthorAgent._route`.

The manifest lives in this neutral module (rather than in
:mod:`clio_author.integration.clio_adapter`) so both the adapter *and* the agent
can read it without a circular import: the adapter already imports the agent, so
the agent cannot import the adapter back. The dynamic orchestrator
(:func:`~clio_author.experts.orchestrate.run_orchestrate`) consumes this list as
the menu of actions it may plan over.
"""

from __future__ import annotations

from typing import Any

# Discovery manifest for every routed action: a one-line description plus the
# payload keys a host is expected to supply. Kept in lock-step with the router in
# :meth:`ClioAuthorAgent._route`.
ACTIONS: list[dict[str, Any]] = [
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
        "payload_keys": ["paper", "persona", "ground", "figures", "blocks"],
    },
    {
        "action": "meta_review",
        "description": "Aggregate several reviews into a single area-chair meta-review.",
        "payload_keys": ["reviews"],
    },
    {
        "action": "rebuttal",
        "description": (
            "Draft an author rebuttal addressing a review point by point "
            "(grounded; invents nothing)."
        ),
        "payload_keys": ["paper", "review", "review_text", "target"],
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
        "action": "kg",
        "description": (
            "Extract a content knowledge graph (claims/methods/datasets/results + "
            "relations) from a paper's memory blocks. With full=True (or an explicit "
            "stages list) runs the multi-stage pipeline "
            "(metadata -> ontology -> extraction -> coref -> verification -> summary) "
            "with checkpoint/resume."
        ),
        "payload_keys": ["blocks", "out_dir", "full", "stages", "checkpoints"],
    },
    {
        "action": "plan",
        "description": (
            "Turn an idea or outline into per-section writing plans "
            "(tasks, claims, sources, word budgets)."
        ),
        "payload_keys": ["idea", "experimental_log", "outline", "blocks", "candidates", "out_dir"],
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
            "plan",
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
    {
        "action": "orchestrate",
        "description": "Plan and run a sequence of actions to achieve a goal (dynamic multi-step).",
        "payload_keys": ["goal", "inputs", "max_steps", "out_dir"],
    },
]


__all__ = ["ACTIONS"]

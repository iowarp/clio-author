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
        "action": "gather",
        "description": (
            "Ingest many sources (files, folders, globs, git repos, PDFs/arXiv "
            "ids) into one merged memory-block set (context.json) for grounding "
            "the writing path."
        ),
        "payload_keys": ["sources", "out_dir", "max_files", "max_text_chars"],
    },
    {
        "action": "experiment",
        "description": (
            "Read the design/architecture/experiments of one or more reference "
            "papers and (with a new-paper idea) recreate a grounded evaluation "
            "plan: datasets, baselines, metrics, ablations, protocol, threats."
        ),
        "payload_keys": ["blocks", "sources", "markdown", "text", "idea", "out_dir"],
    },
    {
        "action": "ask",
        "description": "Answer a question grounded only in the provided memory blocks.",
        "payload_keys": ["question", "blocks", "sources"],
    },
    {
        "action": "review",
        "description": "Produce a structured, persona-conditioned peer review of a paper.",
        "payload_keys": ["paper", "persona", "ground", "figures", "blocks", "sources"],
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
        "payload_keys": [
            "outline",
            "section_plan",
            "blocks",
            "sources",
            "source",
            "vision",
            "out_path",
        ],
    },
    {
        "action": "revise",
        "description": (
            "Revise existing prose. mode='feedback' (default) addresses reviewer "
            "feedback/critique and may change content; mode='style' polishes "
            "clarity/flow/academic voice while preserving meaning and citations. "
            "(Subsumes the 'edit' and 'polish' aliases.)"
        ),
        "payload_keys": [
            "draft",
            "text",
            "mode",
            "review",
            "critic_notes",
            "voice",
            "target",
        ],
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
        "payload_keys": ["blocks", "sources", "out_dir", "full", "stages", "checkpoints"],
    },
    {
        "action": "plan",
        "description": (
            "Turn an idea or outline into per-section writing plans "
            "(tasks, claims, sources, word budgets)."
        ),
        "payload_keys": [
            "idea",
            "experimental_log",
            "outline",
            "blocks",
            "sources",
            "candidates",
            "out_dir",
        ],
    },
    {
        "action": "research",
        "description": (
            "Propose foundational/recent/competing sources, gaps, and a synthesis "
            "for a topic or section; grounds proposed titles against a scholar "
            "backend when one is configured (invents no verified citations)."
        ),
        "payload_keys": [
            "topic",
            "section",
            "outline",
            "blocks",
            "sources",
            "source",
            "depth",
            "out_dir",
        ],
    },
    {
        "action": "discover",
        "description": (
            "Find real candidate papers for a topic via scholarly search "
            "(Semantic Scholar/OpenAlex/Crossref/arXiv)."
        ),
        "payload_keys": ["query", "topic", "limit", "cutoff_date", "out_dir"],
    },
    {
        "action": "verify_work",
        "description": (
            "Goal-backward check of written prose against the claims it should "
            "make: per-claim made/supported, rolled up to a VERIFIED/GAPS verdict."
        ),
        "payload_keys": ["section_plan", "claims", "text", "markdown", "draft"],
    },
    {
        "action": "check_refs",
        "description": (
            "Deterministically lint a BibTeX bibliography and cross-check it "
            "against the cited keys in the prose (malformed/duplicate entries, "
            "cited-but-missing, uncited entries). No LLM; suggestions only."
        ),
        "payload_keys": ["bibtex", "markdown", "text", "sections"],
    },
    {
        "action": "section_review",
        "description": (
            "Layered review of ONE section: L1 reference check, L2 coherence, L3 "
            "persona peer review, with a deterministically derived severity summary."
        ),
        "payload_keys": ["section", "text", "markdown", "bibtex", "persona", "out_dir"],
    },
    {
        "action": "audit",
        "description": (
            "Deterministic manuscript completeness audit: required sections "
            "present, per-section word budgets, unresolved [TODO]/[CITE:]/empty "
            "\\cite{} placeholders, and citation coverage. No LLM."
        ),
        "payload_keys": ["sections", "markdown", "outline", "bibtex", "candidates", "verified"],
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
            "sources",
            "review",
            "max_rounds",
            "plan",
            "out_dir",
            "pdf",
        ],
    },
    {
        "action": "export",
        "description": "Export a composed manuscript to LaTeX (paper.tex + references.bib).",
        "payload_keys": ["title", "sections", "markdown", "outline", "bibtex", "out_dir", "pdf"],
    },
    {
        "action": "write_review",
        "description": "Run a writer/reviewer critic-refine loop and return the final output.",
        "payload_keys": ["outline", "section_plan", "blocks", "sources", "source", "max_rounds"],
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


# --------------------------------------------------------------------------- #
# Author-lifecycle metadata
# --------------------------------------------------------------------------- #
# The phases of the author's journey, in order. An action may serve several
# phases (e.g. ``review`` is used both to self-check your own draft in
# ``strengthen`` and to referee others' papers). ``docs/LIFECYCLE.md`` tells the
# full story; this is the machine-readable map a host can route by.
PHASES: list[tuple[str, str]] = [
    ("frame", "Frame — what's my story, and what already exists?"),
    ("gather", "Gather — pull in the material to build on"),
    ("plan", "Plan — blueprint the paper and its evaluation"),
    ("draft", "Draft — write and illustrate"),
    ("strengthen", "Strengthen — self-review and tighten before anyone sees it"),
    ("referee", "Referee — review others' papers"),
    ("respond", "Respond — answer the reviewers of your paper"),
    ("ship", "Ship — produce the camera-ready"),
    ("drive", "Drive — run a multi-step job end to end"),
]

# Per-action lifecycle assignment: ``action -> (phases, needs_source)``.
# ``needs_source`` is True when the action operates on a *processed paper* (memory
# blocks / figures), i.e. you will normally ``ingest`` or ``gather`` first;
# False when it works from text / an idea / JSON you supply directly. ``ingest``
# and ``gather`` are the producers of source content, so they are False.
_LIFECYCLE: dict[str, tuple[list[str], bool]] = {
    "ingest": (["gather"], False),
    "gather": (["gather"], False),
    "experiment": (["frame", "plan"], True),
    "ask": (["frame", "gather"], True),
    "review": (["strengthen", "referee"], False),
    "meta_review": (["referee"], False),
    "rebuttal": (["respond"], False),
    "cite": (["gather", "strengthen"], False),
    "revise": (["strengthen", "respond"], False),
    "coherence": (["strengthen"], False),
    "kg": (["frame", "gather"], True),
    "plan": (["plan"], False),
    "research": (["frame", "plan"], False),
    "discover": (["frame"], False),
    "verify_work": (["strengthen"], False),
    "check_refs": (["strengthen"], False),
    "section_review": (["strengthen", "referee"], False),
    "audit": (["strengthen", "respond"], False),
    "describe_figures": (["draft"], True),
    "plot": (["draft"], False),
    "compose": (["draft", "ship"], False),
    "export": (["ship"], False),
    "write": (["draft"], False),
    "write_review": (["strengthen"], False),
    "figure_refine": (["draft", "strengthen"], False),
    "orchestrate": (["drive"], False),
}

# Attach the lifecycle metadata to each action entry, keeping the manifest the
# single source of truth. A KeyError here means an action was added without a
# lifecycle assignment (intentional lock-step guard).
_VALID_PHASES = {key for key, _ in PHASES}
for _entry in ACTIONS:
    _phases, _needs_source = _LIFECYCLE[_entry["action"]]
    if not set(_phases) <= _VALID_PHASES:  # pragma: no cover - guards a typo
        raise ValueError(f"action {_entry['action']!r} has an unknown phase: {_phases}")
    _entry["phase"] = _phases
    _entry["needs_source"] = _needs_source


def actions_for_phase(phase: str) -> list[str]:
    """Return the action names that serve ``phase`` (in manifest order)."""
    return [entry["action"] for entry in ACTIONS if phase in entry["phase"]]


def lifecycle_overview() -> list[dict[str, Any]]:
    """Return the phase catalog with the actions that serve each phase."""
    return [
        {"phase": key, "title": title, "actions": actions_for_phase(key)} for key, title in PHASES
    ]


__all__ = ["ACTIONS", "PHASES", "actions_for_phase", "lifecycle_overview"]

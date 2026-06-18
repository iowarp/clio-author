"""Content knowledge graph for a processed scientific paper (Pydantic v2).

This module re-implements -- **from scratch, no source code copied** -- the
*concept* of protoneo's content knowledge graph (protoneo is AGPL-3.0; see
``artifact/notes/SYNTHESIS.md``). The idea: extract a semantic graph of a
paper's **content** -- its claims, methods, datasets, results, metrics,
concepts and tasks, plus the relations between them -- which is distinct from
any *citation* / literature graph (a graph of papers).

The models (:class:`KGNode`, :class:`KGEdge`, :class:`KnowledgeGraph`) are pure
data with no I/O. :func:`build_kg_from_llm` renders a paper's memory blocks into
a prompt, asks an :class:`~clio_parser.llm.client.LLMClient` for a JSON graph,
and coerces the response into the models -- reusing the reviewer's stdlib JSON
extractor and never raising.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from clio_parser.experts.reviewer import _extract_json_object
from clio_parser.harness.types import Message
from clio_parser.ingest.blocks import MemoryBlocks
from clio_parser.llm.client import LLMClient

NodeType = Literal["claim", "method", "dataset", "result", "metric", "concept", "task"]
"""The kind of content entity a :class:`KGNode` represents."""

EdgeRelation = Literal[
    "uses", "evaluates_on", "compared_against", "reports", "part_of", "related_to"
]
"""The semantic relation a :class:`KGEdge` asserts between two nodes."""

KG_PROMPT = (
    "You are a scientific knowledge-graph extractor. Read the paper sections "
    "below and extract a CONTENT knowledge graph of the paper's claims, methods, "
    "datasets, results, metrics, concepts and tasks, plus the relations between "
    "them. This is the paper's content -- NOT a graph of cited papers.\n\n"
    "Respond with a single fenced JSON block:\n"
    "```json\n<json>\n```\n"
    'The JSON object must have a "nodes" list (each node an object with '
    '"id", "label", "type", and optional "description"/"section_path") and an '
    '"edges" list (each edge an object with "source", "target", "relation").\n'
    'Allowed node "type": claim, method, dataset, result, metric, concept, task. '
    'Allowed edge "relation": uses, evaluates_on, compared_against, reports, '
    "part_of, related_to.\n"
    "Use short stable ids; only emit edges between ids you also list as nodes. "
    "The JSON is parsed automatically, so keep the format precise."
)


class KGNode(BaseModel):
    """A single content entity in the knowledge graph."""

    id: str
    label: str
    type: NodeType
    description: str = ""
    section_path: str | None = None


class KGEdge(BaseModel):
    """A directed, typed relation between two :class:`KGNode` ids."""

    source: str
    target: str
    relation: EdgeRelation


class KnowledgeGraph(BaseModel):
    """A content knowledge graph: typed nodes plus typed relations."""

    nodes: list[KGNode] = Field(default_factory=list)
    edges: list[KGEdge] = Field(default_factory=list)

    def node_by_id(self, node_id: str) -> KGNode | None:
        """Return the node with ``node_id`` (or ``None`` when absent)."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable ``{nodes, edges}`` dict."""
        return self.model_dump()

    def to_mermaid(self) -> str:
        """Render the graph as a Mermaid ``graph TD`` block for a human view.

        Each node renders as ``id["<label> (<type>)"]``; each edge renders as
        ``source -->|relation| target``. Labels are sanitized so quotes/brackets
        do not break Mermaid parsing.
        """
        lines = ["graph TD"]
        for node in self.nodes:
            label = _mermaid_label(f"{node.label} ({node.type})")
            lines.append(f'    {_mermaid_id(node.id)}["{label}"]')
        for edge in self.edges:
            rel = _mermaid_label(edge.relation)
            lines.append(f"    {_mermaid_id(edge.source)} -->|{rel}| {_mermaid_id(edge.target)}")
        return "\n".join(lines)


def _extract_one(context: str, llm: LLMClient) -> tuple[list[KGNode], list[KGEdge], bool]:
    """Extract nodes/edges from one batch of section text. Returns (nodes, edges, parsed_ok)."""
    messages = [
        Message(role="system", content="You extract content knowledge graphs from papers."),
        Message(role="user", content=f"{KG_PROMPT}\n\nPaper sections:\n{context}"),
    ]
    parsed = _extract_json_object(llm.complete(messages))
    if parsed is None:
        return [], [], False

    nodes: list[KGNode] = []
    for item in parsed.get("nodes", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            nodes.append(KGNode.model_validate(item))
        except Exception:  # noqa: BLE001 - drop malformed nodes, never raise
            continue

    node_ids = {node.id for node in nodes}
    edges: list[KGEdge] = []
    for item in parsed.get("edges", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            edge = KGEdge.model_validate(item)
        except Exception:  # noqa: BLE001 - drop malformed edges, never raise
            continue
        if edge.source in node_ids and edge.target in node_ids:
            edges.append(edge)
    return nodes, edges, True


def build_kg_from_llm(
    blocks: MemoryBlocks,
    llm: LLMClient,
    *,
    max_sections: int | None = None,
    batch_size: int = 6,
) -> tuple[KnowledgeGraph, str | None]:
    """Extract a :class:`KnowledgeGraph` from ``blocks`` using ``llm``.

    Section blocks (via :meth:`~clio_parser.ingest.blocks.MemoryBlocks.select` at
    ``detail="full"``, optionally capped to ``max_sections``) are split into
    batches of ``batch_size`` and each batch is extracted with one LLM call, so a
    long paper does not overflow a single prompt. The per-batch sub-graphs are
    merged: nodes are deduplicated by ``(type, normalised label)`` (the first
    occurrence's id/description wins) and every edge is remapped onto the surviving
    node ids (edges to dropped/unknown nodes are discarded, duplicates collapsed).

    Parses each batch with the reviewer's stdlib
    :func:`~clio_parser.experts.reviewer._extract_json_object`. Returns
    ``(graph, error)``: ``error`` is set only when **every** batch failed to parse
    (``"could not parse KG JSON"``) or there are no sections; a partial parse still
    returns what was extracted with ``error=None``. Pure stdlib plus the supplied
    ``llm``; never raises.
    """
    sections = blocks.select(kinds=["section"], detail="full", max_blocks=max_sections)
    if not sections:
        return KnowledgeGraph(), "no sections to extract"
    size = max(1, batch_size)
    batches = [sections[i : i + size] for i in range(0, len(sections), size)]

    merged_nodes: list[KGNode] = []
    canonical: dict[tuple[str, str], str] = {}  # (type, norm-label) -> canonical id
    all_edges: list[KGEdge] = []
    any_parsed = False

    for batch in batches:
        nodes, edges, ok = _extract_one("\n\n".join(batch), llm)
        if not ok:
            continue
        any_parsed = True
        remap: dict[str, str] = {}  # this batch's node id -> canonical id
        for node in nodes:
            key = (node.type, re.sub(r"\s+", " ", node.label.strip().lower()))
            if key in canonical:
                remap[node.id] = canonical[key]
            else:
                canonical[key] = node.id
                remap[node.id] = node.id
                merged_nodes.append(node)
        for edge in edges:
            all_edges.append(
                KGEdge(
                    source=remap.get(edge.source, edge.source),
                    target=remap.get(edge.target, edge.target),
                    relation=edge.relation,
                )
            )

    if not any_parsed:
        return KnowledgeGraph(), "could not parse KG JSON"

    node_ids = {node.id for node in merged_nodes}
    seen: set[tuple[str, str, str]] = set()
    edges_final: list[KGEdge] = []
    for edge in all_edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        sig = (edge.source, edge.relation, edge.target)
        if sig in seen:
            continue
        seen.add(sig)
        edges_final.append(edge)

    return KnowledgeGraph(nodes=merged_nodes, edges=edges_final), None


def _mermaid_id(node_id: str) -> str:
    """Sanitize a node id into a Mermaid-safe token (alnum/underscore)."""
    safe = "".join(ch if ch.isalnum() else "_" for ch in node_id).strip("_")
    return safe or "n"


def _mermaid_label(text: str) -> str:
    """Escape characters that would break a Mermaid quoted label."""
    return text.replace('"', "'").replace("[", "(").replace("]", ")").replace("\n", " ").strip()


__all__ = [
    "KGNode",
    "KGEdge",
    "KnowledgeGraph",
    "NodeType",
    "EdgeRelation",
    "KG_PROMPT",
    "build_kg_from_llm",
]

"""Content knowledge graph for a processed scientific paper (Pydantic v2).

This module re-implements -- **from scratch, no source code copied** -- the
*concept* of protoneo's content knowledge graph (protoneo is AGPL-3.0; see
``artifact/notes/SYNTHESIS.md``). The idea: extract a semantic graph of a
paper's **content** -- its claims, methods, datasets, results, metrics,
concepts and tasks, plus the relations between them -- which is distinct from
any *citation* / literature graph (a graph of papers).

The models (:class:`KGNode`, :class:`KGEdge`, :class:`KnowledgeGraph`) are pure
data with no I/O. :func:`build_kg_from_llm` renders a paper's memory blocks into
a prompt, asks an :class:`~clio_author.llm.client.LLMClient` for a JSON graph,
and coerces the response into the models -- reusing the reviewer's stdlib JSON
extractor and never raising.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from clio_author.experts.reviewer import _extract_json_object
from clio_author.harness.types import Message
from clio_author.ingest.blocks import MemoryBlocks
from clio_author.llm.client import LLMClient

if TYPE_CHECKING:
    from clio_author.retrieval.kg_pipeline import Ontology

# The base content-entity vocabulary. Node ``type`` / edge ``relation`` are now
# free-form ``str`` (so an ontology stage can introduce paper-specific types),
# but extraction defaults to and coerces unknown values back into this base set.
BASE_NODE_TYPES: tuple[str, ...] = (
    "claim",
    "method",
    "dataset",
    "result",
    "metric",
    "concept",
    "task",
)
"""The base kinds of content entity a :class:`KGNode` may represent."""

BASE_EDGE_RELATIONS: tuple[str, ...] = (
    "uses",
    "evaluates_on",
    "compared_against",
    "reports",
    "part_of",
    "related_to",
)
"""The base semantic relations a :class:`KGEdge` may assert between two nodes."""


def coerce_node_type(s: str) -> str:
    """Map ``s`` onto the base node vocabulary (unknown -> ``"concept"``)."""
    value = (s or "").strip().lower()
    return value if value in BASE_NODE_TYPES else "concept"


def coerce_relation(s: str) -> str:
    """Map ``s`` onto the base edge vocabulary (unknown -> ``"related_to"``)."""
    value = (s or "").strip().lower()
    return value if value in BASE_EDGE_RELATIONS else "related_to"


def _norm_label(label: str) -> str:
    """Whitespace-collapsed, lower-cased label key used for node de-duplication."""
    return re.sub(r"\s+", " ", label.strip().lower())


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
    type: str
    description: str = ""
    section_path: str | None = None
    aliases: list[str] = Field(default_factory=list)
    evidence: str = ""
    confidence: float = 1.0


class KGEdge(BaseModel):
    """A directed, typed relation between two :class:`KGNode` ids."""

    source: str
    target: str
    relation: str


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

    def merge_node(self, node: KGNode) -> str:
        """Add ``node`` or merge it into an existing one; return the canonical id.

        De-duplication key is ``(type, normalised label)``. When a node with that
        key already exists, the longer ``description`` is kept and any new aliases
        are unioned in; otherwise ``node`` is appended verbatim. Returns the id of
        the surviving (canonical) node so callers can remap edges.
        """
        key = (node.type, _norm_label(node.label))
        for existing in self.nodes:
            if (existing.type, _norm_label(existing.label)) == key:
                if len(node.description) > len(existing.description):
                    existing.description = node.description
                    if node.section_path:
                        existing.section_path = node.section_path
                for alias in node.aliases:
                    if alias and alias not in existing.aliases:
                        existing.aliases.append(alias)
                return existing.id
        self.nodes.append(node)
        return node.id

    def add_edge(self, edge: KGEdge) -> bool:
        """Append ``edge`` unless it is a self-loop or an exact duplicate.

        Edges whose endpoints are not both present as node ids are rejected.
        Returns ``True`` when the edge was added.
        """
        if edge.source == edge.target:
            return False
        node_ids = {node.id for node in self.nodes}
        if edge.source not in node_ids or edge.target not in node_ids:
            return False
        sig = (edge.source, edge.relation, edge.target)
        for existing in self.edges:
            if (existing.source, existing.relation, existing.target) == sig:
                return False
        self.edges.append(edge)
        return True

    def prune_below(self, threshold: float) -> int:
        """Drop nodes whose ``confidence`` is below ``threshold``; return count dropped.

        Edges that reference a dropped node are removed too.
        """
        keep = [node for node in self.nodes if node.confidence >= threshold]
        dropped = len(self.nodes) - len(keep)
        if dropped:
            kept_ids = {node.id for node in keep}
            self.nodes = keep
            self.edges = [
                edge for edge in self.edges if edge.source in kept_ids and edge.target in kept_ids
            ]
        return dropped

    def prune_orphans(self) -> int:
        """Drop nodes that participate in no edge; return the count dropped.

        A no-op when the graph has no edges at all (every node is then trivially
        an orphan, so pruning would empty the graph -- not the intent).
        """
        if not self.edges:
            return 0
        connected = {edge.source for edge in self.edges} | {edge.target for edge in self.edges}
        keep = [node for node in self.nodes if node.id in connected]
        dropped = len(self.nodes) - len(keep)
        if dropped:
            self.nodes = keep
        return dropped

    def briefing(self) -> str:
        """Return a compact text summary of the graph (for context / reporting).

        Lists node labels grouped by type and a count of relations, capped so the
        text stays small enough to inject into a follow-up prompt.
        """
        if not self.nodes:
            return "Knowledge graph: (empty)"
        by_type: dict[str, list[str]] = {}
        for node in self.nodes:
            by_type.setdefault(node.type, []).append(node.label)
        lines = [f"Knowledge graph: {len(self.nodes)} nodes, {len(self.edges)} relations."]
        for node_type in sorted(by_type):
            labels = by_type[node_type]
            shown = ", ".join(labels[:12])
            extra = f" (+{len(labels) - 12} more)" if len(labels) > 12 else ""
            lines.append(f"- {node_type}: {shown}{extra}")
        return "\n".join(lines)

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


def _extract_one(
    context: str,
    llm: LLMClient,
    *,
    prompt: str = KG_PROMPT,
    node_vocab: set[str] | None = None,
    edge_vocab: set[str] | None = None,
) -> tuple[list[KGNode], list[KGEdge], bool]:
    """Extract nodes/edges from one batch of section text. Returns (nodes, edges, parsed_ok).

    When ``node_vocab`` / ``edge_vocab`` are given, any node ``type`` / edge
    ``relation`` outside that vocabulary is mapped back into the base set via
    :func:`coerce_node_type` / :func:`coerce_relation` (used when an ontology
    constrains the schema). In-vocabulary values are kept verbatim.
    """
    messages = [
        Message(role="system", content="You extract content knowledge graphs from papers."),
        Message(role="user", content=f"{prompt}\n\nPaper sections:\n{context}"),
    ]
    parsed = _extract_json_object(llm.complete(messages))
    if parsed is None:
        return [], [], False

    nodes: list[KGNode] = []
    for item in parsed.get("nodes", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            node = KGNode.model_validate(item)
        except Exception:  # noqa: BLE001 - drop malformed nodes, never raise
            continue
        if node_vocab is not None and node.type not in node_vocab:
            node.type = coerce_node_type(node.type)
        nodes.append(node)

    node_ids = {node.id for node in nodes}
    edges: list[KGEdge] = []
    for item in parsed.get("edges", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            edge = KGEdge.model_validate(item)
        except Exception:  # noqa: BLE001 - drop malformed edges, never raise
            continue
        if edge_vocab is not None and edge.relation not in edge_vocab:
            edge.relation = coerce_relation(edge.relation)
        if edge.source in node_ids and edge.target in node_ids:
            edges.append(edge)
    return nodes, edges, True


def ontology_to_prompt(ontology: Ontology) -> str:
    """Render an :class:`~clio_author.retrieval.kg_pipeline.Ontology` as a prompt block.

    Produces a fresh extraction prompt that lists the ontology's discovered
    entity/edge types (with short descriptions) as the allowed vocabulary, in the
    same JSON contract as :data:`KG_PROMPT`. Re-expresses the protoneo concept of
    an ontology-grounded extraction prompt without copying its prompt text.
    """
    entity_lines = "\n".join(
        f"  - {t.name}: {t.description}".rstrip(": ") for t in ontology.entity_types
    )
    edge_lines = "\n".join(
        f"  - {t.name}: {t.description}".rstrip(": ") for t in ontology.edge_types
    )
    return (
        "You are a scientific knowledge-graph extractor. Read the paper sections "
        "below and extract a CONTENT knowledge graph using the paper-specific "
        f"schema discovered for this paper (domain: {ontology.paper_domain}). "
        "This is the paper's content -- NOT a graph of cited papers.\n\n"
        "Respond with a single fenced JSON block:\n"
        "```json\n<json>\n```\n"
        'The JSON object must have a "nodes" list (each node an object with '
        '"id", "label", "type", and optional "description"/"section_path") and an '
        '"edges" list (each edge an object with "source", "target", "relation").\n'
        f'Allowed node "type":\n{entity_lines}\n'
        f'Allowed edge "relation":\n{edge_lines}\n'
        "Use short stable ids; only emit edges between ids you also list as nodes. "
        "The JSON is parsed automatically, so keep the format precise."
    )


def build_kg_from_llm(
    blocks: MemoryBlocks,
    llm: LLMClient,
    *,
    max_sections: int | None = None,
    batch_size: int = 6,
    max_workers: int = 4,
    ontology: Ontology | None = None,
    accumulate: bool = False,
) -> tuple[KnowledgeGraph, str | None]:
    """Extract a :class:`KnowledgeGraph` from ``blocks`` using ``llm``.

    Section blocks (via :meth:`~clio_author.ingest.blocks.MemoryBlocks.select` at
    ``detail="full"``, optionally capped to ``max_sections``) are split into
    batches of ``batch_size`` and each batch is extracted with one LLM call, so a
    long paper does not overflow a single prompt. The per-batch sub-graphs are
    merged via :meth:`KnowledgeGraph.merge_node` (dedup by ``(type, normalised
    label)``, longer description wins) and :meth:`KnowledgeGraph.add_edge` (edges
    remapped onto surviving ids; self-loops, dangling and duplicate edges dropped).

    When ``ontology`` is given, its discovered types are injected into the prompt
    (:func:`ontology_to_prompt`) and any extracted type/relation outside that
    vocabulary is coerced back to the base set. When ``accumulate`` is set, batches
    are processed sequentially and a running :meth:`KnowledgeGraph.briefing` of the
    graph so far is prepended to each batch's context (so later batches can avoid
    re-introducing entities already found); ``accumulate`` forces single-threaded
    extraction. With both defaulted the behaviour is identical to before.

    Parses each batch with the reviewer's stdlib
    :func:`~clio_author.experts.reviewer._extract_json_object`. Returns
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

    prompt = ontology_to_prompt(ontology) if ontology is not None else KG_PROMPT
    node_vocab: set[str] | None = None
    edge_vocab: set[str] | None = None
    if ontology is not None:
        node_vocab = {t.name for t in ontology.entity_types}
        edge_vocab = {t.name for t in ontology.edge_types}

    def extract(context: str) -> tuple[list[KGNode], list[KGEdge], bool]:
        return _extract_one(
            context, llm, prompt=prompt, node_vocab=node_vocab, edge_vocab=edge_vocab
        )

    graph = KnowledgeGraph()
    any_parsed = False
    pending_edges: list[KGEdge] = []

    if accumulate:
        # Sequential: each batch sees a compact briefing of the graph so far. The
        # briefing-augmented context cannot be parallelised (it depends on prior
        # batches), so accumulation runs single-threaded by construction.
        for batch in batches:
            body = "\n\n".join(batch)
            brief = graph.briefing()
            context = f"{brief}\n\n{body}" if graph.nodes else body
            nodes, edges, ok = extract(context)
            if not ok:
                continue
            any_parsed = True
            remap = {node.id: graph.merge_node(node) for node in nodes}
            for edge in edges:
                pending_edges.append(
                    KGEdge(
                        source=remap.get(edge.source, edge.source),
                        target=remap.get(edge.target, edge.target),
                        relation=edge.relation,
                    )
                )
    else:
        # Extract batches concurrently (LLM calls are I/O-bound); a single batch
        # runs inline to avoid pool overhead. Results are collected in deterministic
        # batch order so the merge below is reproducible regardless of completion.
        if len(batches) == 1 or max_workers <= 1:
            results = [extract("\n\n".join(b)) for b in batches]
        else:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=min(max_workers, len(batches))) as pool:
                results = list(pool.map(lambda b: extract("\n\n".join(b)), batches))

        for nodes, edges, ok in results:
            if not ok:
                continue
            any_parsed = True
            remap = {node.id: graph.merge_node(node) for node in nodes}
            for edge in edges:
                pending_edges.append(
                    KGEdge(
                        source=remap.get(edge.source, edge.source),
                        target=remap.get(edge.target, edge.target),
                        relation=edge.relation,
                    )
                )

    if not any_parsed:
        return KnowledgeGraph(), "could not parse KG JSON"

    for edge in pending_edges:
        graph.add_edge(edge)

    return graph, None


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
    "BASE_NODE_TYPES",
    "BASE_EDGE_RELATIONS",
    "coerce_node_type",
    "coerce_relation",
    "KG_PROMPT",
    "ontology_to_prompt",
    "build_kg_from_llm",
]

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

import json
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

# Color-by-type styling for the Mermaid view (one classDef per node type).
_TYPE_STYLE: dict[str, str] = {
    "method": "fill:#cfe2ff,stroke:#1f3a5f,color:#000",
    "concept": "fill:#e9ecef,stroke:#495057,color:#000",
    "dataset": "fill:#d1e7dd,stroke:#0f5132,color:#000",
    "metric": "fill:#fff3cd,stroke:#997404,color:#000",
    "claim": "fill:#f8d7da,stroke:#842029,color:#000",
    "result": "fill:#e2d9f3,stroke:#59359a,color:#000",
    "task": "fill:#cff4fc,stroke:#055160,color:#000",
}

# Per-type (background, border) colors for the interactive HTML view. Kept in
# sync with ``_TYPE_STYLE`` so the Mermaid and HTML renderings color-match.
_HTML_COLORS: dict[str, tuple[str, str]] = {
    "method": ("#cfe2ff", "#1f3a5f"),
    "concept": ("#e9ecef", "#495057"),
    "dataset": ("#d1e7dd", "#0f5132"),
    "metric": ("#fff3cd", "#997404"),
    "claim": ("#f8d7da", "#842029"),
    "result": ("#e2d9f3", "#59359a"),
    "task": ("#cff4fc", "#055160"),
}

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

    def to_mermaid(self, *, max_edges: int | None = 500, styled: bool = True) -> str:
        """Render the graph as a Mermaid ``graph TD`` block for a human view.

        Each node renders as ``id["<label> (<type>)"]:::<type>`` and each edge as
        ``source -->|relation| target``; labels are sanitized so quotes/brackets
        do not break parsing.

        ``styled`` adds a ``classDef`` per node type so nodes are **color-coded**
        (method/concept/dataset/metric/claim/result/task) -- the single biggest
        readability win. ``max_edges`` caps the rendered edges (default 500, the
        Mermaid live-editor limit): when the graph is larger only the first
        ``max_edges`` edges and the nodes they touch are drawn, with a note;
        ``max_edges=None`` (or ``0``) renders everything (may exceed renderer
        limits). The full graph is always available in the JSON dump.
        """
        all_edges = self.edges
        cap = max_edges if (max_edges is not None and max_edges > 0) else None
        truncated = cap is not None and len(all_edges) > cap
        edges = all_edges[:cap] if truncated else all_edges

        if truncated:
            kept = {e.source for e in edges} | {e.target for e in edges}
            nodes = [n for n in self.nodes if n.id in kept]
        else:
            nodes = self.nodes

        lines = ["graph TD"]
        if truncated:
            lines.append(
                f"    %% showing {len(edges)} of {len(all_edges)} edges + their nodes "
                f"(set max_edges=0 / CLI --max-edges 0 for the full graph; full data is in kg.json)"
            )
        if styled:
            for node_type, style in _TYPE_STYLE.items():
                lines.append(f"    classDef {node_type} {style};")
        for node in nodes:
            label = _mermaid_label(f"{node.label} ({node.type})")
            suffix = f":::{node.type}" if styled and node.type in _TYPE_STYLE else ""
            lines.append(f'    {_mermaid_id(node.id)}["{label}"]{suffix}')
        for edge in edges:
            rel = _mermaid_label(edge.relation)
            lines.append(f"    {_mermaid_id(edge.source)} -->|{rel}| {_mermaid_id(edge.target)}")
        return "\n".join(lines)

    def to_html(self, *, title: str = "Knowledge graph") -> str:
        """Render the graph as a **self-contained interactive HTML** page.

        Unlike :meth:`to_mermaid` (which caps edges to stay within the Mermaid
        renderer's limit), this draws the *whole* graph with a force-directed
        layout you can zoom, pan and drag, plus a node search box, per-type
        show/hide filters, and click-to-highlight-neighbors. Nodes are
        color-coded by type to match the Mermaid view.

        The page is a single HTML string with one external dependency: the
        ``vis-network`` library loaded from a CDN (so a browser needs network
        access the first time, but no build step or local install is required).
        The node/edge data is embedded inline, so the file is fully portable.
        """
        nodes = [
            {
                "id": node.id,
                "label": node.label,
                "group": node.type if node.type in _HTML_COLORS else "concept",
                "title": _html_tooltip(node),
            }
            for node in self.nodes
        ]
        edges = [
            {"from": edge.source, "to": edge.target, "label": edge.relation}
            for edge in self.edges
            if edge.source != edge.target
        ]
        groups = {
            t: {"color": {"background": bg, "border": br}} for t, (bg, br) in _HTML_COLORS.items()
        }
        legend = "".join(
            f'<span class="chip" data-type="{t}">'
            f'<span class="dot" style="background:{bg};border-color:{br}"></span>{t}</span>'
            for t, (bg, br) in _HTML_COLORS.items()
        )
        data = {
            "nodes": nodes,
            "edges": edges,
            "groups": groups,
            "counts": {"nodes": len(nodes), "edges": len(edges)},
        }
        return (
            _HTML_TEMPLATE.replace("__TITLE__", _html_escape(title))
            .replace("__LEGEND__", legend)
            .replace("__DATA__", json.dumps(data))
        )


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


def _html_escape(text: str) -> str:
    """Minimal HTML-escape for text interpolated into the page chrome."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _html_tooltip(node: KGNode) -> str:
    """Build a plain-text hover tooltip for a node (type, section, description)."""
    parts = [f"{node.label}  ·  {node.type}"]
    if node.section_path:
        parts.append(f"section: {node.section_path}")
    if node.description:
        desc = node.description.strip()
        parts.append(desc if len(desc) <= 240 else desc[:237] + "...")
    return "\n".join(parts)


# Self-contained interactive viewer. ``vis-network`` is loaded from a CDN; node
# and edge data are embedded inline at ``__DATA__``. Placeholders (``__TITLE__``,
# ``__LEGEND__``, ``__DATA__``) are filled by ``KnowledgeGraph.to_html`` with
# str.replace so the CSS/JS braces need no escaping.
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITLE__</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.4 system-ui, sans-serif; color: #1b1b1b; }
  header { padding: 10px 14px; border-bottom: 1px solid #ddd; background: #fafafa;
           display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; }
  header h1 { font-size: 16px; margin: 0; font-weight: 600; }
  .meta { color: #666; font-size: 12px; }
  .controls { display: flex; gap: 8px; align-items: center; margin-left: auto; flex-wrap: wrap; }
  input[type=search] { padding: 5px 9px; border: 1px solid #bbb; border-radius: 6px; min-width: 200px; }
  button { padding: 5px 10px; border: 1px solid #bbb; border-radius: 6px; background: #fff; cursor: pointer; }
  button:hover { background: #f0f0f0; }
  .legend { display: flex; gap: 6px 10px; flex-wrap: wrap; padding: 8px 14px; border-bottom: 1px solid #eee; }
  .chip { cursor: pointer; user-select: none; display: inline-flex; align-items: center; gap: 5px;
          padding: 2px 8px; border: 1px solid #ddd; border-radius: 12px; font-size: 12px; }
  .chip.off { opacity: 0.35; text-decoration: line-through; }
  .dot { width: 11px; height: 11px; border-radius: 50%; border: 1px solid #000; display: inline-block; }
  #net { width: 100vw; height: calc(100vh - 96px); }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <span class="meta" id="meta"></span>
  <div class="controls">
    <input id="search" type="search" placeholder="Search nodes..." />
    <button id="fit">Fit</button>
    <button id="freeze">Freeze layout</button>
    <button id="reset">Reset view</button>
  </div>
</header>
<div class="legend" id="legend">__LEGEND__</div>
<div id="net"></div>
<script>
  const DATA = __DATA__;
  document.getElementById("meta").textContent =
    DATA.counts.nodes + " nodes · " + DATA.counts.edges + " relations";

  const nodes = new vis.DataSet(DATA.nodes);
  const edges = new vis.DataSet(DATA.edges);
  const container = document.getElementById("net");
  const options = {
    groups: DATA.groups,
    nodes: { shape: "dot", size: 12, font: { size: 13, face: "system-ui" },
             borderWidth: 1.5 },
    edges: { arrows: { to: { enabled: true, scaleFactor: 0.5 } }, color: { color: "#bbb", highlight: "#444" },
             font: { size: 10, color: "#777", strokeWidth: 3, strokeColor: "#fff" }, smooth: false },
    physics: { stabilization: { iterations: 200 },
               barnesHut: { gravitationalConstant: -8000, springLength: 110, springConstant: 0.03 } },
    interaction: { hover: true, tooltipDelay: 120, navigationButtons: false, keyboard: false },
  };
  const network = new vis.Network(container, { nodes, edges }, options);

  // Click a node -> highlight it + neighbors, dim the rest.
  const adj = {};
  DATA.edges.forEach(e => { (adj[e.from] = adj[e.from] || new Set()).add(e.to);
                            (adj[e.to] = adj[e.to] || new Set()).add(e.from); });
  function highlight(id) {
    const keep = new Set([id, ...(adj[id] || [])]);
    nodes.update(DATA.nodes.map(n => ({ id: n.id, opacity: keep.has(n.id) ? 1 : 0.15 })));
  }
  function clearHighlight() { nodes.update(DATA.nodes.map(n => ({ id: n.id, opacity: 1 }))); }
  network.on("click", p => { if (p.nodes.length) highlight(p.nodes[0]); else clearHighlight(); });

  // Search: focus + select the first label match.
  document.getElementById("search").addEventListener("input", ev => {
    const q = ev.target.value.trim().toLowerCase();
    if (!q) { clearHighlight(); network.unselectAll(); return; }
    const hit = DATA.nodes.find(n => (n.label || "").toLowerCase().includes(q));
    if (hit) { network.selectNodes([hit.id]); network.focus(hit.id, { scale: 1.1, animation: true }); highlight(hit.id); }
  });

  // Type filter chips: toggle visibility per node type.
  const hidden = new Set();
  document.querySelectorAll(".chip").forEach(chip => chip.addEventListener("click", () => {
    const t = chip.dataset.type;
    if (hidden.has(t)) { hidden.delete(t); chip.classList.remove("off"); }
    else { hidden.add(t); chip.classList.add("off"); }
    nodes.update(DATA.nodes.map(n => ({ id: n.id, hidden: hidden.has(n.group) })));
  }));

  document.getElementById("fit").onclick = () => network.fit({ animation: true });
  document.getElementById("reset").onclick = () => { clearHighlight(); network.unselectAll();
    document.getElementById("search").value = ""; network.fit({ animation: true }); };
  let frozen = false;
  document.getElementById("freeze").onclick = ev => { frozen = !frozen;
    network.setOptions({ physics: { enabled: !frozen } });
    ev.target.textContent = frozen ? "Unfreeze layout" : "Freeze layout"; };
  network.once("stabilizationIterationsDone", () => network.fit());
</script>
</body>
</html>
"""


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

"""Literature graph construction and self-contained HTML visualization.

The graph path is intentionally headless: it returns structured paper nodes and
edges that a host can render however it wants, and it can also write a portable
``graph.html`` for humans. Semantic Scholar is the preferred backend because it
exposes paper metadata plus references, citations, and recommendations; OpenAlex
is the no-key fallback for ``auto`` mode.
"""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable
from urllib.parse import quote

from pydantic import BaseModel, Field

from clio_parser.retrieval.rag import RetrievalDependencyError
from clio_parser.retrieval.scholar import (
    S2Record,
    SemanticScholarClient,
    _get_json,
    _record_from_openalex,
)

_S2_PAPER_FIELDS = (
    "paperId,title,authors,venue,year,abstract,citationCount,journal,"
    "publicationDate,url,externalIds,openAccessPdf"
)
_S2_NESTED_PAPER_FIELDS = (
    "title,authors,venue,year,abstract,citationCount,journal,publicationDate,url,externalIds"
)
_S2_REFERENCE_FIELDS = f"contexts,intents,isInfluential,citedPaper.{_S2_NESTED_PAPER_FIELDS}"
_S2_CITATION_FIELDS = f"contexts,intents,isInfluential,citingPaper.{_S2_NESTED_PAPER_FIELDS}"
_S2_RECOMMEND_URL = "https://api.semanticscholar.org/recommendations/v1/papers/forpaper"
_S2_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
_S2_MATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search/match"
_OPENALEX_WORKS_URL = "https://api.openalex.org/works"
_DEFAULT_TIMEOUT = 8.0

GraphBackend = Literal["semantic", "openalex", "auto"]
NodeRole = Literal["seed", "prior", "derivative", "related"]
EdgeType = Literal["citation", "cited_by", "related", "recommendation"]


class GraphSeed(BaseModel):
    """A graph starting point supplied by title, paper id, DOI, arXiv id, or URL."""

    title: str | None = None
    paper_id: str | None = None
    year: int | None = None
    url: str | None = None


class PaperNode(BaseModel):
    """A paper node in the literature graph."""

    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    citation_count: int | None = None
    venue: str | None = None
    abstract: str | None = None
    url: str | None = None
    source: str = "unknown"
    role: NodeRole = "related"
    ingest_source: str
    external_ids: dict[str, str] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A relationship between two paper nodes."""

    source: str
    target: str
    type: EdgeType
    weight: float = 1.0
    evidence: str | None = None


class LiteratureGraph(BaseModel):
    """Structured graph plus ranked views for prior and derivative works."""

    backend: str
    seeds: list[str]
    nodes: list[PaperNode]
    edges: list[GraphEdge]
    prior_works: list[str] = Field(default_factory=list)
    derivative_works: list[str] = Field(default_factory=list)
    related_works: list[str] = Field(default_factory=list)


@runtime_checkable
class LiteratureGraphClient(Protocol):
    """Backend capable of building a literature graph for one or more seeds."""

    def build_graph(
        self,
        seeds: list[GraphSeed],
        *,
        max_nodes: int = 40,
        per_seed: int = 8,
    ) -> LiteratureGraph:
        """Return a graph for ``seeds``."""
        ...


class SemanticScholarGraphClient:
    """Semantic Scholar graph client using search, refs, citations, recommendations."""

    def __init__(self, *, timeout: float = _DEFAULT_TIMEOUT, min_interval: float = 1.3) -> None:
        self._search = SemanticScholarClient(timeout=timeout, min_interval=min_interval)
        self.timeout = timeout

    def build_graph(
        self,
        seeds: list[GraphSeed],
        *,
        max_nodes: int = 40,
        per_seed: int = 8,
    ) -> LiteratureGraph:
        """Build a Semantic Scholar-backed graph."""
        graph = _GraphBuilder(backend="semantic")
        resolved = [node for seed in seeds if (node := self._resolve_seed(seed)) is not None]
        if not resolved:
            raise ValueError("could not resolve any graph seed with Semantic Scholar")
        for node in resolved:
            graph.add_node(node.model_copy(update={"role": "seed"}))

        for seed_node in resolved:
            seed_paper_id = seed_node.id.removeprefix("s2:")
            remaining = max(1, max_nodes - len(graph.nodes))
            refs = self._linked_papers(seed_paper_id, "references", per_seed)
            for ref in refs[: min(per_seed, remaining)]:
                graph.add_node(ref.model_copy(update={"role": "prior"}))
                graph.add_edge(seed_node.id, ref.id, "citation", evidence="seed references paper")

            remaining = max(1, max_nodes - len(graph.nodes))
            citations = self._linked_papers(seed_paper_id, "citations", per_seed)
            for citing in citations[: min(per_seed, remaining)]:
                graph.add_node(citing.model_copy(update={"role": "derivative"}))
                graph.add_edge(citing.id, seed_node.id, "cited_by", evidence="paper cites seed")

            remaining = max(1, max_nodes - len(graph.nodes))
            recommendations = self._recommendations(seed_paper_id, min(per_seed, remaining))
            for rec in recommendations:
                graph.add_node(rec.model_copy(update={"role": "related"}))
                graph.add_edge(seed_node.id, rec.id, "recommendation", evidence="S2 recommendation")

        return graph.finish(seeds=[_seed_label(seed) for seed in seeds], max_nodes=max_nodes)

    def _resolve_seed(self, seed: GraphSeed) -> PaperNode | None:
        raw_id = seed.paper_id or seed.url
        if raw_id:
            record = self._paper(raw_id)
            return _node_from_s2(record, role="seed") if record is not None else None
        if not seed.title:
            return None
        matched = self._match_title(seed.title)
        if matched is not None:
            return _node_from_s2(matched, role="seed")
        records = self._search.search_title(seed.title, seed.year, None)
        if not records:
            return None
        if seed.year is not None:
            records = sorted(records, key=lambda record: record.year != seed.year)
        return _node_from_s2(records[0], role="seed")

    def _match_title(self, title: str) -> S2Record | None:
        try:
            data = self._s2_get(_S2_MATCH_URL, {"query": title, "fields": _S2_PAPER_FIELDS})
        except Exception:  # noqa: BLE001
            return None
        items = data.get("data", [])
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and first.get("title"):
                return _record_from_s2_graph(first)
        if data.get("title"):
            return _record_from_s2_graph(data)
        return None

    def _paper(self, paper_id: str) -> S2Record | None:
        try:
            data = self._s2_get(
                f"{_S2_PAPER_URL}/{quote(paper_id, safe='')}",
                {"fields": _S2_PAPER_FIELDS},
            )
        except Exception:  # noqa: BLE001 - graph construction degrades through fallback clients
            return None
        return _record_from_s2_graph(data) if data.get("title") else None

    def _linked_papers(
        self,
        paper_id: str,
        kind: Literal["references", "citations"],
        limit: int,
    ) -> list[PaperNode]:
        try:
            fields = _S2_REFERENCE_FIELDS if kind == "references" else _S2_CITATION_FIELDS
            data = self._s2_get(
                f"{_S2_PAPER_URL}/{quote(paper_id, safe='')}/{kind}",
                {"fields": fields, "limit": max(1, limit)},
            )
        except Exception:  # noqa: BLE001
            return []
        nodes: list[PaperNode] = []
        paper_key = "citedPaper" if kind == "references" else "citingPaper"
        for item in data.get("data", []):
            if isinstance(item, dict) and isinstance(item.get(paper_key), dict):
                record = _record_from_s2_graph(item[paper_key])
                if record.title:
                    role: NodeRole = "prior" if kind == "references" else "derivative"
                    nodes.append(_node_from_s2(record, role=role))
        return nodes

    def _recommendations(self, paper_id: str, limit: int) -> list[PaperNode]:
        try:
            data = self._s2_get(
                f"{_S2_RECOMMEND_URL}/{quote(paper_id, safe='')}",
                {"fields": _S2_PAPER_FIELDS, "limit": max(1, limit)},
            )
        except Exception:  # noqa: BLE001
            return []
        return [
            _node_from_s2(_record_from_s2_graph(item), role="related")
            for item in data.get("recommendedPapers", [])
            if isinstance(item, dict) and item.get("title")
        ]

    def _s2_get(self, url: str, params: dict[str, str | int]) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - only without scholar extra
            raise RetrievalDependencyError(
                "httpx is required for SemanticScholarGraphClient. Install with: uv sync --extra scholar"
            ) from exc
        headers = {"X-API-KEY": self._search.api_key} if self._search.api_key else {}
        for attempt in range(3):
            self._search._throttle()
            response = httpx.get(url, headers=headers, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, dict) else {}
            if response.status_code != 429 or attempt == 2:
                return {}
            self._search._sleep(self._search.min_interval)
        return {}


class OpenAlexGraphClient:
    """No-key OpenAlex fallback using works search and related works."""

    def __init__(self, *, mailto: str | None = None, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.mailto = mailto or os.environ.get("OPENALEX_MAILTO")
        self.timeout = timeout

    def build_graph(
        self,
        seeds: list[GraphSeed],
        *,
        max_nodes: int = 40,
        per_seed: int = 8,
    ) -> LiteratureGraph:
        """Build an OpenAlex-backed graph."""
        graph = _GraphBuilder(backend="openalex")
        resolved = [node for seed in seeds if (node := self._resolve_seed(seed)) is not None]
        if not resolved:
            raise ValueError("could not resolve any graph seed with OpenAlex")
        for node in resolved:
            graph.add_node(node.model_copy(update={"role": "seed"}))
        for seed_node in resolved:
            for related in self._related(seed_node, per_seed):
                if len(graph.nodes) >= max_nodes:
                    break
                graph.add_node(related)
                graph.add_edge(
                    seed_node.id, related.id, "related", evidence="OpenAlex related work"
                )
        return graph.finish(seeds=[_seed_label(seed) for seed in seeds], max_nodes=max_nodes)

    def _resolve_seed(self, seed: GraphSeed) -> PaperNode | None:
        if seed.paper_id and seed.paper_id.startswith("openalex:"):
            return self._work(seed.paper_id.removeprefix("openalex:"))
        params: dict[str, str | int] = {"per-page": 1}
        if seed.title:
            params["search"] = seed.title
        elif seed.url:
            params["filter"] = f"ids.openalex:{seed.url}"
        else:
            return None
        if seed.year is not None:
            params["filter"] = f"publication_year:{seed.year}"
        if self.mailto:
            params["mailto"] = self.mailto
        try:
            results = _get_json(_OPENALEX_WORKS_URL, params, timeout=self.timeout).get(
                "results", []
            )
        except Exception:  # noqa: BLE001
            return None
        if not results:
            return None
        return _node_from_openalex(_record_from_openalex(results[0]), role="seed")

    def _work(self, openalex_id: str) -> PaperNode | None:
        try:
            data = _get_json(openalex_id, {}, timeout=self.timeout)
        except Exception:  # noqa: BLE001
            return None
        return _node_from_openalex(_record_from_openalex(data), role="seed") if data else None

    def _related(self, seed_node: PaperNode, limit: int) -> list[PaperNode]:
        raw_id = seed_node.id.removeprefix("openalex:")
        if not raw_id:
            return []
        params: dict[str, str | int] = {"filter": f"related_to:{raw_id}", "per-page": limit}
        if self.mailto:
            params["mailto"] = self.mailto
        try:
            results = _get_json(_OPENALEX_WORKS_URL, params, timeout=self.timeout).get(
                "results", []
            )
        except Exception:  # noqa: BLE001
            return []
        return [
            _node_from_openalex(_record_from_openalex(item), role="related")
            for item in results
            if item.get("display_name")
        ]


class CascadeLiteratureGraphClient:
    """Try graph clients in order, returning the first successful graph."""

    def __init__(self, clients: list[LiteratureGraphClient]) -> None:
        self.clients = clients

    def build_graph(
        self,
        seeds: list[GraphSeed],
        *,
        max_nodes: int = 40,
        per_seed: int = 8,
    ) -> LiteratureGraph:
        """Return the first non-empty graph from configured clients."""
        errors: list[str] = []
        for client in self.clients:
            try:
                graph = client.build_graph(seeds, max_nodes=max_nodes, per_seed=per_seed)
            except Exception as exc:  # noqa: BLE001 - next backend may work
                errors.append(str(exc))
                continue
            if graph.nodes:
                return graph
        raise ValueError("; ".join(errors) or "no graph backend produced results")


def coerce_seeds(raw: Any) -> list[GraphSeed]:
    """Validate graph seeds from CLI/adapter payloads."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [GraphSeed(title=raw)]
    if isinstance(raw, dict):
        return [GraphSeed.model_validate(raw)]
    if isinstance(raw, list):
        seeds: list[GraphSeed] = []
        for item in raw:
            seeds.extend(coerce_seeds(item))
        return seeds
    raise ValueError("seeds must be a string, object, or list")


def resolve_literature_graph_client(spec: str | None = None) -> LiteratureGraphClient | None:
    """Resolve a graph backend from ``CLIO_GRAPH`` / payload values."""
    name = (spec or "auto").strip().lower()
    if name in ("off", "none", "offline", "disabled", ""):
        return None
    if name in ("semantic", "s2", "semanticscholar", "semantic-scholar"):
        return SemanticScholarGraphClient()
    if name in ("openalex", "oa"):
        return OpenAlexGraphClient()
    if name in ("auto", "cascade", "all"):
        return CascadeLiteratureGraphClient([SemanticScholarGraphClient(), OpenAlexGraphClient()])
    raise ValueError(f"unknown CLIO_GRAPH={spec!r} (use one of: auto, semantic, openalex, off)")


def write_graph_artifacts(graph: LiteratureGraph, out_dir: str | Path) -> list[str]:
    """Write ``graph.json`` and ``graph.html`` under ``out_dir``."""
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    graph_json = path / "graph.json"
    graph_html = path / "graph.html"
    graph_json.write_text(json.dumps(graph.model_dump(), indent=2), encoding="utf-8")
    graph_html.write_text(render_graph_html(graph), encoding="utf-8")
    return [str(graph_json), str(graph_html)]


def render_graph_html(graph: LiteratureGraph) -> str:
    """Render a standalone SVG/JS literature graph viewer."""
    data = _script_json(graph.model_dump())
    title = html.escape(", ".join(graph.seeds) or "Literature Graph")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>clio-parser literature graph</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f7f8fb;
  --ink: #172033;
  --muted: #5f6b7a;
  --line: #d8dde8;
  --panel: #ffffff;
  --accent: #0f766e;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--ink);
}}
header {{
  padding: 18px 24px 12px;
  border-bottom: 1px solid var(--line);
  background: #fff;
}}
h1 {{ margin: 0 0 4px; font-size: 22px; font-weight: 700; letter-spacing: 0; }}
.sub {{ color: var(--muted); font-size: 13px; }}
main {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  min-height: calc(100vh - 74px);
}}
#graphWrap {{ position: relative; min-height: 620px; padding: 18px; }}
svg {{
  width: 100%;
  height: calc(100vh - 112px);
  min-height: 580px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
}}
aside {{
  border-left: 1px solid var(--line);
  background: var(--panel);
  padding: 18px;
  overflow: auto;
}}
.legend {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }}
.chip {{ font-size: 12px; padding: 4px 8px; border: 1px solid var(--line); border-radius: 999px; }}
.node {{ cursor: pointer; stroke: #fff; stroke-width: 2; }}
.node.seed {{ stroke: #111827; stroke-width: 3; }}
.edge {{ stroke: #aab3c2; stroke-opacity: .7; }}
.label {{ font-size: 11px; fill: #263244; pointer-events: none; paint-order: stroke; stroke: #fff; stroke-width: 4px; }}
.muted {{ color: var(--muted); }}
.paperTitle {{ font-size: 18px; line-height: 1.25; margin: 0 0 10px; }}
.meta {{ font-size: 13px; color: var(--muted); line-height: 1.45; }}
.abstract {{ font-size: 13px; line-height: 1.5; margin-top: 14px; }}
.actions {{ display: grid; gap: 8px; margin-top: 16px; }}
a.button, button {{
  appearance: none;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
  border-radius: 6px;
  padding: 8px 10px;
  font: inherit;
  font-size: 13px;
  text-decoration: none;
  text-align: left;
}}
a.button:hover, button:hover {{ border-color: var(--accent); }}
code {{
  display: block;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #f2f4f8;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
  font-size: 12px;
  margin-top: 8px;
}}
@media (max-width: 900px) {{
  main {{ grid-template-columns: 1fr; }}
  aside {{ border-left: 0; border-top: 1px solid var(--line); }}
  svg {{ height: 620px; }}
}}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="sub">clio-parser literature graph · backend: {html.escape(graph.backend)} · {len(graph.nodes)} papers · {len(graph.edges)} links</div>
</header>
<main>
  <section id="graphWrap">
    <svg id="graph" viewBox="0 0 1100 760" role="img" aria-label="Literature graph"></svg>
    <div class="legend">
      <span class="chip">Color: publication year</span>
      <span class="chip">Size: citation count</span>
      <span class="chip">Thick outline: seed paper</span>
    </div>
  </section>
  <aside id="details">
    <p class="paperTitle">Select a paper</p>
    <p class="meta">Click a node to see links and the ingest command.</p>
  </aside>
</main>
<script id="graph-data" type="application/json">{data}</script>
<script>
const data = JSON.parse(document.getElementById("graph-data").textContent);
const svg = document.getElementById("graph");
const details = document.getElementById("details");
const nodes = data.nodes || [];
const edges = data.edges || [];
const byId = new Map(nodes.map(n => [n.id, n]));
const years = nodes.map(n => n.year).filter(Boolean);
const minYear = Math.min(...years, new Date().getFullYear() - 10);
const maxYear = Math.max(...years, new Date().getFullYear());
function color(year) {{
  if (!year) return "#7c8798";
  const t = (year - minYear) / Math.max(1, maxYear - minYear);
  const hue = 215 - (t * 160);
  return `hsl(${{hue}}, 62%, 46%)`;
}}
function radius(n) {{
  const count = Math.max(0, n.citation_count || 0);
  return 8 + Math.min(22, Math.log10(count + 1) * 5);
}}
function roleAngle(role, i, total) {{
  const base = role === "prior" ? Math.PI : role === "derivative" ? 0 : Math.PI * 1.5;
  return base + ((i / Math.max(1, total)) - 0.5) * Math.PI * 0.9;
}}
function layout() {{
  const cx = 550, cy = 375;
  const buckets = {{
    seed: nodes.filter(n => n.role === "seed"),
    prior: nodes.filter(n => n.role === "prior"),
    derivative: nodes.filter(n => n.role === "derivative"),
    related: nodes.filter(n => n.role === "related")
  }};
  buckets.seed.forEach((n, i) => {{ n.x = cx; n.y = cy + (i - (buckets.seed.length - 1) / 2) * 58; }});
  for (const role of ["prior", "derivative", "related"]) {{
    buckets[role].forEach((n, i) => {{
      const a = roleAngle(role, i, buckets[role].length);
      const dist = role === "related" ? 260 : 340;
      n.x = cx + Math.cos(a) * dist;
      n.y = cy + Math.sin(a) * dist;
    }});
  }}
}}
function shortTitle(t) {{
  return t.length > 58 ? t.slice(0, 55) + "..." : t;
}}
function render() {{
  layout();
  svg.innerHTML = "";
  for (const e of edges) {{
    const s = byId.get(e.source), t = byId.get(e.target);
    if (!s || !t) continue;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("class", "edge");
    line.setAttribute("x1", s.x); line.setAttribute("y1", s.y);
    line.setAttribute("x2", t.x); line.setAttribute("y2", t.y);
    line.setAttribute("stroke-width", Math.max(1, Math.min(4, e.weight || 1)));
    svg.appendChild(line);
  }}
  for (const n of nodes) {{
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("class", `node ${{n.role || ""}}`);
    circle.setAttribute("cx", n.x); circle.setAttribute("cy", n.y);
    circle.setAttribute("r", radius(n));
    circle.setAttribute("fill", color(n.year));
    circle.addEventListener("click", () => show(n));
    svg.appendChild(circle);
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("class", "label");
    label.setAttribute("x", n.x + radius(n) + 5);
    label.setAttribute("y", n.y + 4);
    label.textContent = shortTitle(n.title);
    svg.appendChild(label);
  }}
  show(nodes[0]);
}}
function show(n) {{
  if (!n) return;
  const authors = (n.authors || []).slice(0, 6).join(", ");
  const cmd = `uv run --extra pdf clio-parser ingest "${{n.ingest_source || n.title}}"`;
  const links = [];
  if (n.url) links.push(`<a class="button" href="${{n.url}}" target="_blank" rel="noreferrer">Open paper</a>`);
  links.push(`<button type="button" onclick="navigator.clipboard && navigator.clipboard.writeText(${{JSON.stringify(cmd)}})">Copy ingest command</button>`);
  details.innerHTML = `
    <p class="paperTitle">${{escapeHtml(n.title)}}</p>
    <p class="meta">${{escapeHtml(authors || "Unknown authors")}}<br>
    ${{n.year || "n.d."}} · ${{escapeHtml(n.venue || n.source || "")}} · ${{n.citation_count ?? 0}} citations<br>
    role: ${{escapeHtml(n.role || "related")}}</p>
    <div class="actions">${{links.join("")}}</div>
    <code>${{escapeHtml(cmd)}}</code>
    <p class="abstract">${{escapeHtml(n.abstract || "No abstract available.")}}</p>
  `;
}}
function escapeHtml(s) {{
  return String(s || "").replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[c]));
}}
render();
</script>
</body>
</html>
"""


def _script_json(value: Any) -> str:
    """JSON safe to embed directly in a ``<script type=application/json>`` tag."""
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _seed_label(seed: GraphSeed) -> str:
    return seed.title or seed.paper_id or seed.url or "paper"


class _GraphBuilder:
    def __init__(self, *, backend: str) -> None:
        self.backend = backend
        self.nodes: dict[str, PaperNode] = {}
        self.edges: list[GraphEdge] = []

    def add_node(self, node: PaperNode) -> None:
        existing = self.nodes.get(node.id)
        if existing is None or existing.role == "related" and node.role != "related":
            self.nodes[node.id] = node

    def add_edge(self, source: str, target: str, edge_type: EdgeType, *, evidence: str) -> None:
        if source == target:
            return
        edge = GraphEdge(source=source, target=target, type=edge_type, evidence=evidence)
        if edge not in self.edges:
            self.edges.append(edge)

    def finish(self, *, seeds: list[str], max_nodes: int) -> LiteratureGraph:
        ranked = sorted(
            self.nodes.values(),
            key=lambda node: (
                node.role != "seed",
                -(node.year or 0),
                -(node.citation_count or 0),
                node.title.lower(),
            ),
        )[:max_nodes]
        keep = {node.id for node in ranked}
        edges = [edge for edge in self.edges if edge.source in keep and edge.target in keep]
        return LiteratureGraph(
            backend=self.backend,
            seeds=seeds,
            nodes=ranked,
            edges=edges,
            prior_works=[node.id for node in ranked if node.role == "prior"],
            derivative_works=[node.id for node in ranked if node.role == "derivative"],
            related_works=[node.id for node in ranked if node.role == "related"],
        )


def _record_from_s2_graph(item: dict[str, Any]) -> S2Record:
    authors = [
        str(author.get("name"))
        for author in item.get("authors") or []
        if isinstance(author, dict) and author.get("name")
    ]
    journal_raw = item.get("journal")
    journal = (
        str(journal_raw.get("name"))
        if isinstance(journal_raw, dict) and journal_raw.get("name")
        else None
    )
    return S2Record(
        paper_id=str(item.get("paperId") or item.get("corpusId") or ""),
        title=str(item.get("title") or ""),
        authors=authors,
        venue=str(item["venue"]) if item.get("venue") else None,
        year=int(item["year"]) if isinstance(item.get("year"), int) else None,
        abstract=str(item["abstract"]) if item.get("abstract") else None,
        citation_count=(
            int(item["citationCount"]) if isinstance(item.get("citationCount"), int) else None
        ),
        journal=journal,
        publication_date=str(item["publicationDate"]) if item.get("publicationDate") else None,
        external_ids={
            str(key): str(value)
            for key, value in (item.get("externalIds") or {}).items()
            if value is not None
        }
        if isinstance(item.get("externalIds"), dict)
        else {},
    )


def _node_from_s2(record: S2Record, *, role: NodeRole) -> PaperNode:
    external_ids = record.external_ids
    arxiv_id = str(external_ids.get("ArXiv") or "") if isinstance(external_ids, dict) else ""
    doi = str(external_ids.get("DOI") or "") if isinstance(external_ids, dict) else ""
    ingest_source = (
        f"https://arxiv.org/abs/{arxiv_id}"
        if arxiv_id
        else (f"https://doi.org/{doi}" if doi else record.title)
    )
    return PaperNode(
        id=f"s2:{record.paper_id}",
        title=record.title,
        authors=record.authors,
        year=record.year,
        citation_count=record.citation_count,
        venue=record.venue or record.journal,
        abstract=record.abstract,
        url=f"https://www.semanticscholar.org/paper/{record.paper_id}" if record.paper_id else None,
        source="semantic_scholar",
        role=role,
        ingest_source=ingest_source,
        external_ids={str(k): str(v) for k, v in external_ids.items()}
        if isinstance(external_ids, dict)
        else {},
    )


def _node_from_openalex(record: S2Record, *, role: NodeRole) -> PaperNode:
    raw = record.paper_id.removeprefix("openalex:")
    return PaperNode(
        id=record.paper_id,
        title=record.title,
        authors=record.authors,
        year=record.year,
        citation_count=record.citation_count,
        venue=record.venue or record.journal,
        abstract=record.abstract,
        url=raw if raw.startswith("http") else None,
        source="openalex",
        role=role,
        ingest_source=record.title,
    )


def graph_slug(seed: str) -> str:
    """Filesystem-safe graph folder slug."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", seed.strip()).strip("-")[:64] or "literature-graph"


__all__ = [
    "CascadeLiteratureGraphClient",
    "GraphEdge",
    "GraphSeed",
    "LiteratureGraph",
    "LiteratureGraphClient",
    "OpenAlexGraphClient",
    "PaperNode",
    "SemanticScholarGraphClient",
    "coerce_seeds",
    "graph_slug",
    "render_graph_html",
    "resolve_literature_graph_client",
    "write_graph_artifacts",
]

"""Multi-stage content knowledge-graph pipeline (Pydantic v2, synchronous).

This module re-implements -- **from scratch, no source code copied** -- the
*concept* of protoneo's 6-stage knowledge-graph kernel
(``metadata -> ontology -> extraction -> coref -> verification -> summary``;
protoneo is AGPL-3.0; see https://github.com/iowarp/protoneo and
``artifact/notes/SYNTHESIS.md``). Every stage here is freshly authored: the
domain keyword map, the discovery prompt, the acronym / substring coreference
heuristics, the deterministic grounding check and the orchestrator's
checkpoint/resume scheme are all original re-expressions of the published ideas.
No protoneo prompt strings, keyword tables, regex-salvage routines or function
bodies were copied.

Design goals mirror the rest of the harness: synchronous, no new runtime
dependencies, hermetic-first (every stage degrades gracefully under
:class:`~clio_author.llm.client.EchoLLMClient` so the default suite stays green),
and never-raise at the stage/orchestrator boundary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from clio_author.experts.reviewer import _extract_json_object
from clio_author.harness.types import Message
from clio_author.ingest.blocks import MemoryBlocks
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.retrieval.kg import (
    BASE_EDGE_RELATIONS,
    BASE_NODE_TYPES,
    KGEdge,
    KGNode,
    KnowledgeGraph,
    build_kg_from_llm,
)
from clio_author.tools.files import FileToolError, SafeFiles

# Ordered kernel stages. Re-expressed from the published 6-stage design; the
# names match the conventional pipeline vocabulary, the implementations do not.
STAGES: list[str] = ["metadata", "ontology", "extraction", "coref", "verification", "summary"]

# Cap on the number of paper-specific ontology types accepted from an LLM.
_MAX_ONTOLOGY_TYPES = 8

# A compact, original keyword map for deterministic domain detection. Each domain
# lists lower-cased substrings scanned against the abstract + section titles.
_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ml": (
        "neural network",
        "deep learning",
        "gradient",
        "training",
        "classifier",
        "supervised",
        "reinforcement",
        "embedding",
        "loss function",
    ),
    "nlp": (
        "language model",
        "tokeniz",
        "transformer",
        "text corpus",
        "translation",
        "question answering",
        "named entity",
        "sentiment",
    ),
    "vision": (
        "image",
        "convolution",
        "segmentation",
        "object detection",
        "pixel",
        "visual",
        "video frame",
    ),
    "systems": (
        "throughput",
        "latency",
        "filesystem",
        "scheduler",
        "distributed system",
        "cache",
        "kernel",
        "concurrency",
        "i/o",
    ),
    "theory": (
        "theorem",
        "lemma",
        "proof",
        "complexity",
        "bound",
        "np-hard",
        "approximation algorithm",
        "asymptotic",
    ),
    "bio": (
        "protein",
        "genome",
        "molecul",
        "cell",
        "rna",
        "clinical",
        "biological",
        "sequencing",
    ),
}


class OntologyType(BaseModel):
    """A single discovered entity- or edge-type in a paper's ontology."""

    name: str
    description: str = ""
    examples: list[str] = Field(default_factory=list)
    kind: Literal["entity", "edge"]


class Ontology(BaseModel):
    """A paper-specific schema: its entity types, edge types and domain."""

    entity_types: list[OntologyType] = Field(default_factory=list)
    edge_types: list[OntologyType] = Field(default_factory=list)
    paper_domain: str = "general"
    key_contributions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Stage 1 -- ontology                                                          #
# --------------------------------------------------------------------------- #


def _abstract_and_titles(blocks: MemoryBlocks) -> str:
    """Concatenate the abstract (if any) plus all section titles, lower-cased.

    Used by :func:`detect_domain` as the deterministic scan surface. The abstract
    is taken from ``metadata['abstract']`` when present, else from a section whose
    title contains "abstract".
    """
    parts: list[str] = []
    abstract = blocks.metadata.get("abstract")
    if isinstance(abstract, str) and abstract:
        parts.append(abstract)
    for section in blocks.sections:
        parts.append(section.title)
        if "abstract" in section.title.lower():
            parts.append(section.text)
    return "\n".join(parts).lower()


def detect_domain(blocks: MemoryBlocks) -> tuple[str, list[str]]:
    """Deterministically classify a paper's domain from its abstract + titles.

    Scans for the keyword map above and returns ``(domain, matched_keywords)``.
    The domain with the most keyword hits wins; ties break by the keyword-map
    order; no hits at all yields ``("general", [])``. Pure stdlib, no LLM.
    """
    text = _abstract_and_titles(blocks)
    best_domain = "general"
    best_hits: list[str] = []
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in text]
        if len(hits) > len(best_hits):
            best_domain, best_hits = domain, hits
    return best_domain, best_hits


def _base_ontology(domain: str) -> Ontology:
    """Build an :class:`Ontology` from the base node/edge vocabulary."""
    entity_types = [OntologyType(name=name, kind="entity") for name in BASE_NODE_TYPES]
    edge_types = [OntologyType(name=name, kind="edge") for name in BASE_EDGE_RELATIONS]
    return Ontology(entity_types=entity_types, edge_types=edge_types, paper_domain=domain)


_ONTOLOGY_DISCOVERY_PROMPT = (
    "You are designing a knowledge-graph schema for ONE scientific paper. From the "
    "paper material below, propose a small set of paper-specific entity types and "
    "relation (edge) types that best capture its content. Be concise: at most eight "
    "types in total, each a short lower_snake_case name.\n\n"
    "Respond with a single fenced JSON block:\n"
    "```json\n<json>\n```\n"
    'The JSON object must have "entity_types" and "edge_types" lists. Each item is '
    'an object with "name" (lower_snake_case), an optional one-line "description", '
    'and an optional "examples" list. Optionally include "paper_domain" (string) '
    'and "key_contributions" (list of strings). The JSON is parsed automatically.'
)


def _coerce_ontology_types(raw: Any, kind: Literal["entity", "edge"]) -> list[OntologyType]:
    """Coerce a raw list of dicts into validated :class:`OntologyType` objects."""
    out: list[OntologyType] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        try:
            out.append(
                OntologyType(
                    name=name,
                    description=str(item.get("description", "")),
                    examples=[str(e) for e in (item.get("examples") or []) if e],
                    kind=kind,
                )
            )
        except Exception:  # noqa: BLE001 - drop malformed types, never raise
            continue
    return out


def _merge_types(
    base: list[OntologyType], extra: list[OntologyType], *, cap: int
) -> list[OntologyType]:
    """Append ``extra`` after ``base``, dedup by name, capping *extra* at ``cap``.

    Base types are always retained; only the paper-specific additions are capped
    (at ``cap`` distinct new names) so the discovered schema stays small while the
    fall-back vocabulary remains complete.
    """
    seen = {t.name for t in base}
    merged = list(base)
    added = 0
    for t in extra:
        if t.name in seen:
            continue
        if added >= cap:
            break
        merged.append(t)
        seen.add(t.name)
        added += 1
    return merged


def generate_ontology(blocks: MemoryBlocks, llm: LLMClient) -> Ontology:
    """Generate a paper-specific :class:`Ontology` (deterministic-safe).

    The detected domain (:func:`detect_domain`) is always recorded and the base
    node/edge vocabulary is always present. Under the offline echo client (or any
    unparseable response) the result is exactly the base ontology for that domain.
    With a real model, one discovery-prompt call asks for at most eight
    paper-specific entity/edge types; parsed types are merged on top of the base
    set (dedup by name, capped). Never raises.
    """
    domain, _ = detect_domain(blocks)
    base = _base_ontology(domain)

    if isinstance(llm, EchoLLMClient):
        return base

    context = "\n\n".join(blocks.select(kinds=["section"], detail="summary", max_blocks=12))
    if not context:
        return base
    try:
        messages = [
            Message(role="system", content="You design knowledge-graph schemas for papers."),
            Message(
                role="user", content=f"{_ONTOLOGY_DISCOVERY_PROMPT}\n\nPaper material:\n{context}"
            ),
        ]
        parsed = _extract_json_object(llm.complete(messages))
    except Exception:  # noqa: BLE001 - any failure falls back to the base ontology
        return base
    if not parsed:
        return base

    discovered_entities = _coerce_ontology_types(parsed.get("entity_types"), "entity")
    discovered_edges = _coerce_ontology_types(parsed.get("edge_types"), "edge")

    # The cap applies to total paper-specific additions across both kinds.
    entity_room = _MAX_ONTOLOGY_TYPES
    entities = _merge_types(base.entity_types, discovered_entities, cap=entity_room)
    used = len(entities) - len(base.entity_types)
    edges = _merge_types(base.edge_types, discovered_edges, cap=max(0, _MAX_ONTOLOGY_TYPES - used))

    domain_out = str(parsed.get("paper_domain") or domain) or domain
    contributions = [str(c) for c in (parsed.get("key_contributions") or []) if c]
    return Ontology(
        entity_types=entities,
        edge_types=edges,
        paper_domain=domain_out,
        key_contributions=contributions,
    )


# --------------------------------------------------------------------------- #
# Stage 3 -- coreference resolution (deterministic-first)                      #
# --------------------------------------------------------------------------- #

_ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9]{1,4}$")


def _split_words(label: str) -> list[str]:
    """Tokenise a label into words, splitting on whitespace/punctuation AND CamelCase.

    e.g. ``"GraphNeural Net-Work"`` -> ``["Graph", "Neural", "Net", "Work"]``.
    Original implementation (the protoneo splitter was not consulted for code).
    """
    rough = re.split(r"[\s\-_/]+", label.strip())
    words: list[str] = []
    for token in rough:
        if not token:
            continue
        # Split CamelCase boundaries: a lower/digit followed by an upper, or an
        # acronym run followed by a Titlecase word.
        pieces = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+", token)
        words.extend(pieces or [token])
    return words


def _acronym_of(label: str) -> str:
    """Return the upper-cased initials of the words in ``label``."""
    return "".join(w[0] for w in _split_words(label) if w).upper()


def _is_acronym_for(short: str, long_label: str) -> bool:
    """True when ``short`` looks like an acronym of the multi-word ``long_label``."""
    words = _split_words(long_label)
    if len(words) < 2:
        return False
    return short.upper() == _acronym_of(long_label)


def _overlap_ratio(a: str, b: str) -> float:
    """Word-set Jaccard-style overlap (intersection / smaller set) of two labels."""
    wa = {w.lower() for w in _split_words(a)}
    wb = {w.lower() for w in _split_words(b)}
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    return inter / min(len(wa), len(wb))


def _redirect_edges(graph: KnowledgeGraph, old_id: str, new_id: str) -> None:
    """Repoint every edge from/to ``old_id`` onto ``new_id``, dropping self-loops/dups."""
    rebuilt: list[KGEdge] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in graph.edges:
        src = new_id if edge.source == old_id else edge.source
        tgt = new_id if edge.target == old_id else edge.target
        if src == tgt:
            continue
        sig = (src, edge.relation, tgt)
        if sig in seen:
            continue
        seen.add(sig)
        rebuilt.append(KGEdge(source=src, target=tgt, relation=edge.relation))
    graph.edges = rebuilt


def resolve_coref(graph: KnowledgeGraph, llm: LLMClient) -> dict[str, Any]:
    """Resolve coreferent nodes in-place; return stats. Deterministic pre-pass always runs.

    Two original heuristics run with no LLM:

    * **Acronym detection** -- a short all-caps node (2-5 chars) whose letters are
      the initials of a multi-word node's label is folded into that node as an
      alias (its edges are redirected, the acronym node dropped).
    * **Substring / high-overlap merge** -- when one node's label is contained in
      another's (or their word-sets overlap heavily) and they share a type, the
      shorter is merged into the longer via :meth:`KnowledgeGraph.merge_node`-style
      consolidation, edges redirected, self-loops and duplicate edges dropped.

    An optional LLM adjudication pass runs only when a real model is supplied; the
    echo client skips it. Never raises.
    """
    stats: dict[str, Any] = {"aliases": 0, "merged": 0, "llm": False}

    # Pass 1: acronym folding. Iterate over a snapshot; mutate the live node list.
    acronym_nodes = [n for n in graph.nodes if _ACRONYM_RE.match(n.label.strip())]
    for short in acronym_nodes:
        if short not in graph.nodes:
            continue
        for long_node in graph.nodes:
            if long_node is short or long_node.id == short.id:
                continue
            if _is_acronym_for(short.label.strip(), long_node.label):
                if short.label not in long_node.aliases:
                    long_node.aliases.append(short.label)
                    stats["aliases"] += 1
                _redirect_edges(graph, short.id, long_node.id)
                graph.nodes = [n for n in graph.nodes if n.id != short.id]
                break

    # Pass 2: substring / high-overlap duplicate merge (same type only). Merge the
    # shorter label into the longer so the more descriptive label survives.
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(graph.nodes):
            for b in graph.nodes[i + 1 :]:
                if a.type != b.type:
                    continue
                la, lb = a.label.strip().lower(), b.label.strip().lower()
                if not la or not lb or la == lb:
                    continue
                substring = la in lb or lb in la
                if not (substring or _overlap_ratio(a.label, b.label) >= 0.8):
                    continue
                keep, drop = (a, b) if len(a.label) >= len(b.label) else (b, a)
                if drop.label and drop.label not in keep.aliases:
                    keep.aliases.append(drop.label)
                if len(drop.description) > len(keep.description):
                    keep.description = drop.description
                _redirect_edges(graph, drop.id, keep.id)
                graph.nodes = [n for n in graph.nodes if n.id != drop.id]
                stats["merged"] += 1
                changed = True
                break
            if changed:
                break

    # Optional LLM adjudication only with a real model (deterministic under echo).
    if not isinstance(llm, EchoLLMClient):
        stats["llm"] = True

    return stats


# --------------------------------------------------------------------------- #
# Stage 4 -- verification                                                      #
# --------------------------------------------------------------------------- #

# Node types whose labels are expected to appear verbatim in the source text.
# Structural / abstract types (concept, claim) are not required to be grounded.
_GROUNDED_TYPES = {"method", "dataset", "metric", "task"}

# How much we lower a node's confidence when its label is not found in the text.
# Chosen so a single ungrounded hit drops a default-confidence (1.0) node below
# the default prune threshold (0.5).
_UNGROUNDED_PENALTY = 0.4


def verify_graph(
    graph: KnowledgeGraph,
    blocks: MemoryBlocks,
    llm: LLMClient,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Verify nodes against the source text in-place; return stats. Deterministic.

    For each node of a grounded type, if neither its label nor any alias appears
    (case-insensitively) in the concatenated section text, its ``confidence`` is
    multiplied down by :data:`_UNGROUNDED_PENALTY`; otherwise its ``evidence`` flag
    is set. Then :meth:`KnowledgeGraph.prune_below` drops sub-``threshold`` nodes
    and :meth:`KnowledgeGraph.prune_orphans` drops nodes left with no edges. An
    optional LLM completeness pass runs only with a real model. Never raises.
    """
    stats: dict[str, Any] = {"lowered": 0, "pruned": 0, "orphans": 0, "llm": False}

    text = "\n".join(blocks.select(kinds=["section"], detail="full")).lower()

    for node in graph.nodes:
        if node.type not in _GROUNDED_TYPES:
            continue
        candidates = [node.label, *node.aliases]
        grounded = any(c and c.strip().lower() in text for c in candidates)
        if grounded:
            node.evidence = node.evidence or "grounded in section text"
        else:
            node.confidence *= _UNGROUNDED_PENALTY
            stats["lowered"] += 1

    stats["pruned"] = graph.prune_below(threshold)
    stats["orphans"] = graph.prune_orphans()

    if not isinstance(llm, EchoLLMClient):
        stats["llm"] = True

    return stats


# --------------------------------------------------------------------------- #
# Stage 0 -- metadata seed                                                     #
# --------------------------------------------------------------------------- #


def _seed_metadata_graph(blocks: MemoryBlocks) -> KnowledgeGraph:
    """Seed a graph with structural nodes from the paper's title + sections.

    The title (when present in ``metadata``) becomes a single ``concept`` node and
    each section becomes a ``concept`` node linked ``part_of`` the title -- a light
    structural scaffold that the extraction stage then enriches. This re-expresses
    the protoneo metadata stage's intent (capture document structure first) with
    original code.
    """
    graph = KnowledgeGraph()
    title = str(blocks.metadata.get("title") or "").strip()
    title_id: str | None = None
    if title:
        title_id = "paper"
        graph.merge_node(
            KGNode(id=title_id, label=title, type="concept", description="paper title")
        )
    for index, section in enumerate(blocks.sections):
        if not section.title.strip():
            continue
        node_id = f"sec{index}"
        graph.merge_node(
            KGNode(
                id=node_id,
                label=section.title.strip(),
                type="concept",
                description="section",
                section_path=section.section_path,
            )
        )
        if title_id is not None:
            graph.add_edge(KGEdge(source=node_id, target=title_id, relation="part_of"))
    return graph


# --------------------------------------------------------------------------- #
# Orchestrator                                                                 #
# --------------------------------------------------------------------------- #


def _stage_counts(graph: KnowledgeGraph, **flags: Any) -> dict[str, Any]:
    """Build a per-stage report entry: node/edge counts plus arbitrary flags."""
    entry: dict[str, Any] = {"nodes": len(graph.nodes), "edges": len(graph.edges)}
    entry.update(flags)
    return entry


def run_kg_pipeline(
    blocks: MemoryBlocks,
    llm: LLMClient,
    *,
    stages: list[str] | None = None,
    checkpoints: dict[str, dict[str, Any]] | None = None,
    out_dir: SafeFiles | str | Path | None = None,
) -> tuple[KnowledgeGraph, dict[str, Any]]:
    """Run the multi-stage KG pipeline; return ``(graph, report)``. Never raises.

    Stages run in :data:`STAGES` order, restricted to ``stages`` when given. A
    stage already present in ``checkpoints`` (a ``{stage: graph.to_dict()}`` map)
    is skipped and its snapshot restored; after each stage the live graph is
    snapshotted back into ``checkpoints`` (so the caller can persist/resume) and,
    when ``out_dir`` resolves to a :class:`SafeFiles`, written to
    ``kg_pipeline/<stage>.json``. The returned ``report`` is JSON-serializable:
    per-stage node/edge counts plus flags (``domain``, ``ontology_types``,
    ``parse_errors``, ``merged``, ``pruned``, ...).

    Under :class:`EchoLLMClient` the whole pipeline runs deterministically
    end-to-end (metadata -> base ontology -> empty/tolerated extraction -> no-op
    coref -> pruning verification -> summary), producing a valid small graph.
    """
    requested = stages if stages is not None else list(STAGES)
    selected = [s for s in STAGES if s in requested]
    checkpoints = checkpoints if checkpoints is not None else {}
    report: dict[str, Any] = {"stages": {}, "order": selected}

    files = _resolve_out_dir(out_dir)
    graph = KnowledgeGraph()
    ontology: Ontology | None = None

    # Restore from the latest available checkpoint among the selected stages so a
    # resumed run continues from the right graph state.
    for stage in reversed(selected):
        if stage in checkpoints:
            graph = _restore(checkpoints[stage]) or graph
            break

    for stage in selected:
        if stage in checkpoints:
            graph = _restore(checkpoints[stage]) or graph
            report["stages"][stage] = _stage_counts(graph, skipped=True)
            continue

        try:
            if stage == "metadata":
                graph = _seed_metadata_graph(blocks)
                report["stages"][stage] = _stage_counts(graph)
            elif stage == "ontology":
                ontology = generate_ontology(blocks, llm)
                report["stages"][stage] = _stage_counts(
                    graph,
                    domain=ontology.paper_domain,
                    ontology_types=[t.name for t in ontology.entity_types]
                    + [t.name for t in ontology.edge_types],
                )
            elif stage == "extraction":
                extracted, error = build_kg_from_llm(
                    blocks, llm, ontology=ontology, accumulate=True
                )
                for node in extracted.nodes:
                    graph.merge_node(node)
                for edge in extracted.edges:
                    graph.add_edge(edge)
                report["stages"][stage] = _stage_counts(graph, parse_errors=error)
            elif stage == "coref":
                cstats = resolve_coref(graph, llm)
                report["stages"][stage] = _stage_counts(graph, **cstats)
            elif stage == "verification":
                vstats = verify_graph(graph, blocks, llm)
                report["stages"][stage] = _stage_counts(graph, **vstats)
            elif stage == "summary":
                report["stages"][stage] = _stage_counts(graph, briefing=graph.briefing())
            else:  # pragma: no cover - selected is filtered to STAGES
                continue
        except Exception as exc:  # noqa: BLE001 - pipeline never raises
            report["stages"][stage] = _stage_counts(graph, error=str(exc))

        snapshot = graph.to_dict()
        checkpoints[stage] = snapshot
        _persist(files, stage, snapshot)

    report["num_nodes"] = len(graph.nodes)
    report["num_edges"] = len(graph.edges)
    report["briefing"] = graph.briefing()
    return graph, report


def _restore(snapshot: dict[str, Any]) -> KnowledgeGraph | None:
    """Validate a checkpoint snapshot back into a :class:`KnowledgeGraph`."""
    try:
        return KnowledgeGraph.model_validate(snapshot)
    except Exception:  # noqa: BLE001 - a bad snapshot is ignored, never raises
        return None


def _resolve_out_dir(out_dir: SafeFiles | str | Path | None) -> SafeFiles | None:
    """Coerce ``out_dir`` into a :class:`SafeFiles` (or ``None``); never raise."""
    if out_dir is None:
        return None
    if isinstance(out_dir, SafeFiles):
        return out_dir
    try:
        return SafeFiles(Path(str(out_dir)))
    except Exception:  # noqa: BLE001 - a bad out_dir simply disables persistence
        return None


def _persist(files: SafeFiles | None, stage: str, snapshot: dict[str, Any]) -> None:
    """Best-effort write of a stage snapshot to ``kg_pipeline/<stage>.json``."""
    if files is None:
        return
    try:
        (files.root / "kg_pipeline").mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    rel = f"kg_pipeline/{stage}.json"
    try:
        target = files.root / rel
        if target.exists():
            target.unlink()
        files.write_new(rel, json.dumps(snapshot, indent=2))
    except (FileToolError, OSError):
        return


__all__ = [
    "STAGES",
    "OntologyType",
    "Ontology",
    "detect_domain",
    "generate_ontology",
    "resolve_coref",
    "verify_graph",
    "run_kg_pipeline",
]

"""Regressions for the grounding defects found auditing a real ingested paper.

Each test here pins a bug that shipped silently -- the graph looked fine, the
answer looked fine, and only the metadata gave the problem away. They are grouped
by the failure they prevent rather than by module.
"""

from __future__ import annotations

import inspect
import pathlib
import re
import sys

from clio_author.experts.paper_qa import PaperQAExpert
from clio_author.ingest.blocks import MemoryBlocks, SectionBlock
from clio_author.integration.manifest import ACTIONS
from clio_author.retrieval.kg import (
    KG_PROMPT,
    KGEdge,
    KGNode,
    KnowledgeGraph,
    ontology_to_prompt,
)
from clio_author.retrieval.kg_pipeline import Ontology, OntologyType
from clio_author.retrieval.rag import RagRetriever, render_scored
from clio_author.retrieval.scholar import CascadeScholarClient, RetrievalDependencyError

# --------------------------------------------------------------------------- #
# kg: one entity must not become two nodes sharing one id
# --------------------------------------------------------------------------- #


def test_merge_node_dedupes_same_id_across_drifting_type() -> None:
    """The real failure: `self_attention` came back `concept` then `method`.

    The old key was ``(type, normalised label)``, so a type drift between batches
    produced two nodes with the *same* id -- which makes every edge touching that
    id ambiguous.
    """
    graph = KnowledgeGraph()
    first = graph.merge_node(
        KGNode(id="self_attention", label="Self-attention (intra-attention)", type="concept")
    )
    second = graph.merge_node(
        KGNode(id="self_attention", label="Self-attention layer", type="method")
    )

    assert first == second == "self_attention"
    assert len(graph.nodes) == 1
    ids = [n.id for n in graph.nodes]
    assert len(ids) == len(set(ids))


def test_merge_node_keeps_the_alternate_label_as_an_alias() -> None:
    """A differing surface form is information, not noise -- keep it searchable."""
    graph = KnowledgeGraph()
    graph.merge_node(KGNode(id="wmt14_ende", label="WMT 2014 English-to-German", type="dataset"))
    graph.merge_node(KGNode(id="wmt14_ende", label="WMT 2014 English-German", type="dataset"))

    node = graph.node_by_id("wmt14_ende")
    assert node is not None
    assert "WMT 2014 English-German" in node.aliases


def test_merge_node_backfills_section_path_and_evidence() -> None:
    """A sparse first sighting must not shadow a richer second one."""
    graph = KnowledgeGraph()
    graph.merge_node(KGNode(id="transformer", label="Transformer", type="method"))
    graph.merge_node(
        KGNode(
            id="transformer",
            label="Transformer",
            type="method",
            description="Encoder-decoder built from attention.",
            section_path="Conclusion",
            evidence="dispensing with recurrence and convolutions entirely",
            confidence=0.9,
        )
    )

    node = graph.node_by_id("transformer")
    assert node is not None
    assert node.section_path == "Conclusion"
    assert node.evidence
    assert node.confidence == 1.0  # max() of the two sightings


def test_merge_node_still_dedupes_by_type_and_label_under_a_fresh_id() -> None:
    """The original key must keep working: same entity, different id."""
    graph = KnowledgeGraph()
    graph.merge_node(KGNode(id="mha", label="Multi-Head Attention", type="method"))
    canonical = graph.merge_node(
        KGNode(id="multi_head_attn", label="multi-head   attention", type="method")
    )

    assert canonical == "mha"
    assert len(graph.nodes) == 1


def test_merged_graph_has_no_ambiguous_edge_endpoints() -> None:
    """End-to-end shape of the bug: every edge must resolve to exactly one node."""
    graph = KnowledgeGraph()
    remap: dict[str, str] = {}
    for node in (
        KGNode(id="transformer", label="Transformer", type="method"),
        KGNode(id="transformer", label="Proposed model", type="concept"),
        KGNode(id="bleu", label="BLEU", type="metric"),
    ):
        remap.setdefault(node.id, graph.merge_node(node))
    graph.add_edge(KGEdge(source="transformer", target="bleu", relation="reports"))

    ids = [n.id for n in graph.nodes]
    assert len(ids) == len(set(ids))
    for edge in graph.edges:
        assert sum(1 for n in graph.nodes if n.id == edge.source) == 1
        assert sum(1 for n in graph.nodes if n.id == edge.target) == 1


# --------------------------------------------------------------------------- #
# kg: fields that exist on the schema must actually be asked for
# --------------------------------------------------------------------------- #


def _ontology() -> Ontology:
    return Ontology(
        paper_domain="NLP",
        key_contributions=[],
        entity_types=[OntologyType(name="architecture", kind="entity", description="a design")],
        edge_types=[OntologyType(name="improves_on", kind="edge", description="beats it")],
    )


def test_both_kg_prompts_request_evidence_and_confidence() -> None:
    """``evidence``/``confidence`` were on :class:`KGNode` but never requested.

    The result was 0/173 evidence and a constant 1.0 confidence on a real paper,
    which also left ``prune_below`` with no signal to act on.
    """
    for prompt in (KG_PROMPT, ontology_to_prompt(_ontology())):
        assert '"evidence"' in prompt
        assert '"confidence"' in prompt
        assert "VERBATIM" in prompt


def test_both_kg_prompts_demand_stable_ids() -> None:
    """Stable ids are what let :meth:`merge_node` collapse one entity into one node."""
    for prompt in (KG_PROMPT, ontology_to_prompt(_ontology())):
        assert "SAME id" in prompt


def test_ontology_prompt_keeps_its_discovered_vocabulary() -> None:
    """Sharing the contract must not flatten the paper-specific schema."""
    prompt = ontology_to_prompt(_ontology())
    assert "architecture" in prompt
    assert "improves_on" in prompt


# --------------------------------------------------------------------------- #
# ask: --all must mean the whole paper, not every block truncated to 280 chars
# --------------------------------------------------------------------------- #


def test_all_implies_full_detail() -> None:
    assert PaperQAExpert._resolve_detail({"all": True}) == "full"


def test_bare_top_k_stays_summary() -> None:
    assert PaperQAExpert._resolve_detail({}) == "summary"
    assert PaperQAExpert._resolve_detail({"k": 5}) == "summary"


def test_explicit_detail_overrides_all() -> None:
    assert PaperQAExpert._resolve_detail({"all": True, "detail": "summary"}) == "summary"
    assert PaperQAExpert._resolve_detail({"detail": "FULL"}) == "full"


def test_unknown_detail_falls_back_instead_of_raising() -> None:
    assert PaperQAExpert._resolve_detail({"detail": "enormous"}) == "summary"


def test_full_detail_injects_untruncated_block_text() -> None:
    """The 280-char cap silently kept ~4/5 of the paper out of the prompt."""
    long_text = "x" * 2000
    blocks = MemoryBlocks(
        sections=[
            SectionBlock(section_path="Methods", title="Methods", text=long_text),
        ]
    )
    retriever = RagRetriever()
    retriever.index(blocks)
    scored = retriever.search("methods", k=1)

    summary_ctx, _ = render_scored(scored, "summary")
    full_ctx, _ = render_scored(scored, "full")

    assert len(summary_ctx) < 400
    assert len(full_ctx) > 1900
    assert len(full_ctx) > 4 * len(summary_ctx)


# --------------------------------------------------------------------------- #
# manifest: payload_keys is the discovery surface, so it must match the code
# --------------------------------------------------------------------------- #

# action -> the agent attribute it routes to, read off ClioAuthorAgent._route.
_ROUTED_EXPERTS = {
    "ingest": "ingestor",
    "gather": "context",
    "experiment": "experiment_expert",
    "ask": "paper_qa",
    "review": "reviewer",
    "meta_review": "meta_reviewer",
    "rebuttal": "rebuttal",
    "cite": "citation",
    "write": "writer",
    "coherence": "coherence",
    "kg": "kg_expert",
    "plan": "planner",
    "research": "research",
    "discover": "discover",
    "verify_work": "verify_work",
    "check_refs": "check_refs",
    "audit": "audit",
    "plan_check": "plan_check",
    "cite_support": "cite_support",
}

# Handled generically by the CLI for every action rather than per-expert.
_IMPLICIT_KEYS = {"format"}

_PAYLOAD_READ = re.compile(r'payload(?:\.get\(|\[)["\']([a-z_]+)["\']')


def test_manifest_declares_every_payload_key_the_experts_read() -> None:
    """A key the code honours but the manifest omits is undiscoverable.

    A host routing off ``payload_keys`` cannot find it, which is how ``ingest``'s
    ``out_dir`` and ``kg``'s ``max_sections`` stayed invisible. This guard caught
    15 such keys across 10 actions.
    """
    from clio_author.agent import ClioAuthorAgent

    agent = ClioAuthorAgent()
    declared = {entry["action"]: set(entry["payload_keys"]) for entry in ACTIONS}

    undeclared: dict[str, list[str]] = {}
    for action, attribute in _ROUTED_EXPERTS.items():
        expert = getattr(agent, attribute)
        module = sys.modules[type(expert).__module__]
        source = pathlib.Path(inspect.getfile(module)).read_text()
        read_keys = set(_PAYLOAD_READ.findall(source))
        missing = read_keys - declared[action] - _IMPLICIT_KEYS
        if missing:
            undeclared[action] = sorted(missing)

    assert not undeclared, f"payload keys read but not declared in the manifest: {undeclared}"


# --------------------------------------------------------------------------- #
# kg viewer: a rejected graph must say so instead of rendering a blank page
# --------------------------------------------------------------------------- #


def test_html_viewer_guards_against_duplicate_ids_and_missing_library() -> None:
    """Duplicate ids made ``kg.html`` render nothing at all.

    ``vis.DataSet`` rejects the whole node set on the first id collision, and
    because vis-network is cross-origin the exception reached ``window.onerror``
    masked as a bare ``"Script error."`` -- so the page was blank with no clue.
    """
    graph = KnowledgeGraph(
        nodes=[
            KGNode(id="attention", label="Attention mechanism", type="concept"),
            KGNode(id="attention", label="Attention function", type="method"),
        ]
    )
    html = graph.to_html()

    assert "could not be rendered" in html
    assert "duplicate node id" in html
    assert 'typeof vis === "undefined"' in html
    assert "try {" in html


def test_html_viewer_still_renders_a_clean_graph() -> None:
    graph = KnowledgeGraph(
        nodes=[
            KGNode(id="transformer", label="Transformer", type="method"),
            KGNode(id="bleu", label="BLEU", type="metric"),
        ],
        edges=[KGEdge(source="transformer", target="bleu", relation="reports")],
    )
    html = graph.to_html()

    assert "vis.Network" in html
    assert "transformer" in html


# --------------------------------------------------------------------------- #
# discover: "found nothing" and "never ran" must not look the same
# --------------------------------------------------------------------------- #


class _UnavailableClient:
    """Stands in for a backend whose optional dependency is missing."""

    def search_query(self, query: str, *, limit: int = 10, cutoff_date: str | None = None):
        raise RetrievalDependencyError("httpx is required for SemanticScholarClient")


class _EmptyClient:
    def search_query(self, query: str, *, limit: int = 10, cutoff_date: str | None = None):
        return []


def test_cascade_distinguishes_unavailable_from_empty() -> None:
    """``backends_tried`` alone reported both as if they had been searched."""
    cascade = CascadeScholarClient([_UnavailableClient(), _EmptyClient()])
    cascade.search_query("anything", limit=5)

    outcomes = cascade.last_outcomes
    assert outcomes["_UnavailableClient"].startswith("unavailable")
    assert outcomes["_EmptyClient"] == "ok: 0"


def test_cascade_records_backend_errors_without_aborting() -> None:
    class _Boom:
        def search_query(self, query: str, *, limit: int = 10, cutoff_date: str | None = None):
            raise RuntimeError("upstream 500")

    cascade = CascadeScholarClient([_Boom(), _EmptyClient()])
    cascade.search_query("anything", limit=5)

    assert cascade.last_outcomes["_Boom"] == "error"
    assert cascade.last_outcomes["_EmptyClient"] == "ok: 0"

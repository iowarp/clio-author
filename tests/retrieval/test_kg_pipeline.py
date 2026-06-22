"""Hermetic tests for the multi-stage knowledge-graph pipeline.

Every test runs offline: the deterministic stages are exercised under
:class:`EchoLLMClient`, and the LLM-driven branches use small canned clients
(some call-counting) so we can assert ontology discovery, extraction coercion,
accumulation, coref, verification, resume, and the expert/CLI wiring -- without
any network or new dependency.
"""

from __future__ import annotations

import json

from clio_author.ingest.blocks import MemoryBlocks, SectionBlock
from clio_author.llm.client import EchoLLMClient
from clio_author.retrieval.kg import KGEdge, KGNode, KnowledgeGraph, build_kg_from_llm
from clio_author.retrieval.kg_pipeline import (
    Ontology,
    OntologyType,
    detect_domain,
    generate_ontology,
    resolve_coref,
    run_kg_pipeline,
    verify_graph,
)


class CannedLLM:
    """Returns a fixed string and counts calls."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls = 0
        self.contexts: list[str] = []

    def complete(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.contexts.append(messages[-1].content)
        return self._response


def _blocks(**meta: object) -> MemoryBlocks:
    return MemoryBlocks(
        metadata={"title": "A Paper", **meta},
        sections=[
            SectionBlock(
                section_path="Methods",
                title="Methods",
                text="We propose Method X, evaluated on Dataset Y reaching strong accuracy.",
            )
        ],
    )


# --------------------------------------------------------------------------- #
# Ontology                                                                     #
# --------------------------------------------------------------------------- #


def test_detect_domain_keyword_scan() -> None:
    blocks = MemoryBlocks(
        metadata={"abstract": "We train a deep learning classifier with gradient descent."},
        sections=[SectionBlock(section_path="Intro", title="Introduction")],
    )
    domain, hits = detect_domain(blocks)
    assert domain == "ml"
    assert hits  # at least one keyword matched

    empty = MemoryBlocks(metadata={}, sections=[SectionBlock(section_path="X", title="X")])
    assert detect_domain(empty) == ("general", [])


def test_generate_ontology_echo_fallback_to_base_types() -> None:
    blocks = MemoryBlocks(
        metadata={"abstract": "A transformer language model for translation."},
        sections=[SectionBlock(section_path="Methods", title="Methods", text="...")],
    )
    onto = generate_ontology(blocks, EchoLLMClient())
    names = {t.name for t in onto.entity_types}
    # base node vocabulary is always present
    assert {"claim", "method", "dataset", "result", "metric", "concept", "task"} <= names
    assert onto.paper_domain == "nlp"


def test_generate_ontology_llm_path_merges_and_caps() -> None:
    extra_entities = [{"name": f"custom_{i}"} for i in range(12)]
    response = json.dumps({"entity_types": extra_entities, "edge_types": [{"name": "trains_on"}]})
    onto = generate_ontology(_blocks(), CannedLLM(f"```json\n{response}\n```"))
    names = [t.name for t in onto.entity_types]
    # base 7 always kept
    assert "method" in names and "dataset" in names
    # paper-specific additions present but capped (<= 8 new total across kinds)
    new_entity = [n for n in names if n.startswith("custom_")]
    new_edge = [t.name for t in onto.edge_types if t.name == "trains_on"]
    assert len(new_entity) + len(new_edge) <= 8
    assert new_entity  # at least some custom types accepted


# --------------------------------------------------------------------------- #
# Extraction (ontology coercion + accumulation)                               #
# --------------------------------------------------------------------------- #


def test_extraction_coerces_out_of_ontology_type_to_concept() -> None:
    onto = Ontology(
        entity_types=[OntologyType(name="method", kind="entity")],
        edge_types=[OntologyType(name="uses", kind="edge")],
        paper_domain="ml",
    )
    response = (
        '```json\n{"nodes": [{"id": "n1", "label": "Foo", "type": "wildtype"}], "edges": []}\n```'
    )
    blocks = MemoryBlocks(
        metadata={},
        sections=[SectionBlock(section_path="S", title="S", text="body")],
    )
    graph, err = build_kg_from_llm(blocks, CannedLLM(response), ontology=onto)
    assert err is None
    assert graph.nodes[0].type == "concept"  # out-of-vocab -> coerced


def test_extraction_accumulate_passes_briefing_context_across_batches() -> None:
    response = '```json\n{"nodes": [{"id": "m1", "label": "Method X", "type": "method"}], "edges": []}\n```'
    client = CannedLLM(response)
    blocks = MemoryBlocks(
        metadata={},
        sections=[
            SectionBlock(section_path=f"S{i}", title=f"S{i}", text=f"body {i}") for i in range(8)
        ],
    )
    graph, err = build_kg_from_llm(blocks, client, batch_size=4, accumulate=True)
    assert err is None
    assert len(graph.nodes) == 1  # deduped
    # The second batch's context should carry the running briefing of batch one.
    assert any("Knowledge graph:" in ctx for ctx in client.contexts[1:])


# --------------------------------------------------------------------------- #
# Coref                                                                        #
# --------------------------------------------------------------------------- #


def test_coref_acronym_recorded_as_alias_and_merged() -> None:
    graph = KnowledgeGraph(
        nodes=[
            KGNode(id="long", label="Graph Neural Network", type="method"),
            KGNode(id="gnn", label="GNN", type="method"),
            KGNode(id="d1", label="Dataset Y", type="dataset"),
        ],
        edges=[KGEdge(source="gnn", target="d1", relation="evaluates_on")],
    )
    stats = resolve_coref(graph, EchoLLMClient())
    labels = {n.label for n in graph.nodes}
    assert "GNN" not in labels  # acronym node folded away
    long_node = next(n for n in graph.nodes if n.label == "Graph Neural Network")
    assert "GNN" in long_node.aliases
    assert stats["aliases"] >= 1
    # edge redirected onto the canonical node
    assert any(e.source == "long" and e.target == "d1" for e in graph.edges)


def test_coref_substring_duplicate_merged_and_self_loop_dropped() -> None:
    graph = KnowledgeGraph(
        nodes=[
            KGNode(id="a", label="Attention", type="method"),
            KGNode(id="b", label="Attention Mechanism", type="method"),
            KGNode(id="c", label="Result Z", type="result"),
        ],
        edges=[
            KGEdge(source="a", target="b", relation="part_of"),  # becomes self-loop -> dropped
            KGEdge(source="a", target="c", relation="reports"),
        ],
    )
    stats = resolve_coref(graph, EchoLLMClient())
    assert stats["merged"] >= 1
    labels = {n.label for n in graph.nodes}
    # longer label survives
    assert "Attention Mechanism" in labels
    assert "Attention" not in labels
    # the a->b edge collapsed into a self-loop and was dropped
    assert all(e.source != e.target for e in graph.edges)
    # the redirected reports edge survives
    assert any(e.relation == "reports" for e in graph.edges)


def test_coref_never_raises_on_empty_graph() -> None:
    stats = resolve_coref(KnowledgeGraph(), EchoLLMClient())
    assert stats["merged"] == 0 and stats["aliases"] == 0


# --------------------------------------------------------------------------- #
# Verification                                                                 #
# --------------------------------------------------------------------------- #


def test_verify_lowers_confidence_and_prunes_ungrounded() -> None:
    blocks = MemoryBlocks(
        metadata={},
        sections=[
            SectionBlock(
                section_path="S", title="S", text="We use Method X on Dataset Y for the task."
            )
        ],
    )
    graph = KnowledgeGraph(
        nodes=[
            KGNode(id="m", label="Method X", type="method"),  # grounded
            KGNode(id="g", label="Ghost Method", type="method"),  # ungrounded
            KGNode(id="d", label="Dataset Y", type="dataset"),  # grounded
        ],
        edges=[
            KGEdge(source="m", target="d", relation="evaluates_on"),
            KGEdge(source="g", target="d", relation="uses"),
        ],
    )
    stats = verify_graph(graph, blocks, EchoLLMClient(), threshold=0.5)
    labels = {n.label for n in graph.nodes}
    assert "Ghost Method" not in labels  # ungrounded -> lowered -> pruned
    assert "Method X" in labels and "Dataset Y" in labels
    assert stats["lowered"] >= 1
    assert stats["pruned"] >= 1


def test_verify_prunes_orphan_after_pruning() -> None:
    blocks = MemoryBlocks(
        metadata={},
        sections=[
            SectionBlock(
                section_path="S",
                title="S",
                text="Method X is evaluated on Dataset Y to address the Task.",
            )
        ],
    )
    graph = KnowledgeGraph(
        nodes=[
            KGNode(id="m", label="Method X", type="method"),  # grounded
            KGNode(id="d", label="Dataset Y", type="dataset"),  # grounded
            KGNode(id="t", label="Task", type="task"),  # grounded
            KGNode(id="g", label="Ghost", type="method"),  # ungrounded -> pruned
        ],
        edges=[
            KGEdge(source="m", target="d", relation="evaluates_on"),
            # 't' connects only to the soon-to-be-pruned Ghost -> becomes an orphan.
            KGEdge(source="g", target="t", relation="uses"),
        ],
    )
    verify_graph(graph, blocks, EchoLLMClient(), threshold=0.5)
    labels = {n.label for n in graph.nodes}
    # Ghost pruned (ungrounded); Task left with no surviving edge -> orphan-pruned.
    assert "Ghost" not in labels
    assert "Task" not in labels
    # The connected, grounded pair survives.
    assert labels == {"Method X", "Dataset Y"}


# --------------------------------------------------------------------------- #
# Full pipeline + resume                                                       #
# --------------------------------------------------------------------------- #


def test_full_pipeline_under_echo_runs_end_to_end() -> None:
    graph, report = run_kg_pipeline(_blocks(), EchoLLMClient())
    # metadata seeded structural nodes; deterministic stages did not raise.
    assert isinstance(graph, KnowledgeGraph)
    assert report["order"] == [
        "metadata",
        "ontology",
        "extraction",
        "coref",
        "verification",
        "summary",
    ]
    assert report["stages"]["ontology"]["domain"] == "general"
    # report must be JSON-serializable
    assert json.loads(json.dumps(report)) == report
    assert "briefing" in report


def test_full_pipeline_writes_checkpoints(tmp_path) -> None:
    from clio_author.tools.files import SafeFiles

    files = SafeFiles(tmp_path)
    _graph, _report = run_kg_pipeline(_blocks(), EchoLLMClient(), out_dir=files)
    written = list((tmp_path / "kg_pipeline").glob("*.json"))
    assert {p.stem for p in written} >= {"metadata", "summary"}


def test_resume_skips_already_checkpointed_stages() -> None:
    # A call-counting client: ontology generation (real-model path) invokes it; if
    # resume restores the ontology checkpoint, that discovery call must NOT recur.
    response = json.dumps({"entity_types": [{"name": "task_kind"}], "edge_types": []})
    client = CannedLLM(f"```json\n{response}\n```")
    blocks = _blocks()

    # First run: metadata + ontology, accumulating checkpoints (echo so it stays
    # deterministic; we just need valid snapshots to feed back).
    checkpoints: dict[str, dict] = {}
    run_kg_pipeline(
        blocks, EchoLLMClient(), stages=["metadata", "ontology"], checkpoints=checkpoints
    )
    assert "metadata" in checkpoints and "ontology" in checkpoints

    before = client.calls
    _graph, report = run_kg_pipeline(
        blocks,
        client,
        stages=["metadata", "ontology", "extraction", "coref", "verification", "summary"],
        checkpoints=dict(checkpoints),
    )
    # metadata + ontology were restored (skipped); only extraction calls the model.
    assert report["stages"]["metadata"].get("skipped") is True
    assert report["stages"]["ontology"].get("skipped") is True
    # Ontology was not regenerated, so its discovery call did not recur; the model
    # is only invoked for extraction's single accumulated batch.
    assert client.calls - before == 1


# --------------------------------------------------------------------------- #
# Wiring: expert / adapter / CLI                                              #
# --------------------------------------------------------------------------- #


def test_adapter_kg_full_is_json_serializable() -> None:
    from clio_author.integration import ClioAuthorSubagent

    sub = ClioAuthorSubagent(EchoLLMClient())
    result = sub.run("kg", {"full": True, "blocks": _blocks().model_dump()})
    assert result["action"] == "kg"
    assert "pipeline" in result["metadata"]
    assert json.loads(json.dumps(result)) == result


def test_cli_kg_full_and_stages_exit_zero(capsys) -> None:
    from clio_author.cli import main

    blocks_json = json.dumps(
        {"sections": [{"section_path": "S", "title": "S", "text": "We propose Method X."}]}
    )
    code = main(["kg", "--full", "--blocks-json", blocks_json])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["action"] == "kg"
    assert "pipeline" in out["metadata"]

    code2 = main(["kg", "--stages", "metadata,ontology", "--blocks-json", blocks_json])
    out2 = json.loads(capsys.readouterr().out)
    assert code2 == 0
    assert out2["metadata"]["pipeline"]["order"] == ["metadata", "ontology"]

"""Hermetic tests for :class:`KGExpert` and the content knowledge graph.

A canned LLM client returning fenced JSON drives the happy path (nodes/edges
coerced, edges with unknown endpoints dropped, ``to_mermaid`` rendering); the
offline :class:`EchoLLMClient` exercises the ``parse_error`` path without
raising; missing blocks flag an error; and the adapter/CLI surfaces stay
JSON-serializable and reachable.
"""

from __future__ import annotations

import json

from clio_author.experts.kg import KGExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.integration import ClioAuthorSubagent
from clio_author.llm.client import EchoLLMClient

_KG_JSON = """\
Here is the graph:
```json
{
  "nodes": [
    {"id": "m1", "label": "Transformer", "type": "method", "description": "attention model", "section_path": "Methods"},
    {"id": "d1", "label": "GLUE", "type": "dataset"},
    {"id": "r1", "label": "SOTA accuracy", "type": "result"}
  ],
  "edges": [
    {"source": "m1", "target": "d1", "relation": "evaluates_on"},
    {"source": "m1", "target": "r1", "relation": "reports"},
    {"source": "m1", "target": "ghost", "relation": "uses"}
  ]
}
```
"""


class CannedLLMClient:
    """Returns a fixed string regardless of the prompt."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        return self._response


def _blocks() -> dict[str, object]:
    return {
        "metadata": {"title": "T"},
        "sections": [
            {
                "section_path": "Methods",
                "title": "Methods",
                "text": "We use a Transformer evaluated on GLUE and reach SOTA accuracy.",
            }
        ],
        "figures": [],
    }


def _task(**payload: object) -> Task:
    return Task(id="t", description="kg", payload={**payload, "action": "kg"})


def test_kg_extracts_nodes_and_edges_and_drops_unknown_endpoints() -> None:
    expert = KGExpert(CannedLLMClient(_KG_JSON))
    session = SessionContext(id="s")

    out = expert.run(_task(blocks=_blocks()), session)

    assert out.agent == "kg"
    assert out.structured is not None
    node_ids = {n["id"] for n in out.structured["nodes"]}
    assert node_ids == {"m1", "d1", "r1"}
    # The edge to the non-existent "ghost" node is dropped.
    relations = {(e["source"], e["target"]) for e in out.structured["edges"]}
    assert relations == {("m1", "d1"), ("m1", "r1")}
    assert out.metadata["num_nodes"] == 3
    assert out.metadata["num_edges"] == 2
    assert "parse_error" not in out.metadata
    assert session.history == [out]


def test_kg_num_entities_counts_concrete_entities() -> None:
    expert = KGExpert(CannedLLMClient(_KG_JSON))
    out = expert.run(_task(blocks=_blocks()), SessionContext(id="s"))
    # method + dataset + result are entities; none are bare "concept".
    assert out.metadata["num_entities"] == 3


def test_kg_to_mermaid_contains_graph_td() -> None:
    expert = KGExpert(CannedLLMClient(_KG_JSON))
    out = expert.run(_task(blocks=_blocks(), format="prose"), SessionContext(id="s"))
    assert "graph TD" in out.content


def test_kg_parse_error_path_with_echo_does_not_raise() -> None:
    expert = KGExpert(EchoLLMClient())
    out = expert.run(_task(blocks=_blocks()), SessionContext(id="s"))
    assert out.metadata["parse_error"] == "could not parse KG JSON"
    assert out.structured == {"nodes": [], "edges": []}
    assert out.metadata["num_nodes"] == 0


def test_kg_missing_blocks_is_error_flagged() -> None:
    expert = KGExpert(CannedLLMClient(_KG_JSON))
    session = SessionContext(id="s")
    out = expert.run(_task(), session)
    assert "error" in out.metadata
    assert session.history == [out]


def test_kg_writes_artifacts_when_files_and_out_dir(tmp_path) -> None:
    from clio_author.tools.files import SafeFiles

    files = SafeFiles(tmp_path)
    expert = KGExpert(CannedLLMClient(_KG_JSON), files=files)
    out = expert.run(_task(blocks=_blocks(), out_dir="kg-out"), SessionContext(id="s"))

    assert len(out.metadata["wrote"]) == 2
    assert (tmp_path / "kg-out" / "kg.json").exists()
    assert (tmp_path / "kg-out" / "kg.mmd").exists()


def test_kg_adapter_run_is_json_serializable_and_listed() -> None:
    sub = ClioAuthorSubagent(CannedLLMClient(_KG_JSON))
    caps = sub.capabilities()
    assert any(entry["action"] == "kg" for entry in caps["actions"])

    result = sub.run("kg", {"blocks": _blocks()})
    assert result["action"] == "kg"
    assert json.loads(json.dumps(result)) == result


def test_kg_cli_blocks_json_exit_zero(capsys) -> None:
    from clio_author.cli import main

    code = main(["kg", "--blocks-json", json.dumps(_blocks())])
    out = capsys.readouterr().out
    result = json.loads(out)
    # Offline echo client -> parse_error metadata, but exit follows the error rule.
    assert result["action"] == "kg"
    # echo path flags parse_error (not an error), so the CLI still exits 0.
    assert code == 0


def test_kg_full_pipeline_under_echo_returns_report() -> None:
    """The `full` flag runs the multi-stage pipeline deterministically under echo."""
    expert = KGExpert(EchoLLMClient())
    out = expert.run(_task(blocks=_blocks(), full=True), SessionContext(id="s"))

    assert out.structured is not None
    pipeline = out.metadata["pipeline"]
    assert pipeline["order"] == [
        "metadata",
        "ontology",
        "extraction",
        "coref",
        "verification",
        "summary",
    ]
    # checkpoints round-trip for resume and the whole output is JSON-serializable.
    assert set(out.metadata["checkpoints"]) >= {"metadata", "summary"}
    assert json.loads(json.dumps(out.metadata)) == out.metadata


def test_kg_stages_subset_runs_only_requested_stages() -> None:
    expert = KGExpert(EchoLLMClient())
    out = expert.run(_task(blocks=_blocks(), stages="metadata,ontology"), SessionContext(id="s"))
    assert out.metadata["pipeline"]["order"] == ["metadata", "ontology"]


def test_build_kg_batches_and_merges_across_sections() -> None:
    """Many sections are split into batches; duplicate entities merge by type+label."""
    from clio_author.ingest.blocks import MemoryBlocks, SectionBlock
    from clio_author.retrieval.kg import build_kg_from_llm

    # A canned client returns the SAME node every call -> across batches it must
    # dedupe to ONE node, proving the merge (not N copies).
    canned = (
        '```json\n{"nodes": [{"id": "m1", "label": "Transformer", "type": "method"}], '
        '"edges": []}\n```'
    )

    class CannedLLM:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages, **kw):  # type: ignore[no-untyped-def]
            self.calls += 1
            return canned

    blocks = MemoryBlocks(
        metadata={},
        sections=[
            SectionBlock(section_path=f"S{i}", title=f"S{i}", text=f"body {i}") for i in range(13)
        ],
    )
    llm = CannedLLM()
    graph, err = build_kg_from_llm(blocks, llm, batch_size=6)
    assert err is None
    assert llm.calls == 3  # 13 sections / 6 per batch -> 3 LLM calls (batched)
    assert len(graph.nodes) == 1  # deduped by (type, label) across batches


def test_build_kg_partial_parse_failure_is_tolerated() -> None:
    """If some batches parse and some don't, return what parsed (error=None)."""
    from clio_author.ingest.blocks import MemoryBlocks, SectionBlock
    from clio_author.retrieval.kg import build_kg_from_llm

    good = '```json\n{"nodes": [{"id": "m1", "label": "X", "type": "method"}], "edges": []}\n```'

    class FlakyLLM:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages, **kw):  # type: ignore[no-untyped-def]
            self.calls += 1
            return good if self.calls == 1 else "no json here"

    blocks = MemoryBlocks(
        metadata={},
        sections=[SectionBlock(section_path=f"S{i}", title=f"S{i}", text="b") for i in range(12)],
    )
    graph, err = build_kg_from_llm(blocks, FlakyLLM(), batch_size=6)
    assert err is None  # partial success
    assert len(graph.nodes) == 1


def test_kg_writes_to_out_dir_without_constructor_files(tmp_path) -> None:
    """Regression: `kg --json {out_dir}` must persist kg.json/kg.mmd even when the
    expert was built with no SafeFiles (the CLI/adapter path)."""
    from clio_author.experts.kg import KGExpert
    from clio_author.harness.session import SessionContext
    from clio_author.harness.types import Task

    canned = (
        '```json\n{"nodes":[{"id":"m1","label":"Transformer","type":"method"}],"edges":[]}\n```'
    )

    class CannedLLM:
        def complete(self, messages, **kw):  # type: ignore[no-untyped-def]
            return canned

    out = tmp_path / "kg-out"
    expert = KGExpert(CannedLLM())  # NO files= passed (mirrors agent/CLI)
    result = expert.run(
        Task(
            id="t",
            description="kg",
            payload={
                "blocks": {
                    "metadata": {},
                    "sections": [{"section_path": "S", "title": "S", "text": "x"}],
                },
                "out_dir": str(out),
            },
        ),
        SessionContext(id="s"),
    )
    assert (out / "kg.json").exists(), "kg.json was not written from payload out_dir"
    assert (out / "kg.mmd").exists(), "kg.mmd was not written from payload out_dir"
    assert any(str(out) in p for p in result.metadata["wrote"])

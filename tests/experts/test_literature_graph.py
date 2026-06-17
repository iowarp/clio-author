"""Hermetic tests for :class:`LiteratureGraphExpert`."""

from __future__ import annotations

from clio_parser.experts.literature_graph import LiteratureGraphExpert
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import Task
from clio_parser.retrieval.literature_graph import GraphEdge, GraphSeed, LiteratureGraph, PaperNode


class FakeGraphClient:
    def build_graph(
        self,
        seeds: list[GraphSeed],
        *,
        max_nodes: int = 40,
        per_seed: int = 8,
    ) -> LiteratureGraph:
        seed = PaperNode(
            id="s2:seed",
            title=seeds[0].title or "Seed",
            year=2020,
            citation_count=10,
            source="semantic_scholar",
            role="seed",
            ingest_source=seeds[0].title or "Seed",
        )
        related = PaperNode(
            id="s2:related",
            title="Related",
            year=2021,
            citation_count=5,
            source="semantic_scholar",
            role="related",
            ingest_source="Related",
        )
        return LiteratureGraph(
            backend="semantic",
            seeds=[seed.title],
            nodes=[seed, related],
            edges=[GraphEdge(source=seed.id, target=related.id, type="recommendation")],
            related_works=[related.id],
        )


def _task(**payload: object) -> Task:
    return Task(id="t", description="literature_graph", payload=payload)


def test_literature_graph_expert_builds_graph_and_writes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    session = SessionContext(id="s")
    expert = LiteratureGraphExpert(client=FakeGraphClient())

    out = expert.run(_task(seed="Seed Paper", out_dir=str(tmp_path)), session)

    assert out.agent == "literature_graph"
    assert out.metadata["num_nodes"] == 2
    assert out.metadata["num_edges"] == 1
    assert (tmp_path / "graph.json").exists()
    assert (tmp_path / "graph.html").exists()
    assert session.history == [out]


def test_literature_graph_expert_errors_without_client() -> None:
    out = LiteratureGraphExpert().run(_task(seed="Seed Paper"), SessionContext(id="s"))

    assert "error" in out.metadata


def test_literature_graph_expert_errors_without_seed() -> None:
    out = LiteratureGraphExpert(client=FakeGraphClient()).run(_task(), SessionContext(id="s"))

    assert "error" in out.metadata

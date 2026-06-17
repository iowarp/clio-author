"""Hermetic tests for literature graph models, rendering, and backend resolution."""

from __future__ import annotations

import json

import pytest

from clio_parser.retrieval.literature_graph import (
    GraphEdge,
    GraphSeed,
    LiteratureGraph,
    PaperNode,
    coerce_seeds,
    graph_slug,
    render_graph_html,
    resolve_literature_graph_client,
    write_graph_artifacts,
)


def _graph() -> LiteratureGraph:
    seed = PaperNode(
        id="s2:seed",
        title="Seed Paper",
        authors=["Ada Lovelace"],
        year=2020,
        citation_count=100,
        url="https://www.semanticscholar.org/paper/seed",
        source="semantic_scholar",
        role="seed",
        ingest_source="Seed Paper",
    )
    prior = PaperNode(
        id="s2:prior",
        title="Prior Paper",
        year=2018,
        citation_count=50,
        source="semantic_scholar",
        role="prior",
        ingest_source="Prior Paper",
    )
    return LiteratureGraph(
        backend="semantic",
        seeds=["Seed Paper"],
        nodes=[seed, prior],
        edges=[GraphEdge(source=seed.id, target=prior.id, type="citation")],
        prior_works=[prior.id],
    )


def test_coerce_seeds_accepts_strings_dicts_and_lists() -> None:
    seeds = coerce_seeds(["Paper A", {"title": "Paper B", "year": 2024}])

    assert [seed.title for seed in seeds] == ["Paper A", "Paper B"]
    assert seeds[1].year == 2024


def test_coerce_seeds_rejects_bad_shape() -> None:
    with pytest.raises(ValueError, match="seeds"):
        coerce_seeds(123)


def test_render_graph_html_contains_data_and_ingest_command() -> None:
    html = render_graph_html(_graph())

    assert "<svg" in html
    assert "clio-parser ingest" in html
    assert "Seed Paper" in html
    assert "publication year" in html
    graph_data = html.split('<script id="graph-data" type="application/json">', 1)[1].split(
        "</script>", 1
    )[0]
    assert "&quot;" not in graph_data
    assert '"nodes"' in graph_data


def test_write_graph_artifacts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    wrote = write_graph_artifacts(_graph(), tmp_path)

    assert {path.rsplit("/", 1)[-1] for path in wrote} == {"graph.json", "graph.html"}
    data = json.loads((tmp_path / "graph.json").read_text())
    assert data["backend"] == "semantic"
    assert (tmp_path / "graph.html").read_text().startswith("<!doctype html>")


def test_graph_slug_is_filesystem_safe() -> None:
    assert graph_slug("Attention Is All You Need!") == "Attention-Is-All-You-Need"


def test_resolve_literature_graph_client_modes() -> None:
    assert resolve_literature_graph_client("off") is None
    assert (
        resolve_literature_graph_client("semantic").__class__.__name__
        == "SemanticScholarGraphClient"
    )
    assert resolve_literature_graph_client("openalex").__class__.__name__ == "OpenAlexGraphClient"
    assert (
        resolve_literature_graph_client("auto").__class__.__name__ == "CascadeLiteratureGraphClient"
    )
    with pytest.raises(ValueError, match="CLIO_GRAPH"):
        resolve_literature_graph_client("bad")


class FakeGraphClient:
    def build_graph(self, seeds: list[GraphSeed], *, max_nodes: int = 40, per_seed: int = 8):
        graph = _graph()
        return graph.model_copy(update={"seeds": [seed.title or "paper" for seed in seeds]})


def test_fake_graph_client_protocol_shape() -> None:
    graph = FakeGraphClient().build_graph([GraphSeed(title="A")])

    assert graph.backend == "semantic"
    assert graph.seeds == ["A"]

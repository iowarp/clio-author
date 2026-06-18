"""Hermetic tests for the retrieval layer (no network, no heavy deps).

Exercises :class:`HashingEmbedder` determinism, :class:`RagRetriever` ranking
(lexical match ranks first), k/kinds filtering and stable tie-break,
:func:`inject_context` (all/section/topk) and :func:`render_scored`.
"""

from __future__ import annotations

from clio_author.ingest.blocks import Equation, FigureInfo, MemoryBlocks, SectionBlock
from clio_author.retrieval.rag import (
    HashingEmbedder,
    RagRetriever,
    ScoredBlock,
    inject_context,
    render_scored,
)


def _blocks() -> MemoryBlocks:
    return MemoryBlocks(
        sections=[
            SectionBlock(
                section_path="Methods",
                title="Methods",
                text="We train a transformer with gradient descent on tokens.",
            ),
            SectionBlock(
                section_path="Methods > Dataset",
                title="Dataset",
                text="The corpus contains photosynthesis chlorophyll measurements.",
            ),
            SectionBlock(
                section_path="Results",
                title="Results",
                text="Accuracy improved across all benchmarks.",
            ),
        ],
        figures=[FigureInfo(figure_id=1, caption="A transformer attention diagram.")],
        equations=[Equation(index=0, latex="E = mc^2")],
    )


def test_hashing_embedder_is_deterministic() -> None:
    emb = HashingEmbedder()
    a = emb.embed(["the quick brown fox", "another sentence"])
    b = emb.embed(["the quick brown fox", "another sentence"])
    assert a == b
    assert len(a[0]) == emb.dim
    # L2-normalized.
    norm = sum(value * value for value in a[0]) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_hashing_embedder_empty_text_is_zero_vector() -> None:
    [vec] = HashingEmbedder().embed([""])
    assert vec == [0.0] * HashingEmbedder().dim


def test_retriever_ranks_lexical_match_first() -> None:
    retriever = RagRetriever()
    retriever.index(_blocks())
    results = retriever.search("photosynthesis chlorophyll", k=5)
    assert results, "expected at least one result"
    assert results[0].block.block_id == "section:methods-dataset"
    # Scores are sorted descending.
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retriever_k_limit() -> None:
    retriever = RagRetriever()
    retriever.index(_blocks())
    results = retriever.search("transformer", k=2)
    assert len(results) == 2


def test_retriever_kinds_filter() -> None:
    retriever = RagRetriever()
    retriever.index(_blocks())
    results = retriever.search("transformer", k=10, kinds=["figure"])
    assert results
    assert all(r.block.kind == "figure" for r in results)


def test_retriever_stable_tiebreak_by_block_id() -> None:
    # A query whose tokens appear in no block -> all scores 0.0 -> deterministic
    # ascending block_id order.
    retriever = RagRetriever()
    retriever.index(_blocks())
    results = retriever.search("qwxz zzzqqq wxyzzz", k=10)
    assert all(r.score == 0.0 for r in results)
    ids = [r.block.block_id for r in results]
    assert ids == sorted(ids)


def test_retriever_empty_index_returns_empty() -> None:
    retriever = RagRetriever()
    retriever.index(MemoryBlocks())
    assert retriever.search("anything") == []


def test_index_is_idempotent_and_replaces() -> None:
    retriever = RagRetriever()
    retriever.index(_blocks())
    retriever.index(MemoryBlocks(sections=[SectionBlock(section_path="Only", title="Only")]))
    results = retriever.search("only", k=10)
    assert [r.block.block_id for r in results] == ["section:only"]


def test_scored_block_to_dict_is_json_safe() -> None:
    block = SectionBlock(section_path="Methods", title="Methods", text="x")
    sb = ScoredBlock(block=block, score=0.5)
    assert sb.to_dict() == {"block_id": "section:methods", "kind": "section", "score": 0.5}


def test_render_scored_returns_ids_in_order() -> None:
    blocks = _blocks()
    retriever = RagRetriever()
    retriever.index(blocks)
    scored = retriever.search("transformer attention", k=3)
    context, ids = render_scored(scored)
    assert ids == [s.block.block_id for s in scored]
    assert isinstance(context, str)
    assert context  # non-empty


def test_inject_context_all() -> None:
    blocks = _blocks()
    out = inject_context(blocks, mode="all")
    assert "Methods" in out
    assert "Results" in out
    assert "Figure 1" in out


def test_inject_context_section() -> None:
    blocks = _blocks()
    out = inject_context(blocks, mode="section", section_path="Methods")
    assert "Methods" in out
    assert "Dataset" in out
    assert "Results" not in out


def test_inject_context_topk() -> None:
    blocks = _blocks()
    out = inject_context(blocks, mode="topk", query="photosynthesis chlorophyll", k=1)
    assert "photosynthesis" in out.lower()
    assert "Results" not in out

"""Live backend tests for the LanceDB / SentenceTransformer retrieval path.

Gated by the ``live`` marker and skipped unless the ``rag`` extra is installed
(``uv sync --extra rag``). Runs a tiny index + search end-to-end through the
real backend.
"""

from __future__ import annotations

import pytest

from clio_author.ingest.blocks import MemoryBlocks, SectionBlock

pytestmark = pytest.mark.live


def _blocks() -> MemoryBlocks:
    return MemoryBlocks(
        sections=[
            SectionBlock(
                section_path="Methods",
                title="Methods",
                text="We train a neural network with stochastic gradient descent.",
            ),
            SectionBlock(
                section_path="Biology",
                title="Biology",
                text="Photosynthesis converts light into chemical energy in chloroplasts.",
            ),
        ]
    )


def test_lancedb_retriever_index_and_search(tmp_path) -> None:  # type: ignore[no-untyped-def]
    pytest.importorskip("lancedb")
    pytest.importorskip("sentence_transformers")

    from clio_author.retrieval.rag import LanceDbRetriever, SentenceTransformerEmbedder

    retriever = LanceDbRetriever(
        embedder=SentenceTransformerEmbedder(),
        uri=str(tmp_path / "lancedb"),
    )
    retriever.index(_blocks())
    results = retriever.search("photosynthesis chloroplasts", k=2)

    assert results
    assert results[0].block.block_id == "section:biology"

    # A pushed-down kinds filter returns matching blocks (all are sections here).
    filtered = retriever.search("photosynthesis chloroplasts", k=2, kinds=["section"])
    assert filtered
    assert all(item.block.kind == "section" for item in filtered)

    # A kind with no indexed blocks returns nothing (no under-counted fallback).
    assert retriever.search("photosynthesis chloroplasts", k=2, kinds=["figure"]) == []

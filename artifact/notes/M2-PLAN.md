# M2 Build Plan — Retrieval + Selective Injection + `paper_qa`

Adds `clio_author/retrieval/rag.py` and `clio_author/experts/paper_qa.py` on top of the M1
memory-block model and M0 harness. Hermetic-first; heavy backend (LanceDB + real embeddings) behind
an optional `rag` extra with lazy imports (mirrors the M1 `pdf` extra + `live` marker).

## Decisions
- **Granularity:** one vector per `Block` (`MemoryBlocks.all_blocks()`), embedding each block's
  `to_context("full")`. Sub-chunking long sections deferred (note in docstring).
- **Default embedder:** deterministic `HashingEmbedder` (hashed term-frequency, L2-normalized,
  cosine) — pure stdlib, reproducible rankings, no numpy/network. Same `embed→vector→cosine` shape
  as the live backend so the `RagRetriever` code path is identical hermetic vs. live.
- Reuse `MemoryBlocks.select`/`Block.to_context`/`block_id` — retrieval ranks, injection composes.
- `paper_qa` fits the M0 harness (`BaseAgent`/`AgentProtocol`, runs via `Engine`/`Sequential`),
  testable with `EchoLLMClient`; never raises (mirror `IngestorExpert`).
- Clean-room; phagocyte processor (LanceDB/Qwen3/OpenCLIP/bge) is behavior reference only.

## Steps
1. **Deps/gating** (`pyproject.toml`): optional `rag = [lancedb, sentence-transformers, numpy]`;
   mypy overrides for those modules; reuse existing `live` marker (no new marker).
2. **`retrieval/rag.py`** (clean-room header): `RetrievalDependencyError`; `Embedder` Protocol
   (`embed(texts)->vectors`); `HashingEmbedder` (hermetic default); `ScoredBlock` (carry the `Block`
   + `score` in memory; serialize only `{block_id,kind,score}`); `RagRetriever(embedder=None)` with
   `index(blocks)` (embed each `to_context("full")`, store in-memory) and
   `search(query,k,kinds=None)->list[ScoredBlock]` (cosine, optional kind filter, stable tie-break
   by `block_id`). **Optional lazy** `SentenceTransformerEmbedder` + `LanceDbRetriever` (same
   `index`/`search`; lazy-import lancedb/sentence_transformers/numpy; raise
   `RetrievalDependencyError` with `uv sync --extra rag` hint).
3. **Selective injection** (in `rag.py`): `inject_context(blocks, retriever=None, query=None,
   mode="topk"|"section"|"all", k=5, detail="summary", section_path=None) -> str` (reuse
   `select` for all/section, `to_context` for topk); `render_scored(scored, detail) ->
   (joined_context, [block_id,...])`.
4. **`experts/paper_qa.py`**: `PaperQAExpert(BaseAgent)` role `paper_qa`; `run` reads
   `task.payload["question"]` (fallback `task.description`) + `["blocks"]` (accept `MemoryBlocks` OR
   its `model_dump()` dict via `model_validate`); index → search(k) → `render_scored` → compose
   system+user messages (module-level prompt template) → `llm.complete` → `AgentOutput(content=answer,
   structured={cited_block_ids, retrieved:[{block_id,kind,score}]}, metadata={k,num_blocks})`;
   append to session; never raise (error-flagged output on missing question/blocks/failure).
5. **Tests**: hermetic `tests/retrieval/test_rag.py` (embedder determinism; ranking + k/kinds filter
   + stable tie-break; `inject_context` all/section/topk; `render_scored`); hermetic
   `tests/experts/test_paper_qa.py` (cited ids; prompt composition via a recording fake client;
   accepts MemoryBlocks + dict; missing-question/blocks error paths; runs through Engine/Sequential).
   Gated `tests/retrieval/test_rag_live.py` (`@pytest.mark.live` + `importorskip`) for
   LanceDb/SentenceTransformer.
6. **Licensing/notes**: clean-room header; `__all__` exports; progress agent updates PROGRESS after.

## Smallest first slice
`HashingEmbedder` + `RagRetriever` + `inject_context`/`render_scored` + `PaperQAExpert` w/
`EchoLLMClient` + hermetic tests = end-to-end grounded Q&A, zero heavy deps. LanceDB backend + live
tests are additive.

## Risks
- `ScoredBlock` serialization: keep `structured["retrieved"]` as `{block_id,kind,score}` dicts only
  (JSON-safe; don't serialize the polymorphic `Block`).
- Keep `HashingEmbedder`/cosine pure-Python (no numpy on the hermetic path).
- Assert prompt composition via a recording fake LLM client, not only the echo.
- Re-index per `run` for M2 (index caching deferred).

## Verification
`uv run ruff check` / `mypy clio_author` clean; `uv run pytest` hermetic green (live/baseline
deselected); `uv run pytest -m live` (with `--extra rag`) for the backend; manual M1→M2 hand-off:
feed `IngestorExpert` `structured` dump as `paper_qa` `task.payload["blocks"]` via Engine/Sequential.

## Files
- Create: `clio_author/retrieval/{__init__,rag}.py`, `clio_author/experts/paper_qa.py`,
  `tests/retrieval/{__init__,test_rag,test_rag_live}.py`, `tests/experts/test_paper_qa.py`.
- Modify: `pyproject.toml`, `clio_author/experts/__init__.py` (export `PaperQAExpert`).
- Reuse (read-only): `ingest/blocks.py`, `experts/ingestor.py`, `harness/{base,types}.py`,
  `llm/client.py`, `ingest/docling_extract.py` (gating idiom), `tests/experts/test_ingestor.py` (shape).

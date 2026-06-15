# M1 Build Plan — Processing Track

arXiv/PDF → clean scientific Markdown + memory blocks, via an `ingestor` expert, with a baseline
diff against the reference implementations. Approved direction; execute with the `coder` agent.

## Context
M0 ships a working sync harness (`BaseAgent.run(task, session) -> AgentOutput`, `Sequential`,
`SessionContext`, Pydantic `types.py`, `EchoExpert`/`EchoLLMClient`). M1 adds the processing core
under `clio_parser/ingest/` and an `ingestor` expert. The biggest quality lever is the deterministic
regex post-process pass layered on Docling — pure-Python, no heavy deps, landable and testable
hermetically first; Docling/PyMuPDF extraction is a thin, dependency-gated wrapper.

Reference impls (both "Ported from paper-to-md"): phagocyte
`artifact/repos/phagocyte/src/ingestor/src/ingestor/extractors/pdf/postprocess/` (6 modules +
`equations.py`) and paper-to-md (MIT, © 2025 Jaime Cernuda; richer enrichment JSON, no equations
pass). Fixed pass order (order matters): **sections → citations → equations → figures →
bibliography → cleanup**. Entry: `process_markdown(content: str, images: list[str] | None) -> str`.

**Smallest first slice (acceptance):** Step 0 (deps) + Step 1 (postprocess port, hermetic) +
minimal Step 3 (`docling_extract.process_pdf(source) -> ExtractionResult`) + minimal Step 5
(`ingestor` expert returning markdown) → converts an arXiv URL to clean Markdown end-to-end. Blocks
(Step 4) + baseline harness (Step 6) land immediately after.

## Steps
0. **Deps + hermetic gating** — `uv add` docling/pymupdf/pillow/httpx as an **optional `pdf` extra**
   (not core); lazy-import inside functions (phagocyte pattern, `pdf_extractor.py:31-47,246-249`).
   Add pytest markers `live`/`baseline` and `addopts = "-m 'not live and not baseline'"` so the
   default suite stays hermetic. (Docling pulls ~500MB models on first run — never a hard dep.)
1. **`ingest/postprocess/`** — clean-room re-port of the 6 passes (regex-only):
   `sections.py` (heading reconstruction from numbering, Roman, `_is_section_title` guard),
   `citations.py` (`[7]`→`[[7]](#ref-7)`, range expansion, anchors; idempotent; don't link years),
   `equations.py` (de-spacing, delimiter normalization; **move transformer/GAN-specific regexes into
   an opt-in `domain_fixes` table** — default pass is generic only), `figures.py` (embed-at-caption,
   idempotent, size-filtered), `bibliography.py` (entry spacing), `cleanup.py` (ligatures/glyphs/
   blank-lines; **must not corrupt `|` table rows**). `__init__.py` exposes `process_markdown`.
2. (folded into 1) equation generalization + **table-fidelity gap deferred to M7** (`ingest/tables.py`).
3. **`ingest/docling_extract.py`** — `PdfConfig` (images_scale=2.0, size filters, flags);
   `resolve_arxiv_url` (ID/abs URL → `arxiv.org/pdf/<id>.pdf`); `download_pdf` (httpx); `extract`
   (Docling primary w/ `do_formula_enrichment` + size-filtered `figureN.png`; PyMuPDF OCR fallback;
   **synchronous** to match M0); `ExtractionResult{markdown,images,metadata,extractor,source_url}`
   (stamp `extractor` to flag degraded OCR mode); `process_pdf` orchestrates resolve→download→
   extract→`process_markdown`.
4. **`ingest/blocks.py`** — Pydantic v2: `FigureInfo`, `Equation`, `CodeBlock`, **new**
   `SectionBlock{section_path,title,text,page_range}`, and a `MemoryBlocks` container (paper-to-md
   `enrichments` shape + `sections`). Each block: stable `block_id` + `to_context(detail)`;
   `MemoryBlocks.select(kinds, section_path, max_blocks)` for **selective injection** (seam for M2
   RAG). M1 must-haves derivable without extra Docling passes: `SectionBlock` + `FigureInfo`
   (description filled later by `figure_agent` in M6).
5. **`experts/ingestor.py`** — `IngestorExpert(BaseAgent)`, `role="ingestor"`; **override `run`**
   (deterministic, not LLM): read `task.payload["source"]`, call `process_pdf`, build `MemoryBlocks`,
   return `AgentOutput(content=markdown, structured=blocks.model_dump(), metadata={extractor,...})`.
   Lazy-import heavy deps; on missing deps/failure return an error-flagged `AgentOutput` (don't
   raise). Fits the M0 contract with zero harness changes; verify it runs through `Sequential`.
6. **Tests** — hermetic unit tests per postprocess module (fixture strings) + `test_blocks.py` +
   `test_ingestor.py` (monkeypatch `process_pdf`). **Baseline harness** `tests/baselines/` (gated
   `live`/`baseline`): the load-bearing test compares **our `process_markdown` vs phagocyte's on
   identical raw Markdown** (isolates the port from Docling nondeterminism); plus coarse full-pipeline
   metrics (section/citation/figure/reference counts within tolerance) on the two `artifact/papers/`
   PDFs, recorded to a report for the M7 eval.
7. **Licensing** — preserve MIT attribution where logic mirrors paper-to-md (header: "Re-implemented
   from the paper-to-md project (MIT, © 2025 Jaime Cernuda), <repo URL>"). Phagocyte license
   unspecified → clean-room re-implementation from the notes' behavior descriptions, **no verbatim
   copy**. **[Human decision]** confirm phagocyte attribution wording before merge. Keep BSD-3.

## Risks / decisions
- **[Human]** phagocyte attribution wording (license unspecified) — clean-room, confirm before merge.
- **Sync vs async:** keep M1 sync (Docling CPU-bound; harness sync). Async is a later cross-cutting concern.
- **Deps optional, not core:** keeps imports + default tests hermetic; expert degrades gracefully.
- **Equation regex brittleness:** domain fixes opt-in; document as heuristic, not a general repairer.
- **Figure-number/`figure_id` misalignment:** use Docling's saved order as source of truth; defer
  printed-number reconciliation to M7/`figure_agent`. Avoid paper-to-md's enumerate-all-pictures bug.
- **Table fidelity:** out of scope for M1; cleanup must not corrupt `|`-rows; `tables.py` → M7.
- **Baseline determinism:** compare postprocess-vs-postprocess on identical raw Markdown, not full-text equality.

## Verification
1. `uv run pytest` (default hermetic) — postprocess + blocks + ingestor unit tests pass, no network/Docling.
2. `uv run ruff check` / `format` + `uv run mypy clio_parser/ingest clio_parser/experts/ingestor.py` clean.
3. `uv run pytest -m baseline` — port-equivalence (exact) + full-pipeline metrics within tolerance on the 2 PDFs.
4. **Manual smoke (first-slice acceptance):** `uv run --extra pdf` ingest of arXiv `2601.23265` →
   clean Markdown + populated `MemoryBlocks` (sections + figures).

## Files
- Create: `clio_parser/ingest/__init__.py`, `ingest/postprocess/{__init__,sections,citations,equations,figures,bibliography,cleanup}.py`, `ingest/docling_extract.py`, `ingest/blocks.py`, `experts/ingestor.py`.
- Modify: `pyproject.toml` (optional `pdf` extra + markers), `experts/__init__.py`.
- Tests: `tests/ingest/test_*.py`, `tests/experts/test_ingestor.py`, `tests/baselines/{conftest,test_pdf_to_md}.py` (+ `__init__.py`).
- Reuse (read-only): `clio_parser/harness/{base,protocol,types,patterns,session}.py`, `llm/client.py`.
- Behavior refs (read-only, clean-room): phagocyte `extractors/pdf/postprocess/*.py` + `pdf_extractor.py`; schemas from `paper-to-md.md` §6.
- Fixtures: `artifact/papers/2601.23265-paperbanana.pdf`, `2604.05018-paperorchestra.pdf`.

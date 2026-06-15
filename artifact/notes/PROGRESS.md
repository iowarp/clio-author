# PROGRESS — clio-parser

Living status ledger. Maintained by the `progress` subagent (see `.claude/agents/progress.md`).
Status legend: ✅ done · 🚧 in progress · ⬜ not started · ⛔ blocked.

**Last updated:** 2026-06-15
**Where we left off:** **M4 merged (PR #5). M5 code-complete and reviewed** on branch
`feat/m5-writing` — `tools/files.py` (`SafeFiles`: sandbox-confined read/write_new/apply_edit,
escape-tested) + `experts/{write_models,writer,editor,write_loop}.py` (wtf-p outline→plan→write→
revise taxonomy; `ReviewerAsCritic` + `run_write_review_loop` over `CriticRefine` — writer↔reviewer
loop terminates on Accept). 207 hermetic tests; ruff + mypy clean; reviewed (APPROVE-WITH-NITS →
applied). The **write-papers** half is now functional. Autonomously continuing through **M6**
(figures — PaperBanana), **M7** (hardening), **M8** (CLIO adapter). See the **Session log** to resume.

## Setup phases

| # | Item | Status | Evidence |
|---|---|---|---|
| P0 | Acquire artifacts → `artifact/` | ✅ | 7 repos in `artifact/repos/`, 2 PDFs in `artifact/papers/`, `MANIFEST.md` |
| P1 | Deep study (per-artifact notes) | ✅ | 9 notes in `artifact/notes/` (clio, phagocyte, paper-to-md, wtf-p, protoneo, papervizagent, 2 papers) |
| P2 | Comparative synthesis | ✅ | `artifact/notes/SYNTHESIS.md` |
| P3 | Design (architecture + build form) | ✅ | `artifact/notes/DESIGN.md` (standalone harness) |
| P4 | Dev harness (`.claude/`) | ✅ | `CLAUDE.md`, `settings.json`, 7 agents, 2 skills |

## Build milestones (from DESIGN.md §5)

| # | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Harness skeleton (`BaseAgent`, `AgentProtocol`, engine, patterns, session, types) + trivial expert; `ClioParserAgent.invoke()` runs | ✅ | `clio_parser/harness/` + `agent.py` + `experts/echo.py` + `llm/client.py`; 4 tests pass, ruff/mypy clean |
| M1 | Processing track: `ingest/` port + `ingestor` expert → Markdown + memory blocks; baseline diff | ✅ | `ingest/{postprocess,blocks,docling_extract}` + `experts/ingestor.py` + `tests/baselines/`; 89 hermetic tests + 3 port-equivalence (byte-match phagocyte); reviewed. Live real-PDF run gated (needs `pdf` extra + network) |
| M2 | Memory blocks + selective injection + `rag` retrieval; `paper_qa` | ✅ | `retrieval/rag.py` (HashingEmbedder default + lazy LanceDb/SentenceTransformer) + `experts/paper_qa.py`; 109 hermetic tests; reviewed. Real-embedding backend gated (`rag` extra) |
| M3 | Grounding: `scholar` (Semantic Scholar) + `citation` expert | ✅ | `retrieval/scholar.py` (pure verification + lazy S2 client) + `experts/citation.py` (suggestions-only, bib-safe); 140 hermetic tests; reviewed (CHANGES-NEEDED → fixed: cutoff gate + symlink-safe write). S2 calls gated (`scholar` extra) |
| M4 | Review: `reviewer` + critic-refine pattern + multi-reviewer | ✅ | `Parallel`+`CriticRefine` patterns implemented; `experts/{review_models,reviewer,meta_reviewer}.py` (AgentReview rubric, `run_panel`); 167 hermetic tests; reviewed (APPROVE-WITH-NITS → fixed). `RoundRobin` still stub |
| M5 | Write/edit: `writer` + `editor` + file tools | ✅ | `tools/files.py` (SafeFiles, sandbox-verified) + `experts/{write_models,writer,editor,write_loop}.py` (`run_write_review_loop` via CriticRefine); 207 hermetic tests; reviewed (APPROVE-WITH-NITS → applied) |
| M6 | Figures (optional): `figure_agent` generation | ✅ | `experts/{figure_models,figure_agent}.py` (describe + matplotlib code-gen; gated `render_plot_code`; `run_figure_refine` via CriticRefine); 224 hermetic tests; reviewed. Diagram image-gen + vision deferred |
| M7 | Harden gaps: table fidelity, generalized equations, baseline eval report | ⬜ | |
| M8 | CLIO integration: thin `clio_adapter` so CLIO can invoke the harness | ⬜ | deferred |

## Open decisions / pending inputs

- ✅ **Agent framework** — plain Python + Pydantic v2 + a pluggable, synchronous `LLMClient` (M0);
  DSPy / LiteLLM / async deferred to concrete `LLMClient` implementations at the seam.
- ✅ **Writing scope** — all capabilities, phased (review → HITL writing → autonomous).
- ⬜ **Default VLM / embedding models** for vision + RAG.
- ⛔ **Phagocyte license** — unspecified upstream; confirm before lifting code verbatim (plan is a fresh port regardless).

## Session log (resume here)

### 2026-06-15 — Session 6: merge PR #4 (M3), build M4 (review)
**Done this session:**
- Merged **PR #4** (M3) to `main`. Started branch `feat/m4-review`.
- **M4 complete:** implemented the `Parallel` (sequential-collect, input-order) and `CriticRefine`
  (producer↔critic, `max_rounds`, `NO_CHANGES_SENTINEL` short-circuit, full round history, never-raises)
  harness patterns. Added `experts/review_models.py` (AgentReview rubric: `PaperReview` with clamped
  axes + `from_loose_dict`, `PersonaSpec`, `MetaReview`), `experts/reviewer.py` (`ReviewerExpert`,
  stdlib-only JSON parse, `parse_error` degradation), `experts/meta_reviewer.py` (`MetaReviewerExpert`
  deterministic aggregation + `run_panel` over `Parallel`). Rubric adapted from PaperOrchestra
  (Apache-2.0); IndependentSynthesis concept re-implemented (no AGPL copy).
- **Review = APPROVE-WITH-NITS → fixed:** `max_rounds` non-int coercion (never-raises), decision
  substring doc + test, import order. 167 hermetic tests pass.

**Stopped at:** M4 code-complete, reviewed, fixed, verified on `feat/m4-review` (committing now).

**Next step:** open the M4 PR; then **M5** — write/edit: `writer`/`editor` experts (wtf-p taxonomy:
outline→plan→write→revise), file read/write/edit tools, and wire writer↔reviewer through
`CriticRefine`. This brings in **wtf-p** and completes the "write papers" half. See `DESIGN.md` §2.3.


### 2026-06-15 — Session 5: merge PR #3 (M2), build M3 (citation grounding)
**Done this session:**
- Merged **PR #3** (M2) to `main`. Started branch `feat/m3-citation`.
- **M3 complete:** `retrieval/scholar.py` — `Reference`/`Candidate`/`S2Record`/`VerifiedCitation`
  models, `ScholarClient` protocol, lazy `SemanticScholarClient`, hermetic `FakeScholarClient`, and
  pure verification (`fuzzy_ratio` thefuzz|difflib, `is_date_valid`, `best_match`, `dedupe`,
  `verified_coverage` ≥90%, `to_bibtex`, `verify`). `experts/citation.py` — `CitationExpert`:
  discover→verify→**suggestions only**; refuses overwriting `references.bib`; never raises.
  Verification logic adapted from PaperOrchestra (Apache-2.0, attributed).
- **Review = CHANGES-NEEDED → fixed:** (1) `cutoff_date` was a no-op → now gated in `best_match`;
  (2) write guard bypassable via dangling symlink → hardened with `is_symlink()` refusal + atomic
  `O_CREAT|O_EXCL|O_NOFOLLOW` write. 140 hermetic tests pass.

**Stopped at:** M3 code-complete, reviewed, fixed, verified on `feat/m3-citation` (committing now).

**Next step:** open the M3 PR; then **M4** — review: a `reviewer` expert using the `CriticRefine`
pattern (implement the stub) + an AgentReview-style rubric (PaperOrchestra) + multi-reviewer via the
`Parallel` pattern. See `DESIGN.md` §2.3.


Newest first. Each entry: what we decided, what we did, and where we stopped — so the next session
can continue from the last conversation without re-deriving context.

### 2026-06-15 — Session 4: merge PR #2 (M1), build M2 (retrieval + paper_qa)
**Done this session:**
- Merged **PR #2** (M1) to `main`. Started branch `feat/m2-retrieval`.
- **M2 complete:** `retrieval/rag.py` — `Embedder` protocol, deterministic `HashingEmbedder`
  (hermetic default, lexical), `RagRetriever` (cosine, kinds filter, stable tie-break),
  `inject_context`/`render_scored`, and a lazy `SentenceTransformerEmbedder` + `LanceDbRetriever`
  behind the optional `rag` extra. `experts/paper_qa.py` — `PaperQAExpert` (grounded Q&A, cited
  block ids, never-raises; accepts `MemoryBlocks` or its dump). 109 hermetic tests; reviewed
  (APPROVE-WITH-NITS, nits applied: lexical-limit docstring, LanceDb `kinds` pushdown, concurrency note).
- Verified M1→M2 hand-off (ingestor blocks → paper_qa retrieval + citation).

**Stopped at:** M2 code-complete, reviewed, fixed, verified on `feat/m2-retrieval` (committing now).

**Next step:** open the M2 PR; then **M3** — citation grounding: `retrieval/scholar.py` (Semantic
Scholar, fuzzy-match + date cutoff per PaperOrchestra) + a `citation` expert. See `DESIGN.md` §2.2/§2.3.

### 2026-06-15 — Session 3: merge PR #1, M1 hermetic core
**Done this session:**
- Merged **PR #1** to `main` (setup + M0). Started branch `feat/m1-processing`.
- **M1 part 1 (hermetic core):** built `clio_parser/ingest/postprocess/` (sections, citations,
  equations, figures, bibliography, cleanup) + `blocks.py` (`FigureInfo`/`Equation`/`CodeBlock`/
  `SectionBlock`/`MemoryBlocks` with `block_id`, `to_context`, `select`, and a section walker).
  Deps kept optional (`pdf` extra); default test suite hermetic.
- **Bug found + fixed:** top-level Arabic headings (`1. INTRODUCTION`) weren't promoted — fixed in
  `sections.py` with false-positive guards (sentences/list items not promoted). 67 tests pass.
- **Licensing:** 5 shared passes adapted from paper-to-md (MIT, attributed); equations clean-room.

- **M1 part 2:** `ingest/docling_extract.py` (`PdfConfig`, `resolve_arxiv_url`, `download_pdf`,
  Docling primary + PyMuPDF OCR fallback, `process_pdf`), `experts/ingestor.py` (`IngestorExpert`,
  never-raises contract), and the gated `tests/baselines/` harness. Code-reviewed
  (APPROVE-WITH-NITS); fixes applied (normalize extractor exceptions to `ExtractionError`, frozen
  `PdfConfig`, stricter arxiv host check). 89 hermetic tests pass.

**Stopped at:** M1 code-complete, reviewed, fixed, and verified on `feat/m1-processing` (committed +
pushed). Real-PDF baseline run gated (needs `pdf` extra + network).

**Next step:** open the M1 PR (`feat/m1-processing` → `main`); then **M2** — retrieval + selective
injection (`retrieval/rag.py` over the memory blocks) + a `paper_qa` path. See `DESIGN.md` §2.2.

### 2026-06-15 — Session 2: push, README, M0 skeleton
**Decisions made:**
- **Agent framework (M0):** plain Python + Pydantic v2 + a pluggable synchronous `LLMClient`
  (`EchoLLMClient` stub for hermetic tests). DSPy/LiteLLM/async deferred to concrete client impls.

**Done this session:**
- Pushed branch `setup/project-harness` to GitHub; wrote and pushed a real `README.md`.
- **M0 complete:** scaffolded `clio_parser/` (`harness/` types, protocol, base, session, patterns,
  engine; `llm/client.py`; `experts/echo.py`; `agent.py`) + `pyproject.toml` + tests. `Sequential`
  pattern implemented; `Parallel`/`RoundRobin`/`CriticRefine` are documented stubs.
- Verified: `uv run pytest` → 4 passed; `ruff` + `mypy` clean; `invoke("hello world")` works.

**Stopped at:** M0 done and verified; M0 commit pending push on `setup/project-harness`.

**Next step:** M1 — processing track. Use `planner` to plan the fresh port of the paper-to-md /
phagocyte post-processing into `clio_parser/ingest/`, then build the `ingestor` expert (PDF/arXiv →
scientific Markdown + memory blocks) and a baseline diff. Optionally run `code-reviewer` on M0 first.

### 2026-06-15 — Session 1: artifacts, design, dev harness
**Decisions made:**
- **Form (locked):** clio-parser is a **standalone, pure-Python multi-agent harness** — *not* an MCP
  server, *not* a Markdown/blueprint agent. The CLIO agent (`iowarp/clio-agent`, develop) will
  **invoke** it as a standalone subagent (thin adapter, deferred). Reference harnesses:
  `papervizagent` + `protoneo/knowledge`.
- **Ingest core:** fresh minimal port of the paper-to-md/phagocyte post-processing.
- **Writing scope:** all capabilities, phased (review → human-in-the-loop writing → autonomous).
- **Framework:** decide at M0 (plain Python+LiteLLM vs DSPy — prototype both).
- **License:** target BSD-3; re-implement AGPL `protoneo` concepts (no code copy); confirm
  Phagocyte license before lifting.
- **Docs rule:** notes must be publishable — no references to individuals/organizations or internal
  discussion; cite sources by repo URL + license only. (All notes scrubbed accordingly.)
- **Subagent models:** opus for planner/designer/coder/code-reviewer/debugger; sonnet for
  test-engineer/explorer/progress.

**Done this session:**
- Initialized git + pushed clio-parser to GitHub.
- Acquired 7 repos + 2 papers into `artifact/`; wrote `MANIFEST.md`.
- Deep-studied every artifact → 9 notes; wrote `SYNTHESIS.md` and `DESIGN.md`.
- Built the `.claude/` dev harness (CLAUDE.md, settings.json, 7 agents, 2 skills); verified all
  formats against official Claude Code docs.
- Added the `progress` agent (with a Session log) and the `doc-updater` agent; created this
  `PROGRESS.md` ledger.

**Stopped at:** setup complete (P0–P4). No build code yet. Everything uncommitted on `main`.

**Next step:** M0 — scaffold the harness skeleton (`clio_parser/harness/`: `BaseAgent`,
`AgentProtocol`, engine, patterns, session, types + a trivial expert so `ClioParserAgent.invoke()`
runs). Use `planner` to produce the M0 build plan first. (Optionally commit P0–P4 to a branch first.)

## Changelog

- 2026-06-15 — P0–P4 complete; `.claude/` dev harness standardized; progress ledger + session log created; `doc-updater` agent added.
- 2026-06-15 — branch pushed; README written; **M0 harness skeleton** complete (4 tests pass, ruff/mypy clean).
- 2026-06-15 — PR #1 merged to `main`; **M1 processing track** complete + reviewed on `feat/m1-processing` (89 hermetic tests + 3 port-equivalence vs phagocyte).
- 2026-06-15 — PR #2 (M1) merged; **M2 retrieval + paper_qa** complete + reviewed on `feat/m2-retrieval` (109 hermetic tests).
- 2026-06-15 — PR #3 (M2) merged; **M3 citation grounding** complete + reviewed (CHANGES-NEEDED → fixed) on `feat/m3-citation` (140 hermetic tests).
- 2026-06-15 — PR #4 (M3) merged; **M4 review** complete + reviewed (APPROVE-WITH-NITS → fixed) on `feat/m4-review` (167 hermetic tests; `Parallel`+`CriticRefine` patterns implemented).
- 2026-06-15 — PR #5 (M4) merged; **M5 write/edit** complete + reviewed (APPROVE-WITH-NITS → applied) on `feat/m5-writing` (207 hermetic tests; SafeFiles + writer/editor + write-review loop).
- 2026-06-15 — PR #6 (M5) merged; **M6 figures** complete + reviewed (APPROVE-WITH-NITS → applied) on `feat/m6-figures` (224 hermetic tests; figure_agent describe + plot-code).

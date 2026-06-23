# Changelog

All notable changes to clio-author are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Author-lifecycle framing.** Every manifest action now carries author-lifecycle metadata —
  a `phase` list (Frame · Gather · Plan · Draft · Strengthen · Referee · Respond · Ship · Drive) and
  a `needs_source` flag — surfaced in `capabilities()` alongside a new `lifecycle` phase catalog, so
  a host (or CLIO) can route by *what the author needs to do* rather than by action name. New
  `clio-author lifecycle` command prints the phase → actions map; new
  [`docs/LIFECYCLE.md`](docs/LIFECYCLE.md) tells the author's story with copy-paste recipes per phase;
  README §2 is reframed around the lifecycle. No behavior change to any action (metadata + docs only).

### Changed
- **Consolidated `edit` + `polish` into one `revise` action** (`mode: feedback|style`) to remove the
  near-duplicate prose-revision surface. `revise --mode feedback` (default) addresses reviewer
  critique (the old `edit`); `revise --mode style` polishes voice while preserving meaning/citations
  (the old `polish`). **`edit` and `polish` are retained as fully working back-compat aliases** (and
  `polish` keeps its CLI subcommand) but no longer appear in the capability manifest — the advertised
  surface drops from 27 to 26 actions with zero breakage. Added docs clarifying when to use each
  quality check (`review` / `section_review` / `verify_work` / `check_refs` / `audit` / `coherence`).

### Added
- **`experiment` action (27th) — design extraction + evaluation recreation.** New
  `clio_author/experts/experiment.py` + `experiment_models.py`: reads the design / architecture /
  experiments of one or more reference papers (multi-paper recovered from `gather`'s `[label]`
  section prefixes; or raw Markdown/text) and extracts each `PaperDesign` (research questions,
  architecture, datasets, baselines, metrics, ablations, protocol, compute, limitations). With a new
  paper `idea` it recreates a grounded `EvaluationPlan` — datasets/baselines/metrics/ablations (each
  tagged with the reference paper it came from), protocol, and threats to validity — and renders a
  drop-in `evaluation_plan.md`. Accepts `--sources` (auto-ingest), persists `experiment_designs.*` +
  `evaluation_plan.*`. Never-raise; offline-safe.
- **`gather` action (26th) + multi-source context.** New `clio_author/ingest/gather.py`
  (`gather_context`) ingests a heterogeneous source set — files, folders, globs, **git repo URLs**,
  PDFs/arXiv ids — and merges them into one `MemoryBlocks` (`context.json`, a drop-in `--blocks-file`,
  plus `context.md`). Deterministic, never-raise (per-source failures land in `skipped`); heavy PDF /
  `git` work stays lazy so the module is hermetic. Directories/repos contribute their docs
  (`.md`/`.rst`/`.txt`/`.tex` + `README`); explicit file paths ingest as given.
- **`--sources` auto-chaining.** Grounding actions (`ask`, `plan`, `write`, `compose`, `research`,
  `kg`, `review`) accept `--sources`/`--sources-file`: the agent auto-gathers them into `blocks`
  before dispatch (explicit `blocks` still wins), so the writing path can be pointed straight at a
  repo/folder/PDFs with no separate ingest step. Manifest payload keys updated accordingly.
- **`discover` action (25th)** — find real candidate papers for a topic via scholarly search
  (Semantic Scholar → OpenAlex → Crossref → arXiv `search_query` + cascade merge/dedupe); writes
  `discovered.json`/`.bib`; `research` gains a `discover` flag to seed its brief from real results.
  Pure API, no LLM, no new deps.
- **PDF compilation** — `export --pdf` and `compose --pdf` compile `paper.tex` → `paper.pdf`
  (tectonic/latexmk/pdflatex; best-effort, `metadata.pdf_error` when no engine, never fails export).
- **README reorganized by workflow** — capabilities grouped (read · understand · discover/verify ·
  review · write/compose · illustrate · export · orchestrate), each with arguments + examples.
- **Full multi-stage knowledge-graph pipeline** (`kg --full`) — re-implements protoneo/knowledge's
  6 stages (metadata → ontology → extraction → coref → verification → summary) clean-room (AGPL-3.0;
  no code copied), with checkpoint/resume (`--stages`, `--resume`). Simple single-shot `kg` stays default.
- **wtf-p writing workflows** as 5 new actions (now 24 total) — `research` (grounded literature brief),
  `verify_work` (goal-backward claim coverage), `check_refs` (deterministic BibTeX + in-text \cite audit),
  `section_review` (3-layer single-section review), `audit` (deterministic pre-submission checks);
  `plan`/`SectionOutline` gain `research_needed`/`research_topics`. Re-implemented from concepts (MIT).
- **MCP-over-HTTP transport + `/author` slash command** — `CLIO_MCP_TRANSPORT=http` runs one long-lived
  bridge; a Claude Code `/author` command (and Codex prompt) drives the CLI.
- **MCP bridge (`mcp` extra) + host-integration proof.** `clio_author/integration/mcp_bridge.py` exposes the subagent over MCP (FastMCP, stdio) so MCP-only hosts can invoke it; the harness itself stays non-MCP. Verified end-to-end that **Claude (CLI), Codex (CLI), and CLIO (its tool gateway)** each invoke clio-author and get the identical result — see `docs/INTEGRATION.md`.
- **Multimodal review.** `review` now *looks at* figures when a vision client is enabled (`CLIO_VISION=gemini` + `--figures-json`/`--figures-file` or `blocks`): each figure is described and folded into the reviewed text, so the critique is vision-grounded. Backward compatible (no vision / no figures -> unchanged); records `vision_review` / `figures_seen`.
- **`rebuttal` action** (19th) + `RebuttalExpert` — draft an author response addressing a review point by point (concede/clarify/propose revisions), grounded in the paper, inventing no new claims or citations. CLI: `clio-author rebuttal --paper-file P --review-json '{...}'`.
- **`plan` action + `PlannerExpert`** (17th action) — turn an idea or a `PaperOutline` into per-section
  **writing plans**: ordered `tasks`, `claims`, `sources`, word budgets, and citation hints (the
  `SectionPlan` schema the `writer` already consumes). Writes `plan.json` to `out_dir`; `write` follows
  a plan via `section_plan`, and `compose --plan` runs the planner per section before drafting.
- **`--out FILE` on every CLI action** — save the result directly (prose `content` for `.md`/`.txt`,
  full JSON for `.json`) instead of redirecting stdout; works for the print-only actions too
  (ask/review/edit/polish/coherence/meta_review).

## [0.3.0]

### Added
- **Retrieval-grounded review.** `review --ground` (when a `CLIO_SCHOLAR` backend is configured) makes
  the reviewer first retrieve related prior work for the paper and inject it into the review prompt,
  so weaknesses/questions can be grounded in real references ("overlaps prior work [Title, Year]").
  Returns the retrieved set in `metadata["related_work"]`/`structured`; off by default and fully
  backward compatible (no scholar client → unchanged single-pass review). Adopts DeepReview's idea.
- **Parallel knowledge-graph extraction.** KG section batches now run concurrently
  (`max_workers`, default 4) with a deterministic order-preserving merge — large papers extract far
  faster while staying reproducible.
- **Section-batched knowledge-graph extraction.** `build_kg_from_llm` now splits a paper's sections
  into batches (`batch_size`, default 6), extracts each with one LLM call, and merges the sub-graphs
  (dedupe nodes by type+label, remap/collapse edges). Long papers that previously overflowed a single
  prompt now extract a full graph (e.g. a 125-section paper → ~347 nodes / 529 edges). Partial batch
  parse failures are tolerated.
- **Content knowledge graph.** New `kg` action and `clio-author kg` subcommand extract a semantic
  graph of a paper's *content* (claims/methods/datasets/results/metrics/concepts/tasks and the
  relations between them) from its memory blocks — distinct from any citation graph. Returns
  `{nodes, edges}` (edges with unknown endpoints dropped), a Mermaid `graph TD` rendering under
  `--format prose`, and writes `kg.json` + `kg.mmd` when `out_dir` is set. Re-implements protoneo's
  knowledge-graph concept from scratch (no AGPL code copied); hermetic on `EchoLLMClient`.
- **`RoundRobin` pattern.** Implemented the round-robin deliberation pattern in
  `clio_author/harness/patterns.py`: agents take turns across `payload["rounds"]`, each turn
  threaded into the shared session so later agents see prior turns.

### Removed
- **Literature graph feature.** Removed the `literature_graph` action, the `clio-author graph`
  subcommand, the `CLIO_GRAPH` backends, and the literature-graph clients/expert. The new `kg`
  action covers content-level graphs; citation-level paper graphs are out of scope.

### Added (earlier in this cycle)
- **`polish` and `coherence` experts** (wtf-p-style writing roles). `polish` improves prose for
  clarity, flow, and academic voice (optional `voice`) while preserving citations/claims;
  `coherence` checks a manuscript's sections for terminology drift, contradictions, undefined terms,
  duplication, and broken flow, returning structured issues. Both are reachable as actions (now 16)
  via the CLI (`polish`/`coherence` subcommands), `run`, and the adapter.
- **LaTeX export** (completes PaperOrchestra parity — a `.tex` manuscript). New `clio_author/export/`:
  pure-stdlib `escape_latex`, `markdown_to_latex` (headings/bold/italic/code/lists/links/citations),
  and `to_latex_document` (standalone `\documentclass` … `\end{document}` with `\section` per section
  and `\bibliography{references}` when a bib is present). New **`export`** action (13th) takes
  compose-style `sections`/`markdown` + optional `bibtex` and writes `paper.tex` (+ `references.bib`).
  `compose --latex` also emits `paper.tex` alongside the Markdown. No new dependencies.
- **`compose` action** (PaperOrchestra's whole-paper orchestration). Takes an `idea` (+ optional
  `experimental_log`, `outline`, `candidates`, `blocks`, `review`, `out_dir`) and drafts a
  multi-section manuscript by chaining the existing experts: outline (provided or LLM-generated) →
  optional citation verification → per-section writing (each in a fresh session, optionally through
  the writer↔reviewer refine loop) → deterministic Markdown assembly (with a `## References` block
  when a bib is produced). Persists `paper.md` + `sections/NN-slug.md` when `out_dir` is set. Never
  raises; a failed section degrades to a placeholder rather than aborting. Reachable as the 12th
  action via `clio-author compose` / `run compose` and the adapter. LaTeX export and the parallel
  plotting branch remain follow-ups.
- **Gemini vision path** (PaperBanana's true-image route), optional and off by default.
  `clio_author/llm/vision.py`: `VisionClient` protocol + `GeminiVisionClient` (stdlib `urllib` REST,
  lazy; reads `GEMINI_API_KEY`/`GOOGLE_API_KEY`) with `describe_image` (vision → text) and
  `generate_image` (text → image PNG), plus `resolve_vision_client`. `figure_agent` uses it when
  enabled: `describe_figures` *looks at* real figure images (metadata reports `vision_described` vs
  `text_described`); `plot` with `spec.kind="diagram"` generates a real image. Falls back to the
  text/code path otherwise; never raises. Wired via `CLIO_VISION` (`gemini`|`off`, default `off`),
  `CLIO_VISION_MODEL` (default `gemini-2.5-flash`), `CLIO_IMAGE_MODEL` (default `gemini-2.5-flash-image`).
- **No-key citation backends.** `CLIO_SCHOLAR=auto` now cascades Semantic Scholar, OpenAlex,
  Crossref, and arXiv. Users can force one backend with `semantic`/`s2`, `openalex`, `crossref`,
  or `arxiv`, or disable lookup with `off`/`none`.
- **Local CLI env files.** `clio-author` now loads `.env.local` (or `CLIO_ENV_FILE`) without
  overriding existing environment variables, so API keys do not need to be pasted into commands.
- **Security documentation and env template.** `.env.local.example` documents supported local
  credentials; `docs/SECURITY.md` covers key rotation, local env files, and S2 rate limits.

### Changed
- **Semantic Scholar throttling.** The S2 client now enforces a cross-process 1 request/second
  interval before HTTP calls and retries once after HTTP 429 to respect the API key rate limit
  across repeated CLI invocations.

## [0.2.3]

### Added
- **File inputs for the CLI** — `--blocks-file`, `--paper-file`, `--source-file`,
  `--candidates-file`. Real papers couldn't be passed inline (a 200 KB+ `--blocks-json` hit the
  shell's "Argument list too long" limit); the `*-file` variants read the file inside the CLI.
- **`--format structured|prose` on every text action** (`write` and `describe` were missing it).

### Fixed
- `clio-author write … --format prose` previously errored with "unrecognized arguments".
- `clio-author ask --blocks-file clio-out/<id>/blocks.json` (and `review`/`write` via `*-file`) now
  handle real-paper-sized inputs.

## [0.2.2]

### Added
- **Citation backend auto-wiring.** The CLI now selects the citation backend via the `CLIO_SCHOLAR`
  environment variable (`auto` (default) = real Semantic Scholar, reading `SEMANTIC_SCHOLAR_API_KEY`;
  `off`/`none` = disabled). `resolve_scholar_client()` makes `clio-author cite` work out of the box.
- **`CHANGELOG.md`.**

### Changed
- **Pinned `torch`/`torchvision` to the CPU index** in `pyproject.toml` (`[tool.uv.sources]` +
  `[[tool.uv.index]] pytorch-cpu`) and regenerated the lock, so `uv sync --all-extras` resolves
  matching CPU wheels and avoids the `torchvision::nms` mismatch. GPU users can override the index.

## [0.2.1]

### Added
- **`format` output option** (`structured` (default) | `prose`) on the actions, so a host can
  request prose output in addition to the structured result.
- **CLI / subagent invocation docs** — how to run via `uv run` and invoke clio-author as a subagent.

### Changed
- More concise README.

## [0.2.0]

### Added
- **Visible ingest output.** `clio-author ingest <id|url|title|topic|path>` writes a browsable
  `./clio-out/<slug>/` containing `paper.md`, `blocks.json`, and `img/figureN.png`. `IngestorExpert`
  now honors `out_dir` from the task payload and persists the Markdown + memory blocks.
- **Comprehensive `README.md`** + reconciled `docs/USAGE.md`: the 11-action catalog, every optional
  extra, model/env configuration, output locations, testing, CI, and troubleshooting.

### Changed
- Package version bumped to match the release line.

## [0.1.2]

### Added
- **GitHub Actions CI** — ruff (lint + format), mypy, and the hermetic pytest suite on every PR and
  push to `main`.
- **Ingest by paper title or topic** — `search_arxiv_pdf` / `resolve_source` resolve a title (exact
  match first) or topic to an arXiv PDF via the arXiv API, in addition to arXiv id / URL / local PDF.

## [0.1.1]

### Added
- **CLI real-provider selection** via `CLIO_LLM` (`echo` (default, offline) | `claude` | `codex` |
  `ollama`; model via `CLIO_LLM_MODEL`, Ollama URL via `CLIO_OLLAMA_URL`). Ready-made `LLMClient`
  providers in `clio_author.llm.providers`.

## [0.1.0]

### Added
- Initial release: a standalone, pure-Python multi-agent harness for processing, reviewing, and
  writing scientific papers (roadmap milestones M0–M8).
- **Harness** — `BaseAgent`/`AgentProtocol`/`Engine` + patterns (`Sequential`, `Parallel`,
  `CriticRefine`), `SessionContext`, Pydantic types; pluggable `LLMClient` (`EchoLLMClient` default).
- **Ingest** — Docling + PyMuPDF extraction with a deterministic academic post-process pass
  (sections, citations, equations, figures, bibliography, tables, cleanup) → memory blocks.
- **Retrieval** — `HashingEmbedder` + in-memory retriever (hermetic) and an optional
  SentenceTransformer + LanceDB backend; Semantic Scholar citation verification (suggestions only).
- **Experts** — ingestor, paper_qa, citation, reviewer, meta_reviewer, writer, editor, figure_agent.
- **Tools** — `SafeFiles` sandboxed read/write/edit; `eval/report.py` metrics.
- **Integration** — `ClioAuthorAgent` routing, `ClioAuthorSubagent` adapter, and the `clio-author` CLI.
- BSD-3-Clause. Adapted from paper-to-md (MIT), PaperBanana/PaperOrchestra (Apache-2.0); protoneo
  concepts re-implemented (not copied). ~300 hermetic tests.

[0.3.0]: https://github.com/SIslamMun/clio-author/releases/tag/v0.3.0
[0.2.3]: https://github.com/SIslamMun/clio-author/releases/tag/v0.2.3
[0.2.2]: https://github.com/SIslamMun/clio-author/releases/tag/v0.2.2
[0.2.1]: https://github.com/SIslamMun/clio-author/releases/tag/v0.2.1
[0.2.0]: https://github.com/SIslamMun/clio-author/releases/tag/v0.2.0
[0.1.2]: https://github.com/SIslamMun/clio-author/releases/tag/v0.1.2
[0.1.1]: https://github.com/SIslamMun/clio-author/releases/tag/v0.1.1
[0.1.0]: https://github.com/SIslamMun/clio-author/releases/tag/v0.1.0

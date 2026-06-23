# Source-project coverage — what AUTHOR took from each, what it didn't

How clio-author (**AUTHOR**) maps to the five projects it was asked to combine/reference. Compiled
from a read of each repo + AUTHOR's code. Legend: **✓ have · ◑ partial · ✗ not in AUTHOR**.
Licensing: paper-to-md (MIT), PaperBanana/papervizagent & PaperOrchestra (Apache-2.0) → adapted with
attribution; **protoneo (AGPL-3.0) → concepts re-implemented clean-room, no code copied**;
wtf-p (MIT) → concepts re-expressed (JS→Python). AUTHOR itself is BSD-3-Clause.

> One-line verdict: AUTHOR has the **analytical core** of all five — and *unifies* them behind one
> interface — but deliberately omits each project's **product shell** (standalone CLIs, FastAPI/MCP
> services, Streamlit UIs, bundled benchmarks, git/state machinery) and the heaviest infra
> (async/streaming, web-search discovery, PDF compilation, VLM-as-Judge eval suites).

---

## 1. paper-to-md (MIT) — PDF → Markdown processing

| Feature | AUTHOR |
|---|---|
| Docling extraction (text/tables/figures/equations/code), logo filter, figure renumber | ✓ `ingest/docling_extract.py` |
| Deterministic post-process (citations, sections, figures, bibliography, cleanup) | ✓ `ingest/postprocess/*` (adapted, MIT) |
| Equation repair + table normalization | ✓ **extended beyond paper-to-md** (`postprocess/equations.py`, `tables.py`) |
| Memory-block / enrichment JSON (figures/equations/code) | ✓ `ingest/blocks.py` (+ adds `SectionBlock`, `to_context()`, block ids) |
| VLM figure descriptions | ✓ via Gemini (`llm/vision.py`) — paper-to-md uses local qwen-vl |
| Claude-Agent-SDK agentic retouch | ✗ — AUTHOR uses targeted experts instead |
| FastAPI service + Ed25519 auth + job queue | ✗ (in-process only) |
| MCP server + `/convert-paper` slash command | ◑ — AUTHOR has its own MCP bridge + `/author`, not paper-to-md's |
| Standalone `pdf2md` CLI, batch script, local-LLM (LiteLLM) provider | ✗ / ✗ / ◑ (AUTHOR has echo/claude/codex/ollama, not LiteLLM) |

**Similar:** same deterministic post-process pipeline + enrichment schemas (adapted). **Different:** AUTHOR adds equation/table passes, section blocks, and selective context injection; drops the service/CLI/agentic-retouch product layer.

## 2. PaperBanana / papervizagent (Apache-2.0) — figures

| Feature | AUTHOR |
|---|---|
| Visualizer↔Critic refine loop (T rounds, "no changes" short-circuit, rollback) | ✓ `harness/patterns.py:CriticRefine` + `figure_refine` |
| Matplotlib code path (+ safe subprocess render) | ✓ `figure_agent.py` + `render_plot_code` |
| Image-gen diagram path (Gemini) | ✓ `llm/vision.py:generate_image` (`plot kind="diagram"`) |
| Vision figure description | ✓ `describe_figures` |
| **Retriever** (reference-example retrieval) + multimodal ICL | ✗ — no reference set/retrieval |
| **Stylist** + auto-synthesized style guides | ✗ |
| **VLM-as-Judge** eval (4 vetoed dims, tiered aggregation) | ✗ |
| PaperBananaBench (292 cases) + MinerU extraction + Streamlit demo | ✗ |

**Similar:** the producer↔critic loop and code/image dual path. **Different:** AUTHOR has the Visualizer+Critic core but **not** the Retriever/Stylist front-end, the style-guide synthesis, or the VLM-judge evaluation/benchmark.

## 3. wtf-p (MIT) — writing workflows

| Workflow/agent | AUTHOR |
|---|---|
| create-outline | ✓ (in `compose`/`plan`) |
| plan-section (tasks/claims/sources/budgets) | ✓ `planner.py` |
| research-gap / lit-review | ✓ `research.py` (grounded via scholar cascade) |
| execute-section / write | ✓ `writer.py` + `write_review` loop |
| review-section (3-layer: citation+coherence+rubric) | ✓ `section_review.py` |
| verify-work (goal-backward claim coverage) | ✓ `verify_work.py` |
| prose-polisher (voice profiles) | ✓ `polish.py` (◑ voice is free-text, not 4 named profiles) |
| coherence-checker | ✓ `coherence.py` |
| citation-expert / citation-formatter | ✓ `cite` + `check_refs.py`/`bib_utils.py` |
| audit-milestone (submit checks) | ✓ `audit.py` |
| 4 reviewer personas | ✓ `review_models.py:PersonaSpec` |
| discuss-section / list-assumptions / map-project / transition | ✗ (interactive/stateful — out of harness scope) |
| 36 `/wtfp:` slash commands, stateful `.planning/`, git checkpoints | ✗ |
| WCN token-compression, multi-runtime (Claude/Gemini/OpenCode) packaging | ✗ |
| poster/slides generation | ✗ |

**Similar:** AUTHOR re-implemented wtf-p's core quality loop (outline→plan→research→write→verify→review→polish→check-refs→audit) + personas. **Different:** wtf-p is a stateful, interactive **CLI command system** with git/checkpoints/WCN/multi-runtime; AUTHOR is a stateless programmatic library. AUTHOR also adds capabilities wtf-p lacks (paper QA, rebuttal, meta-review, figures, KG).

## 4. PaperOrchestra (Apache-2.0) — whole-paper writing

| Feature | AUTHOR |
|---|---|
| Compose pipeline (outline→cite→plan→write→review→assemble) | ✓ `compose.py` |
| Two-stage citation RAG (discover → S2 verify; fuzzy>70 + year bonus, date cutoff, dedup, .bib) | ✓ `retrieval/scholar.py` (**+ extends** S2→OpenAlex→Crossref→arXiv cascade; thefuzz→difflib fallback; cross-process rate-lock) |
| AgentReview rubric + persona + meta-review | ✓ `reviewer.py` + `meta_reviewer.py` |
| LaTeX manuscript assembly | ✓ `export/latex.py` (pure-stdlib) |
| Plotting via PaperBanana (parallel with lit-review) | ◑ figures exist, but no parallel Step2‖Step3, no VLM-critic plot loop |
| **Web-search discovery** (Gemini+Google grounding) | ✗ — AUTHOR verifies supplied candidates, no web crawl |
| Single multimodal section-writing call; tables from experimental log | ◑ per-section writing instead; no table-from-log builder |
| **≥90% citation coverage enforced** in the writer | ◑ coverage *reported*, not enforced |
| Content-refinement accept/revert loop + **anti-reward-hacking** directives | ◑ per-section refine loop; no doc-level accept/revert; no anti-gaming prompts |
| **PDF compilation** (pdflatex/bibtex) | ✗ (out of scope — `.tex` only) |
| Conference templates (CVPR/ICLR) | ✗ |
| Autoraters (Citation-F1, lit-review-quality, side-by-side) + PaperWritingBench (200) | ✗ |

**Similar:** the discover→verify citation pattern + AgentReview + section-isolated writing + compose flow. **Different:** AUTHOR broadens citations to a 4-source cascade and stays hermetic/offline-testable, but omits web discovery, PDF compile, the autorater suite, the benchmark, and the anti-reward-hacking directives.

## 5. protoneo/knowledge (AGPL-3.0 — clean-room) — KG + harness

| Feature | AUTHOR |
|---|---|
| 6-stage KG pipeline (metadata→ontology→extraction→coref→verification→summary) | ✓ `retrieval/kg_pipeline.py` (re-implemented from scratch) |
| Dynamic ontology (domain detect + self-consistency N-sampling + grounding) | ✓ `kg_pipeline.py` |
| Section-batched extraction + accumulated context | ✓ `kg.py:build_kg_from_llm` |
| Coref (acronym/substring/Jaccard merge + alias edges) | ✓ |
| Verification (grounding + prune low-confidence/orphans) | ◑ deterministic + sequential (protoneo runs the 3 passes async-parallel) |
| KnowledgeGraph model (nodes/edges/annotations/confidence) | ✓ `kg.py` |
| Checkpoint / resume | ◑ dict-based + out_dir snapshots (no durable SessionManager) |
| BaseAgent / AgentProtocol / Engine / SessionContext | ✓ `harness/*` (re-implemented) |
| Patterns: Sequential / Parallel / CriticRefine / RoundRobin | ✓ all four |
| **IndependentSynthesis** (3-phase, variance-triggered depth) | ✗ (we have its pieces: Parallel→RoundRobin→synthesize via `run_panel`, not the variance escalation) |
| ToolRegistry (web_search / semantic_scholar / graph_query tools) | ✗ |
| Visual-evidence VLM ingestion, parser registry/chunker | ✗ (figures/ingest handled elsewhere) |
| Self-consistency N-sampling + LLM grounding sub-passes | ◑ ontology N-sampling ✓; the extra LLM grounding/completeness sub-passes are flag-only |
| FastAPI + WebSocket event bus + Vue UI + AppManifest plugins | ✗ |
| Async/streaming, sampler controls, LiteLLM/OAuth | ✗ (AUTHOR is synchronous; providers = echo/claude/codex/ollama) |

**Similar:** AUTHOR re-implemented (clean-room) the whole 6-stage KG pipeline + the BaseAgent/patterns/session harness + ontology self-consistency. **Different:** AUTHOR is **synchronous** and library-only; omits protoneo's async/streaming, the FastAPI/WebSocket service, the tool registry, visual-evidence, the AppManifest plugin system, and the 3-phase IndependentSynthesis with variance-triggered depth.

---

## Overall — what's in AUTHOR vs not

**In AUTHOR (the union, behind one interface — 24 actions):** ingest (Docling + post-process + figures), memory blocks + Q&A + RAG, citation verification (4-source cascade), review + meta-review + rebuttal + 3-layer section review, plan/research/write/edit/polish/coherence/verify_work/check_refs/audit, compose (whole paper) + LaTeX export, figures (code + Gemini image + critic loop) + vision describe, a full 6-stage content **knowledge graph**, the harness (BaseAgent + 4 patterns + sessions), `orchestrate` (goal→plan→run), and three host transports (in-process / CLI / MCP bridge).

**Not in AUTHOR (deliberately):** each source's **product shell** — standalone CLIs, FastAPI/REST/WebSocket services, Streamlit UIs, git/state machinery, multi-runtime packaging, bundled benchmarks (PaperBananaBench, PaperWritingBench); and the heaviest infra — async/streaming, web-search discovery, PDF compilation, the VLM-as-Judge / autorater evaluation suites, protoneo's tool-registry + visual-evidence + IndependentSynthesis, and PaperBanana's Retriever/Stylist + style-guide synthesis.

**Why:** AUTHOR's job was to *unify the capabilities* into one grounded, host-invocable package — not to reproduce five separate products. The omitted items are either (a) host/product concerns a caller supplies, (b) evaluation harnesses (see `docs/BENCHMARK-PLAN.md`), or (c) noted follow-ups. See `docs/MOTIVATION.md` for the gap argument and the cross-system capability matrix.

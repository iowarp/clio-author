# Phagocyte — deep study notes (for clio-author)

Repo: `/home/shazzadul/Illinois_Tech/Summer26/RA/clio-author/artifact/repos/phagocyte`
Branch: `main`. HEAD: `f8c76a9 feat: BigSet-style verify-before-commit tool-call generation (#83)`.
Read-only study; nothing modified.

> Bottom line on the "paper-to-md and phagocyte learnings" relationship:
> Phagocyte's PDF→Markdown core is **literally a fork of the `paper-to-md` project** —
> every module under `src/ingestor/src/ingestor/extractors/pdf/postprocess/` carries the
> docstring *"Ported from paper-to-md project."* The "phagocyte learnings" for making
> PDF→Markdown "scientific-paper perfect" are the **deterministic academic post-processing
> pass** (citations, sections, equations, figures, bibliography, cleanup) layered on top of
> Docling ML extraction, plus the **two-layer corpus audit** and **VLM figure description**.

---

## 1. What Phagocyte is

**Purpose.** An end-to-end pipeline that turns *one research topic into a fine-tuned LLM*.
Tagline (README): *"Research → Parse → Ingest → Process → Generate → Fine-tune."* Six phases,
each a uv-workspace module under `src/`, all fronted by a single `phagocyte` CLI.

1. **Research** (`src/researcher`) — Gemini deep-research → `research_report.md`
2. **Parse** (`src/parser`) — extract references, download papers, DOI→BibTeX
3. **Ingest** (`src/ingestor`) — **PDF / web / GitHub / YouTube / audio → clean Markdown** ← the PDF→MD core
4. **Process** (`src/processor`) — chunk + embed Markdown into a LanceDB vector store
5. **Generate** (`src/generator`) — synthesize QA / CoT / tool-use training data, curate it
6. **Fine-tune** (`src/finetuner`) — multi-backend LoRA (Unsloth / HuggingFace / Ollama)

**Upstream.** `github.com/grc-iit/Phagocyte`. The example corpus and tool
registries are all built around **NDP (National Data Platform)**, **IOWarp**, **Jarvis**, and
HPC I/O papers (LABIOS, Luxio, DataSpaces) — the GRC research domain.

**Tech stack / language.** Python ≥3.11, managed by **uv** (workspace of editable members).
CLI via **click**. Async (`asyncio`, `httpx`). Build backend `hatchling`. Root entry point
`phagocyte = "cli:main"` (`pyproject.toml`).

**Key dependencies (by phase).**
- Ingestor PDF: **Docling** (ML structure/layout/formula extraction) + **PyMuPDF/fitz** (OCR fallback) + **Pillow**.
- Ingestor other: **Magika** (Google neural file-type detection), **Crawl4AI**+Playwright (web), **yt-dlp**+youtube-transcript-api, **openai-whisper** (audio), docx2python/mammoth, python-pptx, ebooklib, pandas/openpyxl, defusedxml.
- Processor: **LanceDB** (vector store), **LlamaIndex** (`MarkdownNodeParser`, `CodeSplitter`/tree-sitter), **Ollama** (default embeddings), sentence-transformers, **open-clip-torch** (CLIP visual embeddings).
- Generator/Finetuner: providers (below), **unsloth/torch/peft/trl/transformers/datasets/accelerate/bitsandbytes** (opt-in `[train]` extra).

---

## 2. Repo structure (top level)

```
AGENTS.md      # autonomous-operation runbook + R1–R7 operating rules (each maps to a real incident)
CLAUDE.md      # @AGENTS.md include + quick ref
GEMINI.md      # Gemini CLI guidance
README.md      # full pipeline + command reference
config.yaml    # parser config (sources, rate limits, institutional/Sci-Hub access)
pyproject.toml # uv workspace; members = the 8 src/ modules
uv.lock        # 1.28 MB lockfile (explains a big chunk of "why so many files")
docs/          # RUN_RECIPES.md, docs/generator/ (design + paper-implementation notes), docs/notebooks/ (Gemma3 / FunctionGemma walkthroughs)
example/       # ndp_docs/ — a full worked corpus: cloned NDP repos + a converted NDP slide-deck PDF; configs/
experiments/   # ndp_knowledge_scaling/ — results/, data/, scripts/ (an eval harness)
img/           # logo + architecture diagram
scripts/       # 93 helper scripts (setup_finetune_venv.sh, gen_verified_traces.py, compare_ndp.py, SLURM helpers)
src/           # the 8 workspace modules (below)
tests/         # root tests
```

`src/` modules: `researcher/ parser/ ingestor/ processor/ generator/ finetuner/`
(phases 1–6) + `providers/` (shared LLM abstraction `phagocyte_providers`) +
`phagocyte_web/` (FastAPI + vanilla-JS wizard, **CLIO design system**) + `cli.py` (the `phagocyte` CLI).
Each module is itself a package (`src/<m>/src/<m>/`) with its own `pyproject.toml`, `mcp/` server, `tests/`, `README.md`.

**Why ~1827 files (not vendored deps).** Real first-party code is moderate; the file count comes from:
- `example/ndp_docs/` — **cloned upstream NDP repos checked into the tree** (`github_com_national-data-platform_ep-api/source/...`, `sci-ndp/*`) plus a converted slide deck whose extracted figures live in `.../img/` (177 files in one paper's `img/` alone).
- `experiments/ndp_knowledge_scaling/results/` (93 files) — generated eval artifacts.
- Per-module `tests/fixtures/` — reduced sample codebases/papers (wisio, labios) used as regression inputs.
- `uv.lock` (single huge file). So: **example data + cloned demo repos + test fixtures + generated experiment results**, not third-party vendoring.

---

## 3. Core functionality / architecture

**Problem solved.** Bootstrapping a domain-specialized LLM from scratch given only a topic:
gather the literature, normalize it to clean Markdown, build a searchable corpus, mint synthetic
SFT data (knowledge + agentic tool-use), and LoRA-train. The whole thing is designed to run
**autonomously by an AI coding agent** (Claude Code / Codex / Gemini CLI) — `AGENTS.md` is the
runbook and `R1–R7` are hard operating rules tied to specific past failures.

**Orchestration.** `src/cli.py` defines a click group with sub-groups `research / parse / ingest /
process / generate / train`, plus two top-level commands: `pipeline` (runs all six phases as
subprocesses, writing `pipeline_output/<slug>/phaseN_*/`, per-phase banners, `--from-phase/--to-phase`
slicing, `--keep-going`) and `doctor` (preflight: uv / Ollama / API keys / GPU). Each phase is wrapped
via `uv run --project src/<module>`. MCP servers exist for every module (`researcher-mcp`, `parser-mcp`,
`ingestor-mcp` (10 tools), `processor-mcp`, `rag-mcp`, `generator-mcp`, `finetuner-mcp`).

---

## 4. THE "LEARNINGS" — what makes PDF→scientific-Markdown "paper-perfect"

This is the core PDF→scientific-Markdown capability. It lives in **`src/ingestor`**.

### 4a. Two-stage PDF extraction
`src/ingestor/src/ingestor/extractors/pdf/pdf_extractor.py` — class `PdfExtractor(BaseExtractor)`,
`media_type = MediaType.PDF`.
- **Primary: Docling** (`_run_docling_extraction`). `PdfPipelineOptions` with
  `images_scale=2.0`, `generate_picture_images=True`, and crucially
  `do_formula_enrichment = self.config.extract_equations` → LaTeX equations. Exports
  `result.document.export_to_markdown()`. Figures pulled from `result.document.pictures`,
  filtered by size (`min_image_width=200`, `min_image_height=150`, `min_image_area=40000`) to
  drop logos/badges, saved as `figure{n}.png`.
- **Fallback: PyMuPDF/`fitz`** (`_run_pymupdf_extraction`) for scanned/OCR PDFs — page-by-page
  `page.get_text("text")` + image extraction, then only basic `cleanup_text`.
- `PdfConfig` flags: `use_postprocess`, `use_ocr_fallback`, `extract_tables`, `extract_equations`.
- Also handles **PDF URLs** (downloads to temp first).

### 4b. The deterministic academic post-processing pass (the actual "paper-to-md learnings")
`src/ingestor/src/ingestor/extractors/pdf/postprocess/__init__.py` → `process_markdown(content, images)`.
Module docstring: **"Ported from paper-to-md project for academic paper processing."** Every
sub-module repeats *"Ported from paper-to-md project."* Fixed pipeline order (order matters):

```python
content = process_sections(content)      # 1
content = process_citations(content)     # 2
content = process_equations(content)     # 3
content = process_figures(content, images or [])  # 4
content = process_bibliography(content)  # 5
content = cleanup_text(content)          # 6
```

**1. `sections.py` — `process_sections`.** Rebuilds the heading hierarchy from numbering depth.
- `_fix_abstract_header`: `"Abstract -Modern HPC…"` → `## Abstract\n\n…`. Same for `Index Terms`.
- `_fix_hierarchical_sections`: `"1. INTRODUCTION"`→`## 1. INTRODUCTION`, `"3.1 …"`→`### …`,
  `"3.1.1 …"`→`#### …`. `_determine_header_level(numbering)` = `min(depth+1, 6)`. Handles
  **Roman numerals** (`I./II./III.`) for top-level sections.
- `_is_section_title()` guards against false positives (len ≤120, not ending in `,;:`, followed by
  blank line or capitalized). `_fix_numbered_bullet_subsections`: `"- 1) Title:"` → `### 1) Title`.

**2. `citations.py` — `process_citations`.** Turns inline numeric cites into anchor links and
splits the doc at the References header so the bibliography isn't re-linked.
- `_expand_citation_ranges`: `[11]-[14]` → `[11], [12], [13], [14]`.
- `_link_single_citations`: `[7]` → `[[7]](#ref-7)` (negative lookbehind/lookahead to skip
  already-linked / image syntax).
- `_add_reference_anchors`: `[1] Author…` → `<a id="ref-1"></a>[1] Author…` — so the links resolve.

**3. `equations.py` — `process_equations`.** The most elaborate module: repairs Docling/OCR LaTeX.
Sub-steps: `_fix_formula_placeholders` (`<!-- formula-not-decoded -->` → `*[Formula - see original PDF]*`),
`_fix_docling_spacing` (de-spaces `"M u l t i H e a d"`→`MultiHead`, `"d _ { k }"`→`d_{k}`,
`"1 0 0 0 0"`→`10000`, acronyms `"I O P S"`→`IOPS`, operators), `_clean_latex_spacing`
(`"\ frac"`→`"\frac"`, `"s i n"`→`\sin`), `_fix_common_ocr_artifacts` (incl. **GAN-specific**
`p_{data}` repairs, minimax fixes, equation-number `\quad (2)`), `_fix_bare_newlines_in_display_math`
(wraps stray `\\` in `\begin{aligned}…\end{aligned}` — has a hardcoded list of ~120 LaTeX command
names to distinguish a real line-break from `\alpha` etc.), `_normalize_equation_delimiters` (blank
lines around `$$…$$`). Output is normalized `$$…$$` display math.

**4. `figures.py` — `process_figures`.** Embeds extracted images *above their captions*.
`_build_figure_map` maps filenames (`figure1.png`, `fig_1`, `document_img_001.png`) → figure number;
`_embed_figures_at_captions` finds `Fig. 1` / `Figure 1:` caption lines and inserts
`![Figure N](./img/<file>)` immediately above. `get_unembedded_figures` lists leftovers.

**5. `bibliography.py` — `process_bibliography`.** `_format_reference_entries` ensures a blank line
between each `[N]` reference entry (recognizing `<a id>` anchors and `- [N]` bullets);
`extract_reference_count` counts entries.

**6. `cleanup.py` — `cleanup_text`.** `_fix_ligatures` (ﬁ→fi, ﬂ→fl, ﬀ→ff, ﬃ/ﬄ/ﬅ/ﬆ, en-dash→hyphen),
`_fix_glyph_artifacts` (`glyph[epsilon1]`→`ε`, full Greek map), `_fix_excessive_blank_lines`
(≤2), `_fix_trailing_whitespace`. Plus opt-in helpers `fix_hyphenated_words` (`docu-\nment`→`document`,
flagged aggressive) and `normalize_unicode` (smart quotes/dashes/spaces).

### 4c. Figure understanding (VLM)
`src/ingestor/src/ingestor/ai/ollama/vlm.py` — `OllamaVLM` (alias `VLMDescriber`), default model
`llava` (also moondream). `--describe-images` makes it write natural-language descriptions per figure
(subject / visual elements / visible text / context). `images/processor.py` `ImageProcessor`
standardizes filenames to `{source}_img_{NNN}.{ext}`, converts to PNG, and lazy-loads the VLM. These
descriptions become the *searchable text* for figure retrieval downstream (processor's `image_chunks`).

### 4d. Two-layer corpus audit ("verify the corpus is on-topic before you train on it")
This is a *corpus-quality* learning distinct from the per-file conversion above.
- **Layer 1 heuristics** (`src/ingestor/src/ingestor/audit/heuristics.py`): shingle-hash cross-file
  duplicates, license-density, SPA-shell markers, filename tiers, link-spam — no LLM.
- **Layer 2 LLM deep-audit** (`audit/llm_judge.py`): sends **head(800)+mid(500)+tail(500)** excerpts
  (not just the head like `--llm-filter`) and asks for strict JSON
  `{verdict: keep|simplify|remove, reason, topic_density, boilerplate_pct}`. Catches **title-bait**
  (head on-topic, body isn't — the real "DataSpaces PDF that's actually oil-reservoir slides" case),
  **junk-in-body** (`testtt`/`abc123` past the head), **empty-after-license**. Default model
  `google/gemma-3-27b` (LM Studio) or `gpt-oss:20b` — *needs a 20B+ model* (smaller → unparseable JSON).
  Quarantines to `<dir>/_quarantine/` by default; writes `audit_report.md`. Runner: `audit/runner.py`.
- `filters/universal_filter.py` is the 3-tier heuristic pre-filter (TOC/nav/stub removal; "100%
  precision, 90.7% retention on HDF5 docs").

### 4e. What the output actually looks like
Real worked example: `example/ndp_docs/Unknown_XXXX_The_National_Data_Platform_NDP_…pdf/` — a converted
NDP slide deck. Confirms the section-injection behavior (`## Section 1`, `## Section 2` synthesized for
a header-poor deck) and a populated `img/` (177 extracted figures). NOTE: this is also a known
**weakness** — for slide decks with no real numbered headings the section detection produces generic
`## Section N` markers (also injected later by the processor's `md_clean._inject_pdf_sections`).

---

## 5. Agent / tool / MCP architecture

- **MCP servers per module** (`src/<m>/mcp/<m>_mcp/server.py`): `ingestor-mcp` (10 tools incl.
  ingest file/batch/crawl/clone/describe-images), `processor-mcp`, `rag-mcp` (semantic/hybrid search),
  `generator-mcp`, etc. Used by Claude Desktop / Cursor / VS Code Copilot / Windsurf / Zed.
- **AGENTS.md is the agent contract.** R1–R7 rules tell an autonomous agent how to run the pipeline,
  verify each phase by artifact (not exit code), and recover from documented failure modes.
- **`generate tool` / agentic tool-use generation** (`src/generator/.../tool/`): builds MCP-style
  multi-step tool-call training examples. `dependency_graph.py` (In-N-Out style) seeds *valid*
  tool chains by matching one tool's output type to the next tool's input type **before** the LLM
  fills args; `tool_executor.py` (`ToolExecutor`) can simulate/really-execute calls.

---

## 6. The BigSet verify-before-commit learning (HEAD commit)

`src/generator/src/generator/tool/verified_commit.py` — class `VerifiedCommitFilter`; CLI
`generate verify <examples> <TOOLS.json>` (shim `src/cli.py` ~L1273; impl `generator/cli.py` `tool-verify`).

- **"BigSet" = verify each example against the tool's *real schema* BEFORE committing it** (vs the
  pipeline's usual generate-then-filter `curate`). It is *the one place the pipeline verifies before
  committing*. Run it **between `generate tool` and `generate curate`** — curate the *verified* file.
- The load-bearing check (`verify_call`): reject `unknown_arg_name` (the **`search_term` vs
  `search_terms`** class), `missing_required_arg`, `placeholder_arg_value`
  (`""/none/null/n/a/todo/<value>` — the `<escape>`-corrupted-null class), `unknown_tool`. These are
  "the exact failure modes measured in the 270M eval" (a 270M model trained on un-verified tool data).
- Survivors stamped with `metadata.provenance` (`verified`, `verification` level, `tools`, `how_found`)
  and `solution.execution_validated=True`. Default **schema** level is offline; `--live` additionally
  executes each call through the built-in `ToolExecutor` and requires success.

(The processor and generator details are summarized here from sub-agent studies; see `verified_commit.py`,
`dependency_graph.py`, `tool_generator.py` for specifics.)

---

## 7. Models used

| Role | Model(s) | Where |
|---|---|---|
| Deep research | Gemini (Deep Research) | researcher (`GOOGLE_API_KEY`/`GEMINI_API_KEY`) |
| Ref-parse / generation / curation | provider-agnostic | `phagocyte_providers` (below) |
| **Audit Layer 2** | **gemma-3-27b** (LM Studio default), gpt-oss:20b/120b | `ingestor/audit/llm_judge.py` (needs 20B+) |
| **Figure VLM** | **llava** (default), moondream | `ingestor/ai/ollama/vlm.py` |
| Text embeddings | **Qwen3-Embedding** 0.6B/4B/8B (low/medium/high) | processor `embedders/profiles.py` (Ollama default) |
| Code embeddings | **jina-code-embeddings** 0.5B/1.5B (low/high) | processor |
| Visual embeddings | **OpenCLIP** ViT-L-14 / ViT-H-14 | processor `openclip.py` |
| Reranker | **BAAI/bge-reranker-v2-m3** cross-encoder | processor `optimizations/reranker.py` |
| Fine-tune targets | **Gemma 3** (270m-it / 4b-it / 27b), **FunctionGemma**, Qwen3-4B-Instruct, Qwen2.5, Llama-3.1-8B | finetuner / docs/notebooks |

**Provider abstraction** (`src/providers/src/phagocyte_providers/providers/`): `get_client()` dispatches to
`openai_compat` (OpenAI / LM Studio / llama.cpp / vLLM / Ollama-as-OpenAI), `ollama`, `anthropic_api`,
`claude_sdk` (wraps the **Claude Code CLI** `claude -p`, no API key), `codex_sdk` (`codex exec`),
`openai_agents` (OpenAI Agents SDK), `gemini`, `antigravity`. Default generation provider is `ollama`;
diversification prefers `claude`.

---

## 8. CLI / entry points / how it runs

- Console script: `phagocyte = "cli:main"` (`pyproject.toml`); `phagocyte-web` for the browser wizard.
- `uv sync` then `uv run phagocyte doctor` → `uv run phagocyte pipeline "<topic>" -o ./pipeline_output`.
- Phase-by-phase: `research → parse refs/batch → ingest batch (--auto-filter/--llm-filter/--audit) →
  process run → generate qa/cot/tool/verify/curate → train run`.
- Per-module: `uv run <module>-mcp`, `uv run pytest` inside `src/<module>/`, lint `uv run ruff check`.
- aarch64/GH200 finetune caveat: use `scripts/setup_finetune_venv.sh` (pins cu128 torch), not `uv sync`.

---

## 9. Relationship to paper-to-md / protoneo / wtf-p / CLIO

- **paper-to-md** — *direct ancestor of the PDF→MD core.* All six PDF post-process modules are
  explicitly *"Ported from paper-to-md project."* This is the concrete link behind the phrase
  "paper-to-md and the phagocyte learnings": Phagocyte took paper-to-md's deterministic academic
  cleanup and embedded it as the post-Docling pass in the ingestor. (No `paper-to-md` repo is vendored
  here; only the ported code + attribution.)
- **CLIO** — appears as the **CLIO design system** used by `phagocyte_web` (CSS tokens
  `src/phagocyte_web/src/phagocyte_web/static/css/tokens.css`; README references the "CLIO design
  system"). Also `scripts/test_xlam_cliokit_mcps.py` references a "cliokit". So the relationship is
  shared GRC tooling/branding (and clio-author is the sibling project this study feeds).
- **protoneo / wtf-p** — **no first-party references inside the Phagocyte source.** (`wtfp` shows up only
  as available Skills/slash-commands in *this* harness, not in the repo.) They are sibling GRC projects,
  not dependencies of Phagocyte.

---

## What "phagocyte learnings" means for clio-author

The "phagocyte learnings" for PDF→scientific-Markdown are concretely:

1. **ML extraction + a deterministic academic post-processing pass.** Don't ship Docling's raw
   Markdown. Run a fixed pipeline: sections → citations → equations → figures → bibliography → cleanup.
   This is the paper-to-md heritage and the single biggest quality lever.
2. **Heading reconstruction from section numbering** (`1.` / `1.1` / `1.1.1` / Roman) with
   guardrails (`_is_section_title`) so paragraphs aren't promoted to headings. Section structure is
   what every downstream chunker (and the QA generator's `section_path` anchoring) relies on.
3. **Citation graph in the Markdown itself**: `[7]`→`[[7]](#ref-7)` + range expansion + reference
   anchors — turns a flat paper into a navigable, link-resolved document.
4. **Aggressive equation repair** of OCR/Docling artifacts (de-spacing, `\\` handling,
   ligature/glyph→Unicode, formula-placeholder markers). Equations are where naive converters fail worst.
5. **Figure-at-caption embedding** + size-filtering of logos + **VLM descriptions** so figures are
   both placed correctly and made searchable.
6. **Verify the corpus, not just convert it**: two-layer audit (heuristics + head/mid/tail LLM judge)
   to drop title-bait / junk-body / boilerplate before it pollutes training — the corpus analogue of
   the generator's "verify-before-commit."
7. **Fallback discipline**: Docling primary, PyMuPDF/OCR fallback; never silently emit garbage —
   stamp metadata (`extractor`, `visual_embedding_fallback`) so consumers detect degraded modes.

## Reusable for clio-author (lift directly)

- **The entire `postprocess/` package** (`sections.py`, `citations.py`, `equations.py`, `figures.py`,
  `bibliography.py`, `cleanup.py`) — pure-Python, regex-only, no heavy deps, self-contained
  `process_markdown(content, images)`. Drop-in for any PDF→MD converter that produces raw Markdown.
- The **`PdfConfig` + Docling pipeline-options** pattern (formula enrichment on, image size filtering,
  OCR fallback) as a tuning reference.
- The **VLM figure-description** approach (`OllamaVLM`) for caption-less figures.
- The **two-layer audit** design (`audit/heuristics.py` + `audit/llm_judge.py` head/mid/tail JSON
  verdict) as a corpus-quality gate.
- The **provider abstraction** (`phagocyte_providers.get_client`) if clio-author needs multi-LLM support
  with a local/no-API-key path (`claude_sdk`, `ollama`).
- The **BigSet verify-before-commit** philosophy generalized: validate structured output against a schema
  and *drop* (don't just down-rank) invalid items before they enter the corpus.

## Open questions

- Where is the upstream **paper-to-md** repo, and how much diverged is Phagocyte's port? (Only the
  attribution comment exists here; no original repo to diff against.) Worth locating if clio-author
  wants the latest upstream fixes.
- **Tables**: the README claims "Table Extraction (tables→markdown)" via Docling, but there is **no
  dedicated table post-process module** — tables ride along as inline GFM inside the Markdown and are
  *not* repaired or made first-class (the processor likewise treats them as section prose). For
  "scientific-paper perfect," table fidelity may be the biggest remaining gap.
- **Equation repair is hardcoded/heuristic** (transformer-paper and GAN-paper-specific regexes like
  `MultiHead`, `p_{data}`). It will be brittle on papers outside that distribution; clio-author should
  treat it as a starting heuristic, not a general solution.
- How exactly does **CLIO / cliokit** relate to clio-author? Phagocyte only consumes the CLIO *design
  system* in its web UI and references a `cliokit` in a test script — the deeper relationship lives in
  the CLIO repos, not here.
- The synthetic `## Section N` injection (here in slide decks; also in processor `md_clean`) is a
  fallback for header-poor inputs — verify clio-author wants that vs. preserving the raw structure.

---

## 10-line summary

1. Phagocyte is a 6-phase Python/uv pipeline: research→parse→ingest→process→generate→fine-tune, turning a topic into a fine-tuned LLM.
2. The PDF→Markdown core is `src/ingestor` — Docling ML extraction (+PyMuPDF OCR fallback) followed by a deterministic academic post-processing pass.
3. That post-process pass (`extractors/pdf/postprocess/`) is explicitly **"Ported from paper-to-md project"** — the literal link behind "paper-to-md and the phagocyte learnings."
4. The "learnings" = sections (heading reconstruction from numbering), citations (`[7]`→`[[7]](#ref-7)` + ranges + anchors), equations (heavy OCR/LaTeX repair), figures (embed-at-caption + size filter), bibliography spacing, cleanup (ligatures/glyphs/Unicode).
5. Figures get VLM descriptions (Ollama llava/moondream) so they're searchable; images filtered by size to drop logos.
6. A two-layer corpus **audit** (heuristics + head/mid/tail LLM judge, gemma-3-27b/gpt-oss:20b) drops title-bait/junk/boilerplate before training.
7. The HEAD feature is **BigSet verify-before-commit** (`generator/tool/verified_commit.py`): validate every tool call against its real schema and *drop* invalid ones (search_term vs search_terms, missing/placeholder args) before curating.
8. Processor (Phase 4) chunks Markdown via LlamaIndex header parser + tree-sitter for code, embeds with Qwen3/jina-code/OpenCLIP into LanceDB (hybrid search + bge reranker).
9. Models: Gemini (research), gemma-3/Qwen/FunctionGemma (generation/finetune), llava (VLM), Qwen3-Embedding + OpenCLIP (embeddings); provider-agnostic via `phagocyte_providers` (incl. no-API-key Claude CLI path).
10. Most reusable for clio-author: the self-contained `postprocess/process_markdown()` package (regex-only, no heavy deps), the VLM figure-describer, and the two-layer audit; biggest open gap is **table fidelity** (no dedicated table post-processing) and the brittleness of hardcoded equation regexes.

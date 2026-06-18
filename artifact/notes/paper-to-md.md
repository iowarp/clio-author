# paper-to-md — Deep Study Notes

Repo: `/home/shazzadul/Illinois_Tech/Summer26/RA/clio-author/artifact/repos/paper-to-md`
Studied: 2026-06-15. Read-only. This is the PDF→Markdown conversion core for clio-author.

---

## 1. Purpose, Tech Stack, Dependencies, License

**Purpose.** Convert academic PDF papers into clean, RAG-ready Markdown with linked citations, embedded figures, structured author metadata, and machine-readable enrichment JSON (figures/equations/code). Distributed as a CLI tool `pdf2md`, plus an optional Dockerized FastAPI microservice and a Claude Code MCP integration.

**Package name / version / license.** `paper-to-md` v`0.2.1`, MIT (`LICENSE`, © 2025 Jaime Cernuda). Author email in `pyproject.toml`: `jcernudagarcia@hawk.iilinoistech.edu` (Illinois Tech). Homepage: `github.com/JaimeCernuda/paper-to-md`.

**Language / build.** Python `>=3.10,<3.13`. Build backend `hatchling`. Console entry point `pdf2md = "pdf2md.cli:app"` (`pyproject.toml` line 60). Wheel packages: `pdf2md` and `service`.

**Core dependencies** (`pyproject.toml` lines 27-35):
- `docling>=2.0.0` — ML-based PDF extraction (text, tables, figures, equations, code, picture classification, VLM picture descriptions).
- `pymupdf>=1.26.6` — declared, but **not actually imported anywhere** in `pdf2md/` (grep finds no `fitz`/`pymupdf` usage). Likely a leftover or transitive expectation. (Open question.)
- `Pillow>=10.0.0` — image size filtering during extraction.
- `claude-agent-sdk>=0.1.14` — cloud LLM "retouch" backend (`claude_agent_sdk.query`, `ClaudeAgentOptions`, `AssistantMessage`, `TextBlock`).
- `litellm>=1.50.0` — local LLM/VLM calls (LM Studio / Ollama) via `litellm.acompletion`.
- `typer>=0.15.0` + `rich>=13.0.0` — CLI and console output.

**Optional extras:**
- `service` (lines 39-50): `fastapi`, `uvicorn[standard]`, `python-multipart`, `arq` (Redis job queue), `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pynacl` (Ed25519), `pydantic-settings`, `structlog`.
- `dev` (lines 51-57): `pytest`, `pytest-asyncio`, `httpx`, `aiosqlite`, `ruff`.

**Lint:** ruff, line-length 100, target py310, rules `E,F,I,W`.

---

## 2. Repository / Package Structure

```
paper-to-md/
├── pyproject.toml, README.md, CLAUDE.md, LICENSE, .env.example
├── Dockerfile, docker-compose.yml, alembic.ini
├── .claude/commands/convert-paper.md      # slash command
├── mcp/server.py                          # MCP server (FastMCP)
├── pdf2md/                                 # ← CORE PACKAGE
│   ├── cli.py                             # typer CLI: convert/retouch/postprocess/enrich/download-models
│   ├── extraction/
│   │   ├── docling.py                     # extract_with_docling()  (Stage 1)
│   │   └── enrichments.py                 # extract_enrichments()    (Stage 4, RAG JSON)
│   ├── postprocess/                        # Stage 2 — deterministic, no AI
│   │   ├── __init__.py                    # process_markdown() orchestrator
│   │   ├── sections.py, citations.py, figures.py, bibliography.py, cleanup.py
│   └── agent/                              # Stage 3 — LLM retouch
│       ├── cleanup.py                     # CLEANUP_PROMPT + Claude SDK runner
│       ├── providers.py                   # LiteLLM provider/model config (env-driven)
│       └── backends/
│           ├── base.py                    # AgentBackend ABC
│           ├── claude.py                  # ClaudeBackend (cloud)
│           ├── local.py                   # LocalBackend (LiteLLM; authors, lettered sections, VLM)
│           └── __init__.py                # get_backend() registry
├── service/                                # FastAPI microservice (extra: [service])
│   ├── app.py, config.py, auth.py, database.py, models.py, schemas.py
│   ├── worker.py, bundle.py
│   └── routes/{submit,status,retrieve}.py
├── migrations/                             # alembic; versions/001_initial.py
├── scripts/
│   ├── batch_convert.py                   # subprocess loop over CLI
│   ├── generate_keypair.py                # Ed25519 keypair + INSERT SQL
│   └── iowarp_publications/main.py        # YAML→PDF downloader (publications)
└── tests/                                  # pytest (postprocess + service)
```

Pipeline mapping (from `CLAUDE.md`):
`PDF → Docling Extraction (extraction/) → Rule-Based Postprocess (postprocess/) → LLM Retouch (agent/) → RAG Enrichments (extraction/enrichments.py)`

---

## 3. Conversion Pipeline & Depth Tiers

Depth enum: `pdf2md/cli.py` `class Depth(str, Enum)` = `low | medium | high`. **Default = medium.**

Feature gating (`cli.py` lines 140-142):
```python
use_retouch         = depth in (Depth.medium, Depth.high) and not raw
use_enrichments     = depth == Depth.high and not raw
use_vlm_descriptions= depth == Depth.high and not raw
```

| Depth | Stage 1 Docling | Stage 2 Postprocess | Stage 3 LLM Retouch | Stage 4 Enrichments+VLM |
|-------|-----------------|---------------------|---------------------|--------------------------|
| `low` | ✅ | ✅ | ❌ | ❌ |
| `medium` (default) | ✅ | ✅ | ✅ | ❌ |
| `high` | ✅ | ✅ | ✅ | ✅ |

`--raw` short-circuits everything after Stage 1 (raw Docling markdown only).

### `convert` traced end-to-end (`cli.py` `convert()`, lines 33-253)
1. Resolve `output_dir` (defaults to PDF's parent dir); doc dir = `output_dir/<pdf_stem>/`. Provider resolved via `resolve_provider(local, provider)` (defaults `lm_studio` when `--local`).
2. **[1/4] Extract** — `extract_with_docling(pdf_path, output_dir, images_scale, min_image_width, min_image_height, min_image_area)` (`extraction/docling.py`). Returns `(md_path, images: list[Path])`. Writes `<stem>/<stem>.md` and `<stem>/img/figureN.png`.
3. **Raw save** — if `--keep-raw` or `--raw`, copies md to `<stem>_raw.md`.
4. **[2/4] Postprocess** — only if not `--raw`. `content = md_path.read_text(); processed = process_markdown(content, [img.name for img in images]); md_path.write_text(processed)`.
5. **[3/4] Retouch** — if `use_retouch`: `backend = "local" if local else "claude"`, then `run_cleanup_with_backend_sync(md_path, backend=, provider=, model=, verbose=False)` (`agent/cleanup.py`). `BackendNotInstalledError` is caught and skipped gracefully.
6. **[4/4] Enrich** — if `use_enrichments`: `extract_enrichments(pdf_path, output_dir, images_scale=, enable_picture_description=use_vlm_descriptions, use_local_vlm=local, vlm_model=model, vlm_provider=provider)`. Writes the RAG JSON files. Any exception is caught and reported as a yellow "Failed" (non-fatal).
7. Prints summary (md path, line count, image dir, enrichments path).

**Stage 1 detail — Docling extraction** (`extraction/docling.py` `extract_with_docling`):
- `PdfPipelineOptions(images_scale=2.0, generate_picture_images=True)`, `DocumentConverter`.
- Accepts `ConversionStatus.SUCCESS` or `PARTIAL_SUCCESS`; else raises `RuntimeError`.
- **Logo/badge filter (important):** iterates `result.document.pictures`, gets PIL image, and **skips** any with `width < min_image_width (200)` OR `height < min_image_height (150)` OR `area < min_image_area (40000)`. Surviving images saved as `figure1.png, figure2.png, ...` with a running `figure_num` (so numbering is contiguous *after* filtering — and therefore may not match the PDF's printed figure numbers). Failures to extract a single image are silently skipped.
- Markdown via `result.document.export_to_markdown()`.

**Stage 2 detail — `process_markdown`** (`postprocess/__init__.py`). Strict order (order matters):
```python
content = process_sections(content)        # sections.py
content = process_citations(content)       # citations.py
content = process_figures(content, images) # figures.py
content = process_bibliography(content)    # bibliography.py
content = cleanup_text(content)            # cleanup.py
```
All five are deterministic regex transforms (no AI). See §5 for each.

**Stage 3 detail — retouch dispatch.** `agent/cleanup.py::run_cleanup_with_backend_sync` is event-loop-safe: uses `asyncio.run` normally, or a `ThreadPoolExecutor` if already inside a running loop (notebook/server). Delegates to `get_backend(name).run_cleanup(...)`.

---

## 4. Vision / VLM Integration

VLM is used **only at depth=high** for figure descriptions. Two distinct code paths, chosen by `use_local_vlm`:

**Provider abstraction** (`pdf2md/agent/providers.py`):
- Env-driven defaults: `PDF2MD_TEXT_MODEL` (default **`qwen3-4b`**), `PDF2MD_VLM_MODEL` (default **`qwen3-vl-4b`**), `PDF2MD_PROVIDER` (default `lm_studio`).
- Hosts: `LM_STUDIO_HOST` (`http://localhost:1234/v1`), `PDF2MD_VLM_HOST` (separate endpoint so VLM can live on another node, default `http://localhost:1234/v1`), `OLLAMA_HOST` (`http://localhost:11434`).
- `ProviderConfig(model, api_base)` returns LiteLLM-format model strings:
  - LM Studio → `lm_studio/<model>`
  - Ollama → `ollama_chat/<model>`
- `get_provider_config()` (text), `get_vlm_config()` (vision; uses `PDF2MD_VLM_HOST`). `get_vlm_config` for ollama → `ollama_chat/<vlm>` with `api_base=OLLAMA_HOST`; for lm_studio → `lm_studio/<vlm>` with `api_base=PDF2MD_VLM_HOST`.

**Path A — cloud / Docling-native VLM** (`use_local_vlm=False`, i.e. default `convert -d high` without `--local`). In `extraction/enrichments.py::extract_enrichments`: sets `pipeline_options.do_picture_description = True` and `picture_description_options = _get_vlm_options(...)`. `_get_vlm_options` builds a Docling `PictureDescriptionApiOptions(url, params={model, max_tokens=1024}, prompt=..., timeout=120, picture_area_threshold=0.02)`. Note `enable_remote_services = not use_local_vlm`. Despite the name "cloud (Claude)", this path actually points Docling's *API* picture-description at whatever `PDF2MD_VLM_HOST`/Ollama URL is configured — there is **no Claude vision path**; ClaudeBackend.`run_describe_figures` raises `NotImplementedError`. The VLM prompt (Docling path):
  > "Describe this scientific figure in detail. Identify the type (chart, diagram, flowchart, etc.), key elements, labels, and any data or relationships shown."

**Path B — local VLM via LiteLLM** (`use_local_vlm=True`, `convert -d high --local`). Docling's own picture-description is skipped; after extraction `_add_local_vlm_descriptions(enrichments, img_dir, provider, model)` calls `LocalBackend.run_describe_figures` (`agent/backends/local.py`). That method:
- Sorts `img_dir/figure*.png` by numeric stem, base64-encodes each, calls `_vlm_call(image_b64, FIGURE_DESCRIPTION_PROMPT, config, max_tokens=500)`.
- `_vlm_call` posts an OpenAI-style multimodal message (`image_url` with `data:image/png;base64,...` + text) through `litellm.acompletion`, temperature 0.1, timeout 180s; strips `<think>...</think>`.
- Returns `[{figure_id, description}]`, merged into `enrichments.figures` by `figure_id`.
- `FIGURE_DESCRIPTION_PROMPT`: type, key elements/labels/axes, trends/relationships, annotations; "Be factual and concise (2-4 sentences). Do not speculate."

**Default models confirmed:** text `qwen3-4b`, vision **`qwen3-vl-4b`** (yes, qwen3-vl).

**Text-retouch backends:**
- `ClaudeBackend` (`backends/claude.py`): wraps `run_cleanup_agent` (Claude Agent SDK), agentic file-editing with `allowed_tools=["Read","Edit","Glob","Grep"]`, `permission_mode="acceptEdits"`. Ignores `provider`/`model`.
- `LocalBackend` (`backends/local.py`): targeted LiteLLM calls only for judgment tasks (author formatting, lettered-section classification). Mechanical cleanup is left to postprocess. `_llm_call` budgets `max_tokens*3` for thinking models and recovers answers from `reasoning_content`.

---

## 5. Figure / Table / Equation / Citation Handling

### Citations (`postprocess/citations.py`)
- Splits doc at first `## References` / `# References` / `References` heading; processes body and references separately.
- `_expand_citation_ranges`: `[11]-[14]` (hyphen/en/em dash) → `[11], [12], [13], [14]`; caps at 50-wide ranges (otherwise left untouched); swaps reversed ranges.
- `_link_single_citations`: regex `(?<!\])\[(\d{1,3})\](?!\()` → `[[N]](#ref-N)`. Guards against already-linked (`[`, `](`, `![` prefixes) → **idempotent**. Only 1-3 digit numbers (4-digit years not linked).
- `_add_reference_anchors`: strips `- ` bullet prefixes from ref entries, prepends `<a id="ref-N"></a>` to `[N]` at line start (indent-aware, dedup-aware).

### Sections (`postprocess/sections.py`)
- `_fix_abstract_header`: `Abstract -text` → `## Abstract\n\ntext` (count=1).
- `_fix_index_terms_header`: same for `Index Terms`.
- `_fix_hierarchical_sections`: `3.1.1 Title` → header level by dot-depth (`_determine_header_level` = `min(depth+1, 6)`: `3`→`##`, `3.1`→`###`, `3.1.1`→`####`, cap `######`). Two patterns: title-on-own-line, and `N.N Title. Body` (splits header + body paragraph). Uses `_is_section_title` heuristic (≤120 chars, not multi-sentence).
- `_fix_numbered_bullet_subsections`: `- 1) Title:` followed by paragraph → `### 1) Title`; plain `- 1) item` → `1. item`.
- **Lettered sections (A., B.) are deliberately NOT handled here** — delegated to the LLM agent (need context: "A. Background" header vs "A. We conducted..." sentence).

### Figures (`postprocess/figures.py`)
- `_build_figure_map`: maps figure number → filename via `(?:figure|fig)[_-]?(\d+)`.
- `_embed_figures_at_captions`: only at **line-start** caption matches `^\s*(?:\*\*)?Fig(?:ure)?\.?\s*(\d+)[.:\s]` (avoids "as shown in Fig. 1"). Inserts `![Figure N](./img/figureN.png)` + blank line above the caption. Tracks `embedded_figures` (pre-seeded from existing `![Figure N]`) → **each figure embedded exactly once, idempotent**.
- `find_unembedded_figures`: diagnostic for unused images.
- Note header in file: logo filtering moved to `docling.py`; `TestNoDeadCode` asserts old helpers (`filter_logo_images`, `renumber_figures`, min-image constants) are gone from this module.

### Tables
No dedicated table post-processing module. Tables come straight from Docling's `export_to_markdown()` (pipe tables). Cleanup steps explicitly **avoid** touching table rows (lines starting with `|` are skipped in `_merge_split_paragraphs` and OCR-artifact removal). The README mentions "Fix table formatting issues" only inside the *agent* CLEANUP_PROMPT (Claude may touch them); LocalBackend does not.

### Equations
Extracted only at depth=high in `enrichments.py::_extract_from_document`. Reads `doc.equations` or `doc.formulas`; pulls `latex` (or `original`) and `text`, page, and ±2 surrounding texts as `context`. Requires Docling `do_formula_enrichment=True`. Not embedded into markdown — only emitted to `equations.json`.

### Code blocks
Same module: iterates `doc.texts` where `item.code_language` is set (Docling `do_code_enrichment=True`); records `text`, `language`, `page`, `context`. Emitted to `code_blocks.json`.

### Cleanup (`postprocess/cleanup.py`) — applied last, in order:
1. `_remove_image_comments` — drop `<!-- image -->` lines.
2. `_fix_ligatures` — ﬁ→fi, ﬂ→fl, ﬀ, ﬃ, ﬄ, ﬅ, ﬆ, plus en-dash `–`→`-`.
3. `_fix_glyph_artifacts` — strip `GLYPH<N>` and `GLYPH&lt;N&gt;`.
4. `_remove_ocr_artifacts_near_figures` — removes clusters of ≥2 short (<60 char) non-structural, non-sentence-ending lines immediately preceding `![Figure N]` embeds (OCR'd axis labels/legends).
5. `_fix_hyphenated_words` — joins `band-\nwidth`→`bandwidth`; preserves compounds (`client-\nto-server`→`client-to-server`); skips headings & code fences.
6. `_merge_split_paragraphs` — merges line-ending-without-terminal-punctuation + blank + lowercase/parenthetical continuation; skips headings/lists/figures/tables.
7. `_fix_excessive_blank_lines` — `\n{3,}`→`\n\n`.
8. `_fix_trailing_whitespace`.

### LLM retouch tasks (`agent/cleanup.py` CLEANUP_PROMPT, Claude) — 6 priorities:
1. Lettered section headers (A./B./C., Roman numerals, mixed 1.A) with context judgment.
2. **Relocate misplaced figures** with their captions to the first referencing section; delete `<!-- image -->`.
3. Remove OCR artifacts above captions.
4. **Format Authors** into `## Authors\n- **Name**, Institution, email`.
5. Merge split paragraphs.
6. General cleanup (headers, tables, lists).

LocalBackend only does #4 (`_format_authors` + `_is_author_noise` removal + `_validate_author_block`) and #1 (`_find_lettered_section_candidates` → `_classify_lettered_sections`, converts HEADER candidates to `##### A. Title`). Typically 1-2 small LLM calls regardless of doc size.

---

## 6. RAG-Ready JSON Outputs — Schemas (IMPORTANT for memory blocks)

Produced by `pdf2md/extraction/enrichments.py` at **depth=high** only. Dataclasses serialized via `dataclasses.asdict` + `json.dump(indent=2)`. Files written by `_save_enrichments` into `<output>/<stem>/`. Per-type files are written **only if that list is non-empty**; `enrichments.json` is always written.

**`CodeBlock`** (→ `code_blocks.json`, list):
```json
{ "text": "<code>", "language": "python|null", "page": 3, "context": "<±2 surrounding texts, ≤200 chars + '...'>" }
```

**`Equation`** (→ `equations.json`, list):
```json
{ "latex": "<latex or docling 'original'>", "text": "<original text repr>", "page": 5, "context": "<surrounding text>" }
```

**`FigureInfo`** (→ `figures.json`, list):
```json
{
  "figure_id": 1,
  "caption": "<resolved caption text>",
  "classification": "chart (0.87)" ,        // "<class_name> (<conf:.2f>)" or bare class or null
  "description": "<VLM description or null>",
  "page": 2,
  "image_path": "./img/figure1.png"
}
```
- `figure_id = idx+1` over `doc.pictures` (enrichments enumerate ALL pictures, **not** the size-filtered set from Stage 1 — so `figure_id`/`image_path` here may not line up 1:1 with the actually-saved `figureN.png` files. **Open question / mismatch risk.**)
- `classification` from Docling `do_picture_classification` annotations (top predicted class + confidence).
- `description` from VLM (Docling annotation `kind=="description"`, or merged from LocalBackend by `figure_id`).
- `caption` resolved via `caption_text(doc)` or by dereferencing `#/texts/N` cref pointers (`_resolve_ref`).

**`enrichments.json`** (combined, always written):
```json
{
  "metadata": {
    "source": "/abs/path/paper.pdf",
    "title": "<doc.title or pdf stem>",
    "num_pages": 12,
    "num_code_blocks": 3,
    "num_equations": 8,
    "num_figures": 6
  },
  "code_blocks": [ {CodeBlock}, ... ],
  "equations":   [ {Equation},  ... ],
  "figures":     [ {FigureInfo},... ]
}
```

For memory-block design: `figures.json` (caption + classification + VLM description + page + image_path) is the richest unit; `equations.json` and `code_blocks.json` each carry their own `context` field (±2 neighboring text items) which is well-suited as retrieval chunks. There is **no** `enrichments.json` "sections" array — section structure lives only in the markdown headers, not in JSON.

---

## 7. MCP Server & `/convert-paper` Slash Command

**MCP server** (`mcp/server.py`) — PEP-723 inline-script (`mcp[cli], httpx, pynacl, python-dotenv`), `FastMCP("pdf2md-service")`. Loads `.env` from repo root. It is a **thin client to the FastAPI service** (does not run conversion locally). Signs each request with Ed25519 via `_sign(method, path)` → headers `Authorization: Signature <b64>`, `X-Timestamp`, `X-Client-Id`. Three tools:
- `pdf2md_submit(pdf_path, depth="medium") -> str` — POST `/submit_paper` (multipart file + depth form), returns `job_id` + status.
- `pdf2md_status(job_id) -> str` — GET `/status/{job_id}`, returns status/progress/file/error string.
- `pdf2md_retrieve(job_id, output_dir) -> str` — GET `/retrieve/{job_id}`, extracts the returned `tar.gz` into `output_dir`, lists extracted files.

Register: `claude mcp add --scope user pdf2md-service -- uv run /path/to/paper-to-md/mcp/server.py`. Requires `.env`: `PDF2MD_SERVICE_URL`, `PDF2MD_CLIENT_ID`, `PDF2MD_PRIVATE_KEY` (base64 Ed25519 private key).

**Slash command** (`.claude/commands/convert-paper.md`): `allowed-tools` are the three MCP tools. Workflow: submit (depth medium default) → poll `pdf2md_status` every 5s until completed/failed (print each change) → retrieve to a dir next to the PDF → report extracted files; on failure show error and stop. Invoked as `/convert-paper path/to/paper.pdf` ($ARGUMENTS).

---

## 8. Service Mode (FastAPI + arq/Redis + Postgres) — brief

(From `service/`, studied via sub-agent.)
- **App** (`service/app.py`): factory `create_app()`, `FastAPI(title="pdf2md Service")`. Routers `submit/status/retrieve` mounted at top level (no prefix), tag `jobs`. Lifespan creates data/upload dirs, validates DB engine, opens arq Redis pool on `app.state.arq_pool`. `GET /health`. structlog. No middleware (auth is a per-route dependency).
- **Auth** (`service/auth.py`): Ed25519 (PyNaCl). Signing payload **`f"{method}\n{path}\n{timestamp}"`** — **body is NOT signed** (multipart). Headers `Authorization: Signature <b64>`, `X-Timestamp`, `X-Client-ID`. Default timestamp tolerance 300s (compose overrides api to 600s). Client looked up by UUID in `clients` table, must be `active`. `verify_signature` uses `VerifyKey(pubkey).verify`. Dependency `authenticate_client` returns the `Client` ORM row.
- **Worker** (`service/worker.py`): arq task `convert_paper(ctx, job_id)`, `WorkerSettings(functions=[convert_paper], max_jobs=worker_max_jobs(=1), job_timeout=1800)`. Same 4-stage pipeline as CLI, writes `progress` strings ("Step k/4: ..."). **Hardcodes `backend="claude"` for retouch** (local/provider not exposed via service). Status transitions queued→processing→completed/failed; uses `asyncio.shield` to record failures on cancel/timeout.
- **DB** (`service/models.py`, `migrations/versions/001_initial.py`): `clients(id uuid pk, name, public_key_b64 unique, active, created_at)`; `jobs(id uuid pk, client_id fk, status enum job_status[queued/processing/completed/failed], filename, depth, file_size_bytes, created_at, started_at, completed_at, progress, output_path, error_message, result_metadata JSON/JSONB)`. Indexes on `client_id`, `status`.
- **Routes/schemas**: `POST /submit_paper` (202) — validates `.pdf`, writes to `upload_dir/<job_id>/<file>`, inserts Job, `enqueue_job("convert_paper", job_id)`; returns `SubmitResponse{job_id,status,created_at}`. `GET /status/{id}` → `StatusResponse` (tenant-scoped by client_id). `GET /retrieve/{id}` → `tar.gz` (409 if failed/incomplete, 410 if output missing). **Bundle** (`service/bundle.py`) `create_tar_gz_bundle`: `tar.add(output_dir, arcname=output_dir.name)` — adds the **entire `<stem>/` output tree** (markdown + `img/` + any enrichment JSON) under a top-level `<stem>/` folder, built in memory.
- **Config** (`service/config.py`): `Settings(BaseSettings)`, env prefix **`PDF2MD_SERVICE_`**: database_url (postgres+asyncpg), redis_url, data_dir(`/data`), upload_dir(`/data/uploads`), auth_timestamp_tolerance_seconds(300), worker_max_jobs(1), Docling image params. `get_settings()` is NOT actually cached.
- **Docker**: `docker-compose.yml` services `api` (port 8000:8000), `worker` (`python -m arq service.worker.WorkerSettings`, mounts `~/.claude:/root/.claude:ro` for Claude SDK creds), `redis:7-alpine`, `postgres:16-alpine` (user/pw/db `pdf2md`). `Dockerfile` multi-stage python:3.11-slim, pre-runs `pdf2md download-models`.

---

## 9. CLI Commands (`pdf2md/cli.py`)

- **`convert <pdf> [output_dir]`** — main 4-stage pipeline (§3). Options: `-d/--depth` (low/medium/high, default medium), `-l/--local`, `-p/--provider` (lm_studio/ollama), `-m/--model`, `--raw`, `--keep-raw`, `--images-scale` (2.0), `--min-image-width` (200), `--min-image-height` (150), `--min-image-area` (40000).
- **`retouch <md_path>`** — Stage 3 only on an existing `.md`. Options `-i/--images` (default `./img`), `-l/--local`, `-p/--provider`, `-m/--model`, `-v/--verbose`. Fixes authors + lettered sections.
- **`postprocess <md_path>`** — Stage 2 only (deterministic). Options `-i/--images`, `-o/--output` (default overwrite). Globs png/jpg/jpeg from images dir. "Equivalent to depth=low processing."
- **`enrich <pdf> <output_dir>`** — Stage 4 only (RAG JSON). Options `--describe` (VLM), `-l/--local`, `-p/--provider`, `-m/--model`, `--images-scale`. Calls `extract_enrichments(enable_picture_description=describe, use_local_vlm=local, ...)`.
- **`download-models`** — instantiates a `DocumentConverter` to trigger Docling ML model downloads (~500MB → `~/.cache/docling/`). One-time.

---

## 10. "phagocyte" search

`grep -ri phagocyte .` over the entire repo → **no hits.** Nothing biology/immunology-related anywhere in paper-to-md.

---

## Tests (coverage signal)
`pytest`, mostly unit tests on the deterministic postprocess layer:
- `test_figures.py` — figure map building, line-start-only embedding, idempotence, `TestNoDeadCode` (asserts logo-filter helpers removed from figures.py).
- `test_citations_bibliography.py` — range expansion, idempotence, anchor injection, linkage invariant, non-numeric/4-digit not linked.
- `test_sections.py` — header levels, hierarchical sections, lettered sections NOT processed by regex.
- `test_cleanup.py` — paragraph merge, hyphenation, OCR-artifact removal, glyphs, image comments; plus `TestProviderConfig` (unknown provider raises, lm_studio/ollama configs).
- `tests/test_service/` — auth, submit, status, retrieve, worker (httpx + aiosqlite). `tests/paper/submit_and_retrieve.py` is an integration harness.
No tests exercise Docling itself or the live LLM/VLM calls.

---

## Reusable for clio-author

- **Deterministic postprocess layer** (`pdf2md/postprocess/`) is fully self-contained, regex-only, idempotent, and well-tested — directly reusable as a normalization pass independent of any LLM. `process_markdown(content, image_filenames)` is the single clean entry point.
- **Enrichment dataclasses + JSON schemas** (`CodeBlock`, `Equation`, `FigureInfo`, `Enrichments`) are a ready blueprint for clio-author memory blocks. `figures.json`/`equations.json`/`code_blocks.json` are the natural retrieval units; each enrichment carries `page` + `context`. Consider adopting these schemas (and adding a sections array, which is currently missing).
- **Provider abstraction** (`agent/providers.py`) cleanly separates cloud vs LM Studio vs Ollama with env-driven model/host config and LiteLLM prefixing — reusable for any local-LLM-or-cloud toggle. Separate `PDF2MD_VLM_HOST` design (VLM on a different node) is a nice pattern.
- **AgentBackend ABC + registry** (`agent/backends/`) is a clean strategy-pattern boundary: swap Claude-SDK agentic editing vs targeted LiteLLM calls behind one interface. The "judgment-only LLM, mechanics by regex" split (LocalBackend) is a good cost-control pattern.
- **Logo/figure size filtering** at extraction time (`docling.py`, PIL dimension thresholds) is a simple, effective figure-quality gate.
- **Ed25519 request signing** (`service/auth.py`, `scripts/generate_keypair.py`, `mcp/server.py`) — lightweight stateless auth pattern reusable for a clio-author service/MCP surface.
- **MCP submit/status/retrieve + slash command** is a complete template for exposing a long-running conversion job to Claude Code.

## Open questions / risks to resolve before building on this

1. **Figure-number alignment.** Stage 1 (`docling.py`) saves only size-passing images and renumbers them contiguously (`figure1..N`), but Stage 4 (`enrichments.py`) enumerates ALL `doc.pictures` as `figure_id = idx+1` and writes `image_path=./img/figure{idx+1}.png`. If any pictures were filtered out, `figures.json` `figure_id`/`image_path` will be **misaligned** with the actual saved files and with the markdown embeds. Needs verification on a real paper with logos.
2. **`pymupdf` is declared but unused** — confirm whether it's dead weight or expected by Docling at runtime.
3. **No "sections" enrichment JSON.** Section structure exists only as markdown headers. clio-author memory design may need a separate sections/outline extractor.
4. **No table enrichment.** Tables are only in markdown (Docling pipe tables); not represented in any JSON, and only the Claude agent path may reformat them.
5. **"cloud (Claude)" VLM is a misnomer.** There is no Claude vision path; `-d high` without `--local` routes Docling's picture-description API at `PDF2MD_VLM_HOST`/Ollama. Claude SDK is text-retouch only.
6. **Service retouch is Claude-only** (worker hardcodes `backend="claude"`) and depends on host `~/.claude` OAuth creds mounted into the container — operationally significant.
7. **`get_settings()` not cached** despite docstring; minor but worth noting if relied upon.
8. Docling version pin is loose (`>=2.0.0`); the enrichment code uses many `hasattr`/`getattr` guards, implying the Docling API surface it targets is somewhat fluid.

---

## 10-Line Summary
1. `paper-to-md` (pkg `paper-to-md` v0.2.1, MIT) is a Python 3.10-3.12 CLI `pdf2md` that converts academic PDFs to RAG-ready Markdown.
2. Pipeline = Docling extraction → deterministic regex postprocess → LLM "retouch" → high-depth RAG enrichments, gated by depth tiers low/medium(default)/high.
3. Stage 1 `extraction/docling.py` extracts markdown + filters logos by PIL size (200×150, 40k area); Stage 2 `postprocess/` does citations/sections/figures/bibliography/cleanup (regex, idempotent, well-tested).
4. Stage 3 retouch has two backends behind an ABC: `ClaudeBackend` (agentic Claude Agent SDK, Read/Edit/Glob/Grep) and `LocalBackend` (LiteLLM, judgment-only: authors + lettered sections).
5. Stage 4 `extraction/enrichments.py` emits `figures.json`, `equations.json`, `code_blocks.json`, and combined `enrichments.json` (depth=high only).
6. JSON schemas: FigureInfo{figure_id,caption,classification,description,page,image_path}, Equation{latex,text,page,context}, CodeBlock{text,language,page,context}, plus metadata{source,title,num_pages,counts}.
7. VLM is qwen3-vl-4b by default; provider abstraction (`agent/providers.py`) supports LM Studio (`lm_studio/`) and Ollama (`ollama_chat/`) via LiteLLM, with a separate `PDF2MD_VLM_HOST`; there is no real Claude vision path.
8. MCP server (`mcp/server.py`, FastMCP) exposes `pdf2md_submit/status/retrieve` over an Ed25519-signed HTTP service; `/convert-paper` slash command orchestrates submit→poll→retrieve.
9. Service mode = FastAPI + arq/Redis + Postgres + Ed25519 auth (signs METHOD\nPATH\nTIMESTAMP, body unsigned), Dockerized; worker hardcodes the Claude retouch backend.
10. `grep -ri phagocyte` → no hits; key risk to verify is figure-id/file-name misalignment between Stage 1 (filtered renumber) and Stage 4 (all-pictures enumeration).

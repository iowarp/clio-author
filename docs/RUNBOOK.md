# AUTHOR (clio-author) — CLI Runbook

A complete, copy-paste reference: **every subcommand, every flag, every setting.** Run the blocks
one at a time and inspect each result. Arranged as a paper's life — **read → understand → discover
& verify sources → judge → write → refine → illustrate → ship.**

- Every command prints a JSON result on **stdout** (logs → stderr; add `2>/dev/null` for clean JSON).
  Exit code `0` = ok, `1` = error.
- **Every** subcommand accepts `--out FILE` (also save the result — prose for `.md`/`.txt`, full
  JSON for `.json`). Text actions and most file-reading subcommands also accept `--json '{...}'`
  (merge extra payload keys) — see the per-subcommand tables below for which flags each one takes.
- Text actions need a model (`CLIO_LLM=…`); without one they return an offline **echo** placeholder.

> **Single-file rule (and the multi-source exception).** Every `--*-file` flag reads exactly **one**
> file (internally `_read_file` in `cli.py`; no `append` or glob). The exception is `--sources`,
> which takes **many** sources at once: the grounding actions (`ask`, `plan`, `write`, `compose`,
> `research`, `kg`, `review`) and the standalone `gather` action accept `--sources S [S ...]` (a mix
> of files, folders, globs, git repo URLs, PDFs/arXiv ids) or `--sources-file FILE` (one per line, or
> a JSON array). They are auto-ingested and merged into the grounding `blocks` for you — so you no
> longer need to concatenate files or pre-`ingest` each one by hand.

---

## 0. Setup (one-time)

```bash
cd ~/Illinois_Tech/Summer26/RA/clio-author
uv sync --all-extras                 # core + pdf/rag/scholar/viz extras (also repairs the venv)
mkdir -p runbook-out
```

## 1. Settings — every environment variable

| Variable | Accepted values (default **bold**) | Used by |
|---|---|---|
| `CLIO_LLM` | **`echo`** · `claude` · `codex` · `ollama` · `lmstudio` · `openrouter` · `litellm` | all text actions |
| `CLIO_LLM_MODEL` | any model name (provider-specific) | the chosen `CLIO_LLM` |
| `CLIO_OLLAMA_URL` | **`http://localhost:11434`** | `CLIO_LLM=ollama` |
| `CLIO_LMSTUDIO_URL` | **`http://localhost:1234/v1`** | `CLIO_LLM=lmstudio` |
| `CLIO_OPENROUTER_URL` | **`https://openrouter.ai/api/v1`** | `CLIO_LLM=openrouter` |
| `OPENROUTER_API_KEY` | your key (**required** for openrouter) | `CLIO_LLM=openrouter` |
| `CLIO_OPENROUTER_REFERER` | optional attribution URL | `CLIO_LLM=openrouter` |
| `CLIO_LITELLM_URL` | **`http://localhost:4000/v1`** | `CLIO_LLM=litellm` |
| `LITELLM_API_KEY` / `LMSTUDIO_API_KEY` | optional bearer key | `litellm` / `lmstudio` |
| `CLIO_SCHOLAR` | **`auto`** (=`cascade`/`all`) · `semantic`(`s2`) · `openalex`(`oa`) · `crossref`(`cr`) · `arxiv` · `off`(`none`/`offline`/`disabled`) | `cite`, `discover`, `review --ground`, `research` |
| `CLIO_RAG` | **`off`** (`hash`, deterministic default) · `semantic`(`st`) · `lancedb` | `ask` retrieval quality (`semantic`/`lancedb` need `--extra rag`) |
| `CLIO_VISION` | **`off`** (`none`/`offline`/`disabled`) · `gemini`(`google`) | `describe`, `review` (with figures), `plot kind="diagram"` |
| `CLIO_VISION_MODEL` | **`gemini-2.5-flash`** | vision describe |
| `CLIO_IMAGE_MODEL` | **`gemini-2.5-flash-image`** | vision image-gen |
| `CLIO_ENV_FILE` | path (**`.env.local`**) | auto-loaded key file |
| `SEMANTIC_SCHOLAR_API_KEY` | your key | `cite` (avoids rate limits) |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | your key | `CLIO_VISION=gemini` |

Put keys in `.env.local` (auto-loaded, never on the command line):
```bash
SEMANTIC_SCHOLAR_API_KEY=...
GEMINI_API_KEY=...
```

## 2. Global flags (on **every** subcommand)

| Flag | Meaning |
|---|---|
| `--out FILE` | also write the result — prose `content` for `.md`/`.txt`, full JSON for `.json` |
| `--append` | with `--out`, **append** after existing content instead of overwriting — builds a running log: each entry gets a `## <question>` header + a `_trace:` line (action · metadata · timestamp). (`.json` + `--append` → JSON Lines.) |
| `--json '{...}'` | merge a JSON object into the action payload (available on all subcommands except `capabilities`) |
| `-h` / `--help` | show that subcommand's exact flags |

## 3. Health check

```bash
uv run ruff check clio_author tests        # -> All checks passed!
uv run mypy clio_author                    # -> Success: no issues found in 75 source files
uv run pytest -q                           # -> 621 passed, 3 skipped, 12 deselected
uv run clio-author capabilities            # -> name=clio-author, 27 actions
uv run clio-author lifecycle               # -> the phase -> actions map (see docs/LIFECYCLE.md)
```

> **Pick by phase, not by name.** AUTHOR is a toolkit you enter at any phase of the author lifecycle
> (Frame · Gather · Plan · Draft · Strengthen · Referee · Respond · Ship). Most actions do **not**
> need `ingest` first. `clio-author lifecycle` prints which actions serve each phase;
> [`docs/LIFECYCLE.md`](LIFECYCLE.md) tells the full story with copy-paste recipes.

> **Dedicated subcommands** with their own flags: `capabilities, ingest, gather, ask, experiment,
> review, cite, discover, plan, write, compose, revise, export, polish, coherence, kg, describe,
> orchestrate, rebuttal, research, verify-work, check-refs, section-review, audit, run`. The other
> actions (`edit`, `meta_review`, `plot`, `write_review`, `figure_refine`) have **no dedicated
> subcommand** — reach them with `clio-author run <action> --json '{...}'`. `edit` and `polish` are
> **aliases** of the unified `revise` action (`edit` ≡ `revise --mode feedback`, `polish` ≡
> `revise --mode style`); both still work and `polish` keeps its own subcommand.

---

# The workflow — a paper's life

## Act I · Read → clean Markdown + memory blocks  *(run first; later acts reuse this)*

**`ingest`** — convert an arXiv id / URL / PDF / paper title into Markdown + memory blocks.

| Flag | Takes | Meaning |
|---|---|---|
| `source` (positional) | string | arXiv id, arXiv-or-HTTP URL, local PDF path, or paper title/topic. **One source only.** |
| `--json` | JSON object | merge any payload key (e.g. `{"out_dir":"..."}`) |
| `--out` | file path | save result |

```bash
# arXiv id, persist to a folder (paper.md + blocks.json + img/ + the pdf):
uv run --extra pdf clio-author ingest 2601.23265 --json '{"out_dir":"runbook-out/ingest"}'
# other source forms:
uv run --extra pdf clio-author ingest "Attention Is All You Need"        # title
uv run --extra pdf clio-author ingest https://arxiv.org/abs/1706.03762   # url
uv run --extra pdf clio-author ingest ./mypaper.pdf                      # local PDF
```
**Expect:** `extractor=docling`, ~125 sections, 12 figures. **Artifacts:** `runbook-out/ingest/`.

**`gather`** — ingest **many** sources (files / folders / globs / git repos / PDFs) into one merged
memory-block set. Deterministic (no LLM). Writes `context.json` (a drop-in `--blocks-file` for the
writing actions) + `context.md`. Directories/repos contribute their docs (`.md`/`.rst`/`.txt`/`.tex`
+ `README`); an explicit file path of any text/code type is ingested as given; PDFs/arXiv ids use the
`pdf` extra. Per-source failures are reported in `structured.skipped`, never fatal.

| Flag | Takes | Meaning |
|---|---|---|
| `--sources` | one or more strings | file/folder/glob path, git repo URL, arXiv id, or PDF URL/path |
| `--sources-file` | file path | sources listed one per line, or a JSON array of strings |
| `--out-dir` | dir path | persist `context.json` (drop-in `--blocks-file`) + `context.md` |
| `--max-files` | int | cap on files pulled from folders/globs/repos in total (default 50) |
| `--max-text-chars` | int | per-text-file character cap; longer files truncated (default 200000) |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys (`sources`, `out_dir`, `max_files`, `max_text_chars`) |
| `--out` | file path | save result |

```bash
# Merge a repo's docs + a notes folder + a PDF into one reusable context:
uv run --extra pdf clio-author gather \
  --sources https://github.com/owner/repo ./notes/ 2601.23265 \
  --out-dir runbook-out/context
# context.json then drops straight into any grounding action:
CLIO_LLM=claude uv run clio-author plan \
  --idea "my thesis" --blocks-file runbook-out/context/context.json
```
**Expect:** `metadata.ingested` units, merged `sections`/`figures`. **Artifacts:** `runbook-out/context/`.

> **Shortcut:** instead of running `gather` first, pass `--sources …` directly to `ask`, `plan`,
> `write`, `compose`, `research`, `kg`, or `review` — they auto-gather into grounding `blocks` before
> running (an explicit `--blocks-file`/`--blocks-json` still takes precedence).

---

## Act II · Understand it

**`ask`** — answer a question grounded in a paper. Give it the paper in **any** form: a `paper.md`
(`--markdown-file`), pre-built blocks (`--blocks-file`), or a **PDF/arXiv id via `--sources`** (it
auto-ingests). `ask` injects the top-`k` most relevant blocks (default 5) — for "what are the
contributions / experiments?" use **`--all`** to inject the whole paper.

| Flag | Takes | Meaning |
|---|---|---|
| `--question` | string (required) | the question to answer |
| `--markdown-file` | one file | a `paper.md` — split into blocks on the fly (no `blocks.json` needed) |
| `--text` | string | raw paper text inline |
| `--blocks-json` / `--blocks-file` | JSON / one file | a MemoryBlocks dump / file (for pre-ingested papers) |
| `--sources` | one or more | a PDF / arXiv id / folder — **auto-ingested** then answered (needs `--extra pdf`) |
| `--k` | int | how many blocks to inject (default 5; raise for broad questions) |
| `--all` | flag | inject the **whole paper** (best for contributions/experiments/summary questions) |
| `--format` | `structured`\|`prose` | default `structured` (JSON); `prose` for human-readable text |
| `--json` / `--out` | JSON object / file | merge extra payload keys / save result |

```bash
# from a paper.md, whole paper (no separate ingest, no blocks.json):
CLIO_LLM=claude uv run clio-author ask --markdown-file runbook-out/ingest/paper.md \
  --question "What are the contributions and what experiments do they run?" \
  --all --format prose --out runbook-out/answer.md

# straight from a PDF / arXiv id (auto-ingests, then answers):
CLIO_LLM=claude uv run --extra pdf clio-author ask --sources 1706.03762 \
  --question "What datasets and baselines are used?" \
  --all --format prose --out runbook-out/answer.md

# from pre-built blocks (top-8 retrieval), with better semantic ranking:
CLIO_RAG=semantic CLIO_LLM=claude uv run --extra rag clio-author ask \
  --blocks-file runbook-out/ingest/blocks.json --question "What problem does this solve?" \
  --k 8 --format prose --out runbook-out/answer.md
```
**Saves to:** `runbook-out/answer.md` (`--out` writes the prose for `.md`/`.txt`, full JSON for `.json`); the result is also printed to stdout.

**`kg`** — extract a content knowledge graph (claims/methods/datasets/results/metrics/concepts/tasks + relations).

| Flag | Takes | Meaning |
|---|---|---|
| `--blocks-json` | JSON string | inline MemoryBlocks dump |
| `--blocks-file` | one file | path to a JSON MemoryBlocks file |
| `--full` | flag | run the 6-stage pipeline (metadata→ontology→extraction→coref→verify→summary) with per-stage checkpoints |
| `--stages` | comma-separated list | restrict the pipeline to specific stage names (implies pipeline path; e.g. `metadata,ontology`) |
| `--resume` | directory | path to a prior run's `kg_pipeline/*.json` checkpoints to resume from |
| `--out-dir` | directory | persist `kg.json`/`kg.mmd` and (with `--full`) per-stage pipeline checkpoints under `kg_pipeline/` |
| `--format` | `structured`\|`prose` | `prose` emits a Mermaid `graph TD` rendering |
| `--json` | JSON object | merge payload keys |
| `--out` | file path | save result |

Plain `kg` (single-shot LLM extraction) is the default. `--full` activates the multi-stage pipeline; `--stages` lets you run a subset; `--resume DIR` feeds prior checkpoints so interrupted runs continue where they left off.

```bash
# Single-shot extraction (default):
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file runbook-out/ingest/blocks.json \
  --out-dir runbook-out/kg-out \
  --format prose          # prose => content is a Mermaid graph

# Full 6-stage pipeline with checkpoint writes:
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file runbook-out/ingest/blocks.json \
  --full --out-dir runbook-out/kg-pipeline

# Resume an interrupted pipeline run:
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file runbook-out/ingest/blocks.json \
  --full --resume runbook-out/kg-pipeline --out-dir runbook-out/kg-pipeline

# Run only specific pipeline stages:
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file runbook-out/ingest/blocks.json \
  --stages metadata,ontology --out-dir runbook-out/kg-pipeline
```
**Artifacts:** `runbook-out/kg-out/{kg.json, kg.mmd}`; pipeline: `runbook-out/kg-pipeline/kg_pipeline/{stage}.json`.

---

## Act III · Discover & verify the scholarship

**`discover`** — find real candidate papers for a topic via scholarly search. **No LLM needed.**

Queries the configured scholar backend (Semantic Scholar → OpenAlex → Crossref → arXiv with `CLIO_SCHOLAR=auto`).
Returns only records the search actually returns; never fabricates titles, authors, or identifiers.
Writes `discovered.json` + `discovered.bib` when `--out-dir` is set.

| Flag | Takes | Meaning |
|---|---|---|
| `--query` | string | the topic/query to search for (inline) |
| `--query-file` | one file | path to a file holding the query text |
| `--limit` | int (default 10) | maximum number of candidate papers to return |
| `--cutoff-date` | `YYYY-MM` string | keep only papers strictly before this date |
| `--out-dir` | directory | persist `discovered.json` + `discovered.bib` |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys (`query`, `topic`, `limit`, `cutoff_date`, `out_dir`) |
| `--out` | file path | save result |

Needs `CLIO_SCHOLAR` (default `auto`). The `scholar` extra adds the Semantic Scholar `httpx` path;
OpenAlex, Crossref, and arXiv use stdlib HTTP.

```bash
# Find up to 5 real papers on retrieval-augmented generation:
CLIO_SCHOLAR=auto uv run clio-author discover \
  --query "retrieval augmented generation" \
  --limit 5 \
  --out-dir runbook-out/discover-out

# With a recency gate (papers before 2024-01 only):
CLIO_SCHOLAR=auto uv run clio-author discover \
  --query "large language model evaluation" \
  --limit 10 --cutoff-date 2024-01 \
  --out-dir runbook-out/discover-out

# From a file and forcing arXiv only:
CLIO_SCHOLAR=arxiv uv run clio-author discover \
  --query-file runbook-out/topic.txt --limit 5
```
**Expect:** `structured.papers = [{title, year, authors, venue, abstract, paper_id, url}]`;
`metadata.count`, `metadata.backends_tried`. **Artifacts:** `runbook-out/discover-out/{discovered.json, discovered.bib}`.

---

**`cite`** — verify citation candidates; emits **suggestions only**, never overwrites.

| Flag | Takes | Meaning |
|---|---|---|
| `--candidates-json` | JSON string | inline list of `{title, year?, reason?}` |
| `--candidates-file` | one file | same format, as a JSON file |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys, e.g. `{"out_dir":"..."}` to persist `suggested.bib` |
| `--out` | file path | save result |

Backend via `CLIO_SCHOLAR` (see §1). Needs `--extra scholar` only for the Semantic-Scholar path
(arxiv/openalex/crossref are stdlib).
```bash
CLIO_SCHOLAR=auto uv run --extra scholar clio-author cite \
  --candidates-json '[{"title":"Attention Is All You Need","year":2017}]' \
  --json '{"out_dir":"runbook-out/cite-out"}'
# force one backend (no key/extra needed for these):
CLIO_SCHOLAR=arxiv  uv run clio-author cite --candidates-json '[{"title":"Attention Is All You Need"}]'
CLIO_SCHOLAR=openalex uv run clio-author cite --candidates-json '[{"title":"Attention Is All You Need"}]'
```
**Expect:** `num_verified=1 meets_90pct=True`. **Artifacts:** `runbook-out/cite-out/{suggested.bib, suggested_citation_map.json}`.

---

## Act IV · Judge it

**`review`** — produce a structured peer review of a paper.

| Flag | Takes | Meaning |
|---|---|---|
| `--paper` | string | paper Markdown text (inline) |
| `--paper-file` | one file | path to a paper Markdown file (e.g. `paper.md`) |
| `--ground` | flag | retrieve related prior work via `CLIO_SCHOLAR` and ground the review in it |
| `--figures-json` | JSON string | inline list of figures (`[{figure_id?, image_path, caption?}]`) to look at; needs `CLIO_VISION=gemini`; sets `metadata.vision_review=true` + `metadata.figures_seen` |
| `--figures-file` | one file | same format, as a JSON file |
| `--format` | `structured`\|`prose` | default `structured`; `prose` = narrative text |
| `--json` | JSON object | merge payload keys; use `{"persona":{"label":"..."}}` for reviewer persona |
| `--out` | file path | save result |

Output: **decision = Accept \| Reject**, **overall 1–10**, **7 axes 1–4** (originality, quality,
clarity, significance, soundness, presentation, contribution), **confidence 1–5**, + summary/
strengths/weaknesses/questions/limitations. With `--figures-json`/`--figures-file` and
`CLIO_VISION=gemini`, figure descriptions are folded into the reviewed text and
`metadata.vision_review` / `metadata.figures_seen` are set.
```bash
# (a) prose review (narrative):
CLIO_LLM=claude uv run clio-author review --paper-file runbook-out/ingest/paper.md \
  --format prose --out runbook-out/review.md

# (b) structured — the decision + all scores (default format = JSON):
CLIO_LLM=claude uv run clio-author review --paper-file runbook-out/ingest/paper.md \
  2>/dev/null | python3 -m json.tool

# (c) grounded — retrieve real related work and ground the critique in it:
CLIO_SCHOLAR=auto CLIO_LLM=claude uv run clio-author review \
  --paper-file runbook-out/ingest/paper.md --ground --format prose

# (d) reviewer persona via --json (the `persona` payload key):
CLIO_LLM=claude uv run clio-author review --paper-file runbook-out/ingest/paper.md \
  --json '{"persona":{"label":"harsh reviewer"}}' --format prose

# (e) multimodal review — reviewer sees the actual figure images (needs CLIO_VISION=gemini):
CLIO_VISION=gemini GEMINI_API_KEY=... CLIO_LLM=claude uv run clio-author review \
  --paper-file runbook-out/ingest/paper.md \
  --figures-json '[{"figure_id":1,"image_path":"runbook-out/ingest/img/figure1.png","caption":"Overview"}]' \
  --format prose
```
**Expect:** in (b) `metadata.decision` ∈ {Accept, Reject}, `metadata.overall` 1–10; (c) adds `metadata.related_work`; (e) adds `metadata.vision_review=true`, `metadata.figures_seen`.

**`meta_review`** *(run-only)* — aggregate reviews → one area-chair decision (offline).

Payload keys: `reviews` (list of review dicts).
```bash
uv run clio-author run meta_review \
  --json '{"reviews":[{"Overall":7,"Decision":"Accept"},{"Overall":5,"Decision":"Reject"}]}'
```

**`rebuttal`** — draft an author rebuttal addressing a review point by point.

| Flag | Takes | Meaning |
|---|---|---|
| `--paper` | string | paper/draft Markdown text (inline) |
| `--paper-file` | one file | path to a paper/draft Markdown file (e.g. `paper.md`) |
| `--review-json` | JSON string | a `PaperReview` dump (inline) to respond to; also accepts `{"weaknesses":[...],"questions":[...]}` loose dicts |
| `--review-file` | one file | path to a JSON `PaperReview` file (e.g. a saved `review` result) |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; also reads `review_text` / `critic_notes` for free-form review text |
| `--out` | file path | save result |

Reads the manuscript from `paper`/`draft`/`markdown` and the review from `review` (a
`PaperReview` dump/dict), `review_text`, or `critic_notes`. Returns `content` = the rebuttal prose,
`structured["rebuttal"]` = same text. When `target` is set (via `--json`), the rebuttal is written
to that file. Never invents results or citations.
```bash
# prose rebuttal to a structured review saved from a prior review run:
CLIO_LLM=claude uv run clio-author rebuttal \
  --paper-file runbook-out/ingest/paper.md \
  --review-file runbook-out/review.json \
  --format prose --out runbook-out/rebuttal.md

# inline JSON review (loose dict with weaknesses + questions):
CLIO_LLM=claude uv run clio-author rebuttal \
  --paper-file runbook-out/ingest/paper.md \
  --review-json '{"weaknesses":["no baseline comparison","evaluation unclear"],"questions":["how is X measured?"]}' \
  --format prose
```
**Expect:** `content` = a point-by-point rebuttal grounded in the paper; `structured.rebuttal` = same text.

**`coherence`** — check cross-section consistency (terminology, contradictions, undefined terms, duplication, flow).

| Flag | Takes | Meaning |
|---|---|---|
| `--sections-json` | JSON string | inline list of `{title, draft}` |
| `--sections-file` | one file | same format, as a JSON file |
| `--markdown-file` | one file | a full Markdown manuscript to split into sections |
| `--text` | string | single passage to check (inline fallback) |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge any additional payload key |
| `--out` | file path | save result |

```bash
CLIO_LLM=claude uv run clio-author coherence \
  --sections-json '[{"title":"Introduction","draft":"X improves accuracy by 5%."},{"title":"Results","draft":"X achieves a 12% gain."}]' \
  --format prose
# or check a whole manuscript file: --markdown-file runbook-out/compose-out/paper.md
```

**`check_refs`** — deterministically lint a BibTeX bibliography and cross-check `\cite{}` keys in the prose. **No model needed.**

| Flag | Takes | Meaning |
|---|---|---|
| `--bibtex` | string | BibTeX bibliography text (inline) |
| `--bibtex-file` | one file | path to a `.bib` file |
| `--markdown-file` | one file | Markdown manuscript to scan for `\cite{}` keys |
| `--text` | string | prose to scan for `\cite{}` keys (inline) |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; also reads `sections` |
| `--out` | file path | save result |

```bash
uv run clio-author check-refs \
  --bibtex-file runbook-out/cite-out/suggested.bib \
  --markdown-file runbook-out/compose-out/paper.md
```
**Expect:** `structured` = `{malformed[], duplicates[], missing_in_bib[], uncited_entries[], counts}`; emits suggestions only, never modifies files.

**`section_review`** — three-layer review of a single section: L1 reference check → L2 coherence → L3 persona peer review.

| Flag | Takes | Meaning |
|---|---|---|
| `--text` | string | the section text (inline) |
| `--text-file` | one file | file holding the section text |
| `--bibtex-file` | one file | BibTeX file for the L1 reference check |
| `--persona-json` | JSON string | a `PersonaSpec` for the L3 reviewer (inline), e.g. `{"label":"harsh reviewer"}` |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; also reads `section`, `markdown`, `out_dir` |
| `--out` | file path | save result |

```bash
CLIO_LLM=claude uv run clio-author section-review \
  --text-file runbook-out/compose-out/sections/01-introduction.md \
  --bibtex-file runbook-out/cite-out/suggested.bib \
  --format prose

# With a custom reviewer persona:
CLIO_LLM=claude uv run clio-author section-review \
  --text-file runbook-out/compose-out/sections/01-introduction.md \
  --persona-json '{"label":"harsh ML reviewer"}' --format prose
```
**Expect:** `structured` = `{layer1, layer2, layer3, severity_summary: [{layer, severity, detail}]}`; `metadata` = `{num_findings, max_severity}` where severity ∈ {critical, major, minor}.

**`audit`** — deterministic manuscript completeness checklist. **No model needed.**

| Flag | Takes | Meaning |
|---|---|---|
| `--sections-json` | JSON string | inline list of `{title, draft, word_budget?}` |
| `--sections-file` | one file | same format, as a JSON file |
| `--markdown-file` | one file | full Markdown manuscript to split and audit |
| `--bibtex-file` | one file | BibTeX file for citation-coverage checking |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; also reads `outline`, `candidates`, `verified` |
| `--out` | file path | save result |

```bash
uv run clio-author audit \
  --markdown-file runbook-out/compose-out/paper.md \
  --bibtex-file runbook-out/cite-out/suggested.bib

# From structured sections with an outline for required-section check:
uv run clio-author audit \
  --sections-file runbook-out/compose-out/sections.json \
  --json '{"outline":{"title":"AUTHOR","sections":[{"title":"Introduction"},{"title":"Method"},{"title":"Experiments"},{"title":"Conclusion"}]}}' \
  --format prose
```
**Expect:** `structured` = `{missing_sections[], word_counts[], placeholders, coverage}`; `metadata` = `{passed, num_sections, num_problems}`.

---

## Act V · Plan, then write a new paper

**`plan`** — turn an idea or outline into per-section writing plans (tasks, claims, sources, word budgets).

> `plan` has **no** `--source`/`--source-file` flags (unlike `write`). Ground it via
> `--blocks-file` or `--log`/`--log-file`.

| Flag | Takes | Meaning |
|---|---|---|
| `--idea` | string | research idea / thesis (inline) |
| `--idea-file` | one file | file holding the idea text |
| `--log` | string | experimental log / results notes (inline) |
| `--log-file` | one file | file holding the experimental log |
| `--outline-json` | JSON string | a `PaperOutline` to plan against instead of generating one |
| `--outline-file` | one file | same format, as a JSON file |
| `--blocks-file` | one file | JSON MemoryBlocks file for grounding |
| `--candidates-file` | one file | JSON citation candidates to fold into citation hints |
| `--out-dir` | directory | persist `plan.json` |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge any additional payload key |
| `--out` | file path | save result |

The output `plans` feed `write` (`--json '{"section_plan":{...}}'`) or `compose --plan`.
Each `SectionOutline` in the returned plan includes `research_needed` (bool) and `research_topics`
(list of strings) — these flag sections that benefit from a `research` action call before drafting.
```bash
CLIO_LLM=claude uv run clio-author plan \
  --idea "AUTHOR: a multi-agent system that reads, reviews, and writes scientific papers." \
  --outline-json '{"title":"AUTHOR","sections":[{"title":"Introduction","goal":"motivate + state the contribution"},{"title":"Method","goal":"the multi-agent pipeline"}]}' \
  --json '{"out_dir":"runbook-out/plan-out"}'
# or plan straight from an idea (it generates the outline first):
CLIO_LLM=claude uv run clio-author plan --idea "cooperating agents for the paper lifecycle" --out runbook-out/plan.json
```
**Expect:** `num_sections`, `num_tasks`, `plan_errors=0`; each plan has tasks/claims/sources + a word budget.
**Artifacts:** `runbook-out/plan-out/plan.json`.

**`experiment`** — read reference papers' design/architecture/experiments and recreate an
evaluation plan for your new paper. Phase 1 extracts each paper's `PaperDesign` (research questions,
architecture, datasets, baselines, metrics, ablations, protocol, compute, limitations); phase 2 (when
`--idea` is given) synthesises an `EvaluationPlan` grounded in those references and adapted to the new
idea. Multi-paper input comes from a `gather` `context.json` (or `--sources`); a single paper can be
given as `--markdown-file`/`--text`.

| Flag | Takes | Meaning |
|---|---|---|
| `--sources` | one or more strings | reference papers/folders/globs/git/PDFs (auto-ingested, multi-paper) |
| `--sources-file` | one file | sources one per line, or a JSON array |
| `--blocks-json` | JSON string | inline MemoryBlocks of the reference paper(s) |
| `--blocks-file` | one file | a `gather` `context.json` / `blocks.json` of the reference paper(s) |
| `--markdown-file` | one file | a single reference paper's Markdown |
| `--text` | string | a single reference paper's text inline |
| `--idea` / `--idea-file` | string / file | the **new** paper's idea — supplying it recreates the eval plan |
| `--out-dir` | directory | persist `experiment_designs.*` + `evaluation_plan.*` |
| `--format` | `structured`\|`prose` | `prose` prints the rendered evaluation plan |
| `--json` | JSON object | merge any additional payload key |
| `--out` | file path | save result |

```bash
# Read two reference papers and recreate an evaluation plan for a new idea:
CLIO_LLM=claude uv run --extra pdf clio-author experiment \
  --sources 2106.09685 ./related/fastcache.pdf \
  --idea "An RL cache-eviction policy for scientific data workloads" \
  --json '{"out_dir":"runbook-out/experiment"}' --format prose
```
**Expect:** `num_papers`, `has_plan=true`; per-paper designs + a grounded evaluation plan.
**Artifacts:** `runbook-out/experiment/experiment_designs.{json,md}` + `evaluation_plan.{json,md}`.

**`research`** — produce a grounded literature brief for a topic or section.

| Flag | Takes | Meaning |
|---|---|---|
| `--topic` | string | the topic to research (inline) |
| `--topic-file` | one file | file holding the topic text |
| `--blocks-file` | one file | JSON MemoryBlocks file for grounding context |
| `--depth` | `standard`\|`deep` | research depth; `deep` aims for more sources and precise gaps |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; also reads `section`, `outline`, `source`, `out_dir`, `discover` |
| `--out` | file path | save result |

The `discover` payload key (pass via `--json '{"discover":true}'`) seeds the brief's `recent` bucket from
real discovered papers via the configured scholar backend before LLM synthesis, giving the brief a
grounded starting point.

```bash
CLIO_LLM=claude uv run clio-author research \
  --topic "attention mechanisms for long-range dependencies" --format prose

# With CLIO_SCHOLAR set, proposed titles are verified against a scholar backend:
CLIO_SCHOLAR=auto CLIO_LLM=claude uv run clio-author research \
  --topic "transformer self-attention" --depth deep --format prose \
  --out runbook-out/research.md

# With real discovered papers seeding the recent bucket:
CLIO_SCHOLAR=auto CLIO_LLM=claude uv run clio-author research \
  --topic "transformer self-attention" \
  --json '{"discover":true}' --format prose

# Supply a section name and outline via --json for section-specific research:
CLIO_LLM=claude uv run clio-author research \
  --json '{"section":"Related Work","outline":"AUTHOR: multi-agent paper lifecycle"}' \
  --blocks-file runbook-out/ingest/blocks.json --format prose
```
**Expect:** `structured` = `{topic, foundational[], recent[], competing[], gaps[], synthesis, confidence, recommendations[]}`; `metadata` = `{num_sources, confidence, grounded}`.

**`verify_work`** — goal-backward check of written prose against the claims it was supposed to make.

| Flag | Takes | Meaning |
|---|---|---|
| `--text` | string | the written prose to verify (inline) |
| `--text-file` | one file | file holding the written prose |
| `--section-plan-json` | JSON string | a `SectionPlan` whose `claims` to verify (inline) |
| `--section-plan-file` | one file | path to a JSON `SectionPlan` file |
| `--claims-json` | JSON string | an explicit list of claim strings to verify (inline) |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys |
| `--out` | file path | save result |

```bash
CLIO_LLM=claude uv run clio-author verify-work \
  --text-file runbook-out/compose-out/sections/01-introduction.md \
  --claims-json '["AUTHOR unifies ingestion, review, and writing","The harness is grounded; it invents no citations"]' \
  --format prose

# From a saved section plan (output of plan):
CLIO_LLM=claude uv run clio-author verify-work \
  --text-file runbook-out/compose-out/sections/01-introduction.md \
  --section-plan-file runbook-out/plan-out/plan.json \
  --format prose
```
**Expect:** `structured` = `{claims: [{claim, made, supported, evidence, gap}], gaps[], status}`; `metadata` = `{num_claims, num_gaps, status}` where `status` ∈ {VERIFIED, GAPS}.

**`write`** — draft one paper section from an outline and source material.

| Flag | Takes | Meaning |
|---|---|---|
| `--source` | string | source material (inline) |
| `--source-file` | one file | source-material file (e.g. `paper.md`) — single file only |
| `--outline` | string | the section title; richer outlines (with `goal`, etc.) via `--json '{"outline":{...}}'` |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; use for `section_plan`, `blocks`, `vision`, `out_path` |
| `--out` | file path | save result |

```bash
CLIO_LLM=claude uv run clio-author write \
  --outline "Introduction" --source-file runbook-out/ingest/paper.md --format prose
```

**`write_review`** *(run-only)* — writer ↔ reviewer critic-refine loop.

Payload keys: `outline`, `section_plan`, `blocks`, `source`, `max_rounds`.
```bash
CLIO_LLM=claude uv run clio-author run write_review \
  --json '{"outline":{"title":"Introduction","goal":"introduce AUTHOR"},"source":"AUTHOR reads, reviews, and writes papers.","max_rounds":1}'
```

**`compose`** — draft a whole multi-section manuscript (outline → cite → write per section → assemble).

| Flag | Takes | Meaning |
|---|---|---|
| `--idea` | string | research idea / thesis (inline) |
| `--idea-file` | one file | file holding the idea text |
| `--log` | string | experimental log / results notes (inline) |
| `--log-file` | one file | file holding the experimental log |
| `--outline-json` | JSON string | a `PaperOutline` to use instead of generating one |
| `--outline-file` | one file | same format, as a JSON file |
| `--candidates-file` | one file | JSON citation candidates to verify and cite |
| `--review` | flag | run a per-section writer/reviewer refine loop |
| `--max-rounds` | int (default 3) | max writer/reviewer rounds per section when `--review` is set |
| `--out-dir` | directory | persist `paper.md` + per-section files |
| `--latex` | flag | also export `paper.tex` (+`references.bib`) when `--out-dir` is set |
| `--pdf` | flag | compile `paper.pdf` from the LaTeX (implies `--latex`; needs a LaTeX engine on PATH) |
| `--plan` | flag | plan each section (tasks/claims/sources) before drafting |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; use for `blocks` and other advanced keys |
| `--out` | file path | save result |

PDF compilation is best-effort: `tectonic`, `latexmk`, and `pdflatex` are tried in that order.
On success `metadata["pdf"]` holds the path; on failure `metadata["pdf_error"]` holds the reason
and compose still succeeds with the Markdown + LaTeX output intact.

```bash
# provided outline, no review:
CLIO_LLM=claude uv run clio-author compose \
  --idea "AUTHOR: a multi-agent system that reads, reviews, and writes scientific papers." \
  --outline-json '{"title":"AUTHOR","sections":[{"title":"Introduction","goal":"motivate"},{"title":"Method","goal":"the pipeline"}]}' \
  --out-dir runbook-out/compose-out

# generate the outline from just the idea, add a per-section refine pass and a log:
CLIO_LLM=claude uv run clio-author compose \
  --idea "AUTHOR: cooperating agents for the paper lifecycle." \
  --log "On PaperBananaBench, AUTHOR verified 1/1 citations and drafted 2 sections." \
  --review --max-rounds 1 --out-dir runbook-out/compose-gen

# write + export LaTeX + compile PDF in one call:
CLIO_LLM=claude uv run clio-author compose \
  --idea "AUTHOR: cooperating agents for the paper lifecycle." \
  --review --out-dir runbook-out/compose-pdf --pdf
```
**Artifacts:** `runbook-out/compose-out/{paper.md, sections/01-*.md, 02-*.md}`;
with `--pdf`: also `paper.tex`, `references.bib`, `paper.pdf` (if a LaTeX engine is found).

---

## Act VI · Refine the prose

**`revise`** — one revision action with two modes. `--mode feedback` (default) addresses reviewer
critique and may change content; `--mode style` polishes clarity/flow/voice while preserving meaning
and `\cite{}` placeholders. (Subsumes the legacy `edit` / `polish` aliases — see below.)

| Flag | Takes | Meaning |
|---|---|---|
| `--mode` | `feedback`\|`style` | `feedback` = address review (may change content); `style` = polish voice |
| `--text` / `--text-file` | string / one file | the prose to revise |
| `--review-json` / `--review-file` | JSON / one file | reviewer feedback to address (feedback mode) |
| `--critic-notes` | string | free-form directive feedback (feedback mode) |
| `--voice` | string | target voice, e.g. `concise` or `formal` (style mode) |
| `--target` | one file | file (under harness root) to apply the revision to |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys |
| `--out` | file path | save result |

```bash
# Style polish:
CLIO_LLM=claude uv run clio-author revise --mode style \
  --text "We propose a method. It is good. It does many useful things." --voice concise --format prose
# Feedback-driven revision:
CLIO_LLM=claude uv run clio-author revise \
  --text "We propose a system. It is good." \
  --review-json '{"weaknesses":["no baseline comparison","unclear evaluation"]}'
```

> **Aliases (back-compat).** `polish` ≡ `revise --mode style` (keeps its own subcommand);
> `edit` ≡ `revise --mode feedback` (run-only: `clio-author run edit --json '{"draft":"…","review":{…}}'`).
> Both still work unchanged.

---

## Act VII · Illustrate

**`plot`** *(run-only)* — generate matplotlib code (or a Gemini image with `kind="diagram"` + `CLIO_VISION=gemini`).

Payload keys: `spec`, `out_path`.
```bash
CLIO_LLM=claude uv run clio-author run plot \
  --json '{"spec":{"kind":"plot","intent":"bar chart comparing baseline 72 vs ours 89"}}'
# real image route:
CLIO_VISION=gemini CLIO_LLM=claude uv run clio-author run plot \
  --json '{"spec":{"kind":"diagram","intent":"flowchart: ingest -> review -> write"},"out_path":"runbook-out/diagram.png"}'
```

**`describe`** (action `describe_figures`) — caption figures using vision.

| Flag | Takes | Meaning |
|---|---|---|
| `--blocks-json` | JSON string | inline MemoryBlocks dump whose figures to describe |
| `--blocks-file` | one file | path to a JSON MemoryBlocks file |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; also reads `figures` and `context` |
| `--out` | file path | save result |

Caption figures (Gemini vision *looks at* the image when `CLIO_VISION=gemini`).
```bash
CLIO_VISION=gemini uv run clio-author describe \
  --blocks-json '{"figures":[{"figure_id":1,"image_path":"'"$PWD"'/runbook-out/ingest/img/figure1.png"}]}' \
  --format prose
```
**Expect:** `vision_described:[1]` + a real description.

**`figure_refine`** *(run-only)* — figure visualizer ↔ critic refine loop.

Payload keys: `spec`, `out_path`, `max_rounds`.
```bash
CLIO_LLM=claude uv run clio-author run figure_refine \
  --json '{"spec":{"kind":"plot","intent":"line chart of loss vs epochs; save to figure.png"},"max_rounds":1}' \
  > runbook-out/figure_refine.json 2>/dev/null
uv run --extra viz python -c "
from pathlib import Path; import json
from clio_author.experts.figure_agent import render_plot_code
code = json.load(open('runbook-out/figure_refine.json'))['content']
print('rendered:', render_plot_code(code, Path('runbook-out/figure.png'), timeout=40))"
```

---

## Act VIII · Ship it — LaTeX + PDF

**`export`** — convert Markdown to compilable `paper.tex` (+ `references.bib`), optionally compile PDF.

| Flag | Takes | Meaning |
|---|---|---|
| `--title` | string | manuscript title (optional) |
| `--sections-json` | JSON string | inline list of `{title, draft}` |
| `--sections-file` | one file | same format, as a JSON file |
| `--markdown-file` | one file | a full Markdown manuscript to split and export |
| `--bibtex-file` | one file | BibTeX file to emit as `references.bib` |
| `--out-dir` | directory | persist `paper.tex` (+ `references.bib`; + `paper.pdf` with `--pdf`) |
| `--pdf` | flag | compile `paper.pdf` from the written `.tex` (needs `--out-dir` and a LaTeX engine on PATH); sets `metadata.pdf` on success or `metadata.pdf_error` on failure; never fails the export |
| `--json` | JSON object | merge payload keys (`title`, `sections`, `markdown`, `outline`, `bibtex`, `out_dir`, `pdf`) |
| `--out` | file path | save result |

Note: `export` has no `--format` flag. PDF compilation tries `tectonic`, then `latexmk`, then
`pdflatex`; if none is found the export still succeeds and `metadata.pdf_error` records the reason.

```bash
uv run clio-author export --title "Demo Paper" \
  --sections-json '[{"title":"Introduction","draft":"We present **AUTHOR**."},{"title":"Method","draft":"It uses a multi-agent pipeline."}]' \
  --out-dir runbook-out/export-out
# from a whole manuscript file + a bib:
uv run clio-author export --title "AUTHOR" --markdown-file runbook-out/compose-out/paper.md \
  --bibtex-file runbook-out/cite-out/suggested.bib --out-dir runbook-out/export-out2
# compile PDF in the same call:
uv run clio-author export --title "AUTHOR" --markdown-file runbook-out/compose-out/paper.md \
  --bibtex-file runbook-out/cite-out/suggested.bib --out-dir runbook-out/export-pdf --pdf
```
**Artifacts:** `paper.tex` (+ `references.bib` when bib is given); with `--pdf` also `paper.pdf` if a LaTeX engine is available.

…or one shot — **`compose --latex`** / **`compose --pdf`** writes Markdown *and* LaTeX *and* optionally PDF:
```bash
CLIO_LLM=claude uv run clio-author compose \
  --idea "AUTHOR: cooperating agents for the paper lifecycle." \
  --latex --out-dir runbook-out/paper
# with PDF:
CLIO_LLM=claude uv run clio-author compose \
  --idea "AUTHOR: cooperating agents for the paper lifecycle." \
  --pdf --out-dir runbook-out/paper-pdf
```
**Artifacts (--latex):** `runbook-out/paper/{paper.md, sections/, paper.tex, references.bib}`.
**Artifacts (--pdf):** same, plus `paper.pdf` when a LaTeX engine is on PATH.

---

## Act IX · Drive it with a goal

**`orchestrate`** — plan and run a sequence of actions to achieve a natural-language goal.

| Flag | Takes | Meaning |
|---|---|---|
| `--goal` | string | the goal to achieve (inline) |
| `--goal-file` | one file | file holding the goal text |
| `--inputs-json` | JSON object | named inputs dict (inline), e.g. `{"source":"2601.23265"}`; referenced as `@name` in the plan |
| `--inputs-file` | one file | same format, as a JSON file |
| `--max-steps` | int (default 6) | maximum number of planned steps to execute |
| `--out-dir` | directory | persist `orchestrate.json` |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge any additional payload key |
| `--out` | file path | save result |

```bash
# ingest a paper and review it in one goal-driven run:
CLIO_LLM=claude uv run clio-author orchestrate \
  --goal "Ingest the paper 2601.23265, then produce a structured peer review." \
  --inputs-json '{"source":"2601.23265"}' \
  --max-steps 4 --out-dir runbook-out/orchestrate-out

# goal from a file, inputs from a file:
CLIO_LLM=claude uv run clio-author orchestrate \
  --goal-file runbook-out/goal.txt \
  --inputs-file runbook-out/inputs.json \
  --out-dir runbook-out/orchestrate-out
```
**Artifacts:** `runbook-out/orchestrate-out/orchestrate.json`.

---

## The run-only actions — payload key reference

These actions have no dedicated subcommand. Reach them with `clio-author run <action> --json '{...}'`.
All other actions have dedicated subcommands — see Appendix A.

| Action | Payload keys | Purpose |
|---|---|---|
| `edit` | `draft`, `review`, `critic_notes`, `target` | revise prose to address reviewer feedback |
| `meta_review` | `reviews` | aggregate several reviews into one area-chair meta-review |
| `plot` | `spec`, `out_path` | generate matplotlib code or a Gemini diagram image |
| `write_review` | `outline`, `section_plan`, `blocks`, `source`, `max_rounds` | writer ↔ reviewer critic-refine loop |
| `figure_refine` | `spec`, `out_path`, `max_rounds` | figure visualizer ↔ critic refine loop |

---

## 4. Where outputs go
- **stdout** always (the JSON result); **`--out FILE`** to also save it.
- **`out_dir` / `out_path`** (payload keys / `--out-dir`) persist structured artifacts:
  ingest → `paper.md`+`blocks.json`+`img/`; cite → `suggested.bib`; discover → `discovered.json`+`discovered.bib`;
  kg → `kg.json`+`kg.mmd`; compose → `paper.md`+`sections/`(+`paper.tex` with `--latex`; +`paper.pdf` with `--pdf`);
  export → `paper.tex`+`references.bib`(+`paper.pdf` with `--pdf`);
  orchestrate → `orchestrate.json`; write/plot/figure_refine → `out_path`.
- Print-only otherwise (ask, review, edit, polish, coherence, meta_review) — use `--out` to capture.

## 5. Tips
- Pretty-print JSON: `… 2>/dev/null | python3 -m json.tool`.
- Any action: `clio-author run <action> --json '{...}'` (the universal escape hatch).
- Big inputs → use the `--*-file` flags (inline JSON can exceed the shell arg limit). Each
  `--*-file` flag reads exactly **one** file — concatenate multiple inputs before passing.
- In-process: `from clio_author.integration.clio_adapter import ClioAuthorSubagent`;
  `ClioAuthorSubagent(llm=…).run("review", {"paper": "..."})`.
- See a subcommand's exact flags anytime: `clio-author <cmd> --help`.

## Appendix A — all 27 actions at a glance

| # | Action | Dedicated subcommand |
|---|---|---|
| 1 | `ingest` | `clio-author ingest <source>` |
| 2 | `ask` | `clio-author ask` |
| 3 | `kg` | `clio-author kg` |
| 4 | `discover` | `clio-author discover` |
| 5 | `cite` | `clio-author cite` |
| 6 | `check_refs` | `clio-author check-refs` |
| 7 | `research` | `clio-author research` |
| 8 | `review` | `clio-author review` |
| 9 | `meta_review` | `clio-author run meta_review` |
| 10 | `section_review` | `clio-author section-review` |
| 11 | `rebuttal` | `clio-author rebuttal` |
| 12 | `verify_work` | `clio-author verify-work` |
| 13 | `audit` | `clio-author audit` |
| 14 | `plan` | `clio-author plan` |
| 15 | `write` | `clio-author write` |
| 16 | `edit` | `clio-author run edit` |
| 17 | `polish` | `clio-author polish` |
| 18 | `coherence` | `clio-author coherence` |
| 19 | `compose` | `clio-author compose` |
| 20 | `write_review` | `clio-author run write_review` |
| 21 | `plot` | `clio-author run plot` |
| 22 | `describe_figures` | `clio-author describe` |
| 23 | `figure_refine` | `clio-author run figure_refine` |
| 24 | `export` | `clio-author export` |
| 25 | `orchestrate` | `clio-author orchestrate` |

## Appendix B — each action's LLM prompt source (to read/tune)
| Action | Prompt constant | File |
|---|---|---|
| ask | `PAPER_QA_SYSTEM_PROMPT` | `clio_author/experts/paper_qa.py` |
| review | `build_reviewer_system_prompt()` (persona-conditioned) | `clio_author/experts/reviewer.py` |
| meta_review | (deterministic, no prompt) | `clio_author/experts/meta_reviewer.py` |
| rebuttal | `REBUTTAL_SYSTEM_PROMPT` | `clio_author/experts/rebuttal.py` |
| plan | `PLANNER_SYSTEM_PROMPT` | `clio_author/experts/planner.py` |
| write / write_review | `WRITER_SYSTEM_PROMPT` | `clio_author/experts/writer.py`, `write_loop.py` |
| edit | `EDITOR_SYSTEM_PROMPT` | `clio_author/experts/editor.py` |
| polish | `POLISH_SYSTEM_PROMPT` | `clio_author/experts/polish.py` |
| coherence | `COHERENCE_SYSTEM_PROMPT` | `clio_author/experts/coherence.py` |
| kg | `KG_SYSTEM_PROMPT` + `KG_PROMPT` | `clio_author/experts/kg.py`, `clio_author/retrieval/kg.py` |
| research | `RESEARCH_SYSTEM_PROMPT` | `clio_author/experts/research.py` |
| verify_work | `VERIFY_WORK_SYSTEM_PROMPT` | `clio_author/experts/verify_work.py` |
| check_refs | (deterministic, no LLM call) | `clio_author/experts/check_refs.py`, `bib_utils.py` |
| section_review | composes check_refs + coherence + reviewer | `clio_author/experts/section_review.py` |
| audit | (deterministic, no LLM call) | `clio_author/experts/audit.py` |
| plot / describe / figure_refine | figure prompts | `clio_author/experts/figure_agent.py` |
| compose | outline-gen prompt | `clio_author/experts/compose.py` |
| orchestrate | orchestrate prompt | `clio_author/experts/orchestrate.py` |
| cite | (deterministic verify) | `clio_author/retrieval/scholar.py` |
| discover | `DISCOVER_SYSTEM_PROMPT` (no LLM call on search path) | `clio_author/experts/discover.py` |
| export | (deterministic Markdown→LaTeX + optional compile_pdf) | `clio_author/export/latex.py` |

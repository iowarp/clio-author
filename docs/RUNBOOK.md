# AUTHOR (clio-author) — CLI Runbook

A complete, copy-paste reference: **every subcommand, every flag, every setting.** Run the blocks
one at a time and inspect each result. Arranged as a paper's life — **read → understand → verify
sources → judge → write → refine → illustrate → ship.**

- Every command prints a JSON result on **stdout** (logs → stderr; add `2>/dev/null` for clean JSON).
  Exit code `0` = ok, `1` = error.
- **Every** subcommand accepts `--out FILE` (also save the result — prose for `.md`/`.txt`, full
  JSON for `.json`). Text actions and most file-reading subcommands also accept `--json '{...}'`
  (merge extra payload keys) — see the per-subcommand tables below for which flags each one takes.
- Text actions need a model (`CLIO_LLM=…`); without one they return an offline **echo** placeholder.

> **Single-file rule.** Every `--*-file` flag reads exactly **one** file (internally `_read_file`
> in `cli.py`; no `nargs`, `append`, or glob). To supply several files as context, concatenate them
> into one file first, or `ingest` each one and pass the resulting `blocks.json`. This applies to
> every file-taking flag listed in this document.

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
| `CLIO_LLM` | **`echo`** · `claude` · `codex` · `ollama` | all text actions |
| `CLIO_LLM_MODEL` | any model name (provider-specific) | the chosen `CLIO_LLM` |
| `CLIO_OLLAMA_URL` | **`http://localhost:11434`** | `CLIO_LLM=ollama` |
| `CLIO_SCHOLAR` | **`auto`** (=`cascade`/`all`) · `semantic`(`s2`) · `openalex`(`oa`) · `crossref`(`cr`) · `arxiv` · `off`(`none`/`offline`/`disabled`) | `cite`, `review --ground` |
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
| `--json '{...}'` | merge a JSON object into the action payload (available on all subcommands except `capabilities`) |
| `-h` / `--help` | show that subcommand's exact flags |

## 3. Health check

```bash
uv run ruff check clio_author tests        # -> All checks passed!
uv run mypy clio_author                    # -> Success: no issues found in 55 source files
uv run pytest -q                           # -> 434 passed, 3 skipped, 10 deselected
uv run clio-author capabilities            # -> name=clio-author, version 0.3.0, 19 actions
```

> **16 subcommands** have dedicated flags: `capabilities, ingest, ask, review, cite, plan, write,
> compose, export, polish, coherence, kg, describe, orchestrate, rebuttal, run`. The other **5 actions**
> (`edit`, `meta_review`, `plot`, `write_review`, `figure_refine`) have **no dedicated subcommand**
> — reach them with `clio-author run <action> --json '{...}'`. `run <action>` works for *any* of
> the 19 actions.

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

---

## Act II · Understand it

**`ask`** — answer a question grounded in memory blocks.

| Flag | Takes | Meaning |
|---|---|---|
| `--question` | string (required) | the question to answer |
| `--blocks-json` | JSON string | inline MemoryBlocks dump; prefer `--blocks-file` for real papers |
| `--blocks-file` | one file | path to a JSON MemoryBlocks file (avoids arg-length limits) |
| `--format` | `structured`\|`prose` | default `structured` (JSON); `prose` for human-readable text |
| `--json` | JSON object | merge any additional payload key |
| `--out` | file path | save result |

```bash
CLIO_LLM=claude uv run clio-author ask \
  --question "What problem does this paper solve?" \
  --blocks-file runbook-out/ingest/blocks.json \
  --format prose \
  --out runbook-out/answer.md
# inline blocks instead of a file: --blocks-json '{"sections":[...]}'
```

**`kg`** — extract a content knowledge graph (claims/methods/datasets/results/metrics/concepts/tasks + relations).

| Flag | Takes | Meaning |
|---|---|---|
| `--blocks-json` | JSON string | inline MemoryBlocks dump |
| `--blocks-file` | one file | path to a JSON MemoryBlocks file |
| `--format` | `structured`\|`prose` | `prose` emits a Mermaid `graph TD` rendering |
| `--json` | JSON object | merge payload keys, e.g. `{"out_dir":"..."}` to write `kg.json`/`kg.mmd` |
| `--out` | file path | save result |

```bash
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file runbook-out/ingest/blocks.json \
  --json '{"out_dir":"runbook-out/kg-out"}' \
  --format prose          # prose => content is a Mermaid graph
```
**Artifacts:** `runbook-out/kg-out/{kg.json, kg.mmd}`.

---

## Act III · Verify the scholarship

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
| `--plan` | flag | plan each section (tasks/claims/sources) before drafting |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; use for `blocks` and other advanced keys |
| `--out` | file path | save result |

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
```
**Artifacts:** `runbook-out/compose-out/{paper.md, sections/01-*.md, 02-*.md}`.

---

## Act VI · Refine the prose

**`edit`** *(run-only)* — revise prose to address reviewer feedback (preserves citations).

Payload keys: `draft`, `review`, `critic_notes`, `target`.
```bash
CLIO_LLM=claude uv run clio-author run edit \
  --json '{"draft":"We propose a system. It is good.","review":{"weaknesses":["no baseline comparison","unclear evaluation"]}}'
```

**`polish`** — polish prose for clarity, flow, and academic voice.

| Flag | Takes | Meaning |
|---|---|---|
| `--text` | string | prose to polish (inline) |
| `--text-file` | one file | file holding the prose to polish |
| `--voice` | string | target voice, e.g. `concise` or `formal` |
| `--target` | one file | file (under harness root) to apply the polished text to |
| `--format` | `structured`\|`prose` | default `structured` |
| `--json` | JSON object | merge payload keys; also reads `draft` via `--json` |
| `--out` | file path | save result |

```bash
CLIO_LLM=claude uv run clio-author polish \
  --text "We propose a method. It is good. It does many useful things." \
  --voice concise --format prose
# --target FILE applies the polished text to a file under the harness root.
```

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

## Act VIII · Ship it — LaTeX

**`export`** — convert Markdown to compilable `paper.tex` (+ `references.bib`).

| Flag | Takes | Meaning |
|---|---|---|
| `--title` | string | manuscript title (optional) |
| `--sections-json` | JSON string | inline list of `{title, draft}` |
| `--sections-file` | one file | same format, as a JSON file |
| `--markdown-file` | one file | a full Markdown manuscript to split and export |
| `--bibtex-file` | one file | BibTeX file to emit as `references.bib` |
| `--out-dir` | directory | persist `paper.tex` (+ `references.bib`) |
| `--json` | JSON object | merge payload keys (`title`, `sections`, `markdown`, `outline`, `bibtex`, `out_dir`) |
| `--out` | file path | save result |

Note: `export` has no `--format` flag.

```bash
uv run clio-author export --title "Demo Paper" \
  --sections-json '[{"title":"Introduction","draft":"We present **AUTHOR**."},{"title":"Method","draft":"It uses a multi-agent pipeline."}]' \
  --out-dir runbook-out/export-out
# from a whole manuscript file + a bib:
uv run clio-author export --title "AUTHOR" --markdown-file runbook-out/compose-out/paper.md \
  --bibtex-file runbook-out/cite-out/suggested.bib --out-dir runbook-out/export-out2
```

…or one shot — **`compose --latex`** writes Markdown *and* LaTeX:
```bash
CLIO_LLM=claude uv run clio-author compose \
  --idea "AUTHOR: cooperating agents for the paper lifecycle." \
  --latex --out-dir runbook-out/paper
```
**Artifacts:** `runbook-out/paper/{paper.md, sections/, paper.tex}`.

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

## The 5 run-only actions — payload key reference

These actions have no dedicated subcommand. Reach them with `clio-author run <action> --json '{...}'`.

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
  ingest → `paper.md`+`blocks.json`+`img/`; cite → `suggested.bib`; kg → `kg.json`+`kg.mmd`;
  compose → `paper.md`+`sections/`(+`paper.tex` with `--latex`); export → `paper.tex`+`references.bib`;
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

## Appendix A — all 19 actions at a glance

| # | Action | Dedicated subcommand |
|---|---|---|
| 1 | `ingest` | `clio-author ingest <source>` |
| 2 | `ask` | `clio-author ask` |
| 3 | `review` | `clio-author review` |
| 4 | `meta_review` | `clio-author run meta_review` |
| 5 | `rebuttal` | `clio-author rebuttal` |
| 6 | `cite` | `clio-author cite` |
| 7 | `write` | `clio-author write` |
| 8 | `edit` | `clio-author run edit` |
| 9 | `polish` | `clio-author polish` |
| 10 | `coherence` | `clio-author coherence` |
| 11 | `kg` | `clio-author kg` |
| 12 | `plan` | `clio-author plan` |
| 13 | `describe_figures` | `clio-author describe` |
| 14 | `plot` | `clio-author run plot` |
| 15 | `compose` | `clio-author compose` |
| 16 | `export` | `clio-author export` |
| 17 | `write_review` | `clio-author run write_review` |
| 18 | `figure_refine` | `clio-author run figure_refine` |
| 19 | `orchestrate` | `clio-author orchestrate` |

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
| plot / describe / figure_refine | figure prompts | `clio_author/experts/figure_agent.py` |
| compose | outline-gen prompt | `clio_author/experts/compose.py` |
| orchestrate | orchestrate prompt | `clio_author/experts/orchestrate.py` |
| cite | (deterministic verify) | `clio_author/retrieval/scholar.py` |
| export | (deterministic Markdown→LaTeX) | `clio_author/export/latex.py` |

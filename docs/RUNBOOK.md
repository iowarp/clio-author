# AUTHOR (clio-author) — CLI Runbook

A complete, copy-paste reference: **every subcommand, every flag, every setting.** Run the blocks
one at a time and inspect each result. Arranged as a paper's life — **read → understand → verify
sources → judge → write → refine → illustrate → ship.**

- Every command prints a JSON result on **stdout** (logs → stderr; add `2>/dev/null` for clean JSON).
  Exit code `0` = ok, `1` = error.
- **Every** subcommand accepts `--json '{...}'` (merge extra payload keys) and `--out FILE`
  (also save the result — prose for `.md`/`.txt`, full JSON for `.json`).
- Text actions need a model (`CLIO_LLM=…`); without one they return an offline **echo** placeholder.

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
| `CLIO_VISION` | **`off`** (`none`/`offline`/`disabled`) · `gemini`(`google`) | `describe`, `plot kind="diagram"` |
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
| `--json '{...}'` | merge a JSON object into the action payload (reach any payload key) |
| `--out FILE` | also write the result — prose `content` for `.md`/`.txt`, full JSON for `.json` |
| `-h` / `--help` | show that subcommand's exact flags |

## 3. Health check

```bash
uv run ruff check clio_author tests        # -> All checks passed!
uv run mypy clio_author                    # -> Success: no issues found in 55 source files
uv run pytest -q                           # -> 434 passed, 3 skipped, 10 deselected
uv run clio-author capabilities            # -> name=clio-author, version 0.3.0, 16 actions
```

> **13 subcommands** have dedicated flags: `capabilities, ingest, ask, review, cite, write, compose,
> export, polish, coherence, kg, describe, run`. The other **5 actions** (`edit`, `meta_review`,
> `plot`, `write_review`, `figure_refine`) have **no dedicated subcommand** — reach them with
> `clio-author run <action> --json '{...}'`. `run <action>` works for *any* of the 16 actions.

---

# The workflow — a paper's life

## Act I · Read → clean Markdown + memory blocks  *(run first; later acts reuse this)*

**`ingest`** — `clio-author ingest SOURCE [--json] [--out]`. SOURCE = arXiv id / arXiv-or-HTTP URL /
paper title / topic / local PDF path. Payload keys: `source`, `out_dir` (via `--json`). Needs `--extra pdf`.
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

**`ask`** — `clio-author ask --question Q [--blocks-json | --blocks-file] [--format] [--json] [--out]`.
Payload keys: `question`, `blocks`.
```bash
CLIO_LLM=claude uv run clio-author ask \
  --question "What problem does this paper solve?" \
  --blocks-file runbook-out/ingest/blocks.json \
  --format prose \
  --out runbook-out/answer.md
# inline blocks instead of a file: --blocks-json '{"sections":[...]}'
```

**`kg`** — `clio-author kg [--blocks-json | --blocks-file] [--format] [--json] [--out]`. Content
knowledge graph (claims/methods/datasets/results/metrics/concepts/tasks + relations). Payload keys:
`blocks`, `out_dir` (via `--json`).
```bash
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file runbook-out/ingest/blocks.json \
  --json '{"out_dir":"runbook-out/kg-out"}' \
  --format prose          # prose => content is a Mermaid graph
```
**Artifacts:** `runbook-out/kg-out/{kg.json, kg.mmd}`.

---

## Act III · Verify the scholarship

**`cite`** — `clio-author cite [--candidates-json | --candidates-file] [--format] [--json] [--out]`.
Verifies refs, emits **suggestions only**. Payload keys: `candidates`, `out_dir` (via `--json`).
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

**`review`** — `clio-author review [--paper | --paper-file] [--ground] [--format] [--json] [--out]`.
Payload keys: `paper`, `persona`, `ground`. Output: **decision = Accept | Reject**, **overall 1–10**,
**7 axes 1–4** (originality, quality, clarity, significance, soundness, presentation, contribution),
**confidence 1–5**, + summary/strengths/weaknesses/questions/limitations.
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
```
**Expect:** in (b) `metadata.decision` ∈ {Accept, Reject}, `metadata.overall` 1–10; (c) adds `metadata.related_work`.

**`meta_review`** *(run-only)* — aggregate reviews → one area-chair decision (offline). Payload key: `reviews`.
```bash
uv run clio-author run meta_review \
  --json '{"reviews":[{"Overall":7,"Decision":"Accept"},{"Overall":5,"Decision":"Reject"}]}'
```

**`coherence`** — `clio-author coherence [--sections-json | --sections-file | --markdown-file | --text] [--format] [--json] [--out]`.
Cross-section consistency (terminology, contradictions, undefined terms, duplication, flow). Payload keys: `sections`, `markdown`, `text`.
```bash
CLIO_LLM=claude uv run clio-author coherence \
  --sections-json '[{"title":"Introduction","draft":"X improves accuracy by 5%."},{"title":"Results","draft":"X achieves a 12% gain."}]' \
  --format prose
# or check a whole manuscript file: --markdown-file runbook-out/compose-out/paper.md
```

---

## Act V · Write a new paper

**`write`** — `clio-author write [--source | --source-file] [--outline] [--format] [--json] [--out]`.
Drafts one section, grounded in the source. Payload keys: `outline`, `section_plan`, `blocks`, `source`, `vision`, `out_path`.
```bash
CLIO_LLM=claude uv run clio-author write \
  --outline "Introduction" --source-file runbook-out/ingest/paper.md --format prose
```

**`write_review`** *(run-only)* — writer ↔ reviewer refine loop. Payload keys: `outline`, `section_plan`, `blocks`, `source`, `max_rounds`.
```bash
CLIO_LLM=claude uv run clio-author run write_review \
  --json '{"outline":{"title":"Introduction","goal":"introduce AUTHOR"},"source":"AUTHOR reads, reviews, and writes papers.","max_rounds":1}'
```

**`compose`** — the whole paper. Full flag set:
`--idea | --idea-file`, `--log | --log-file`, `--outline-json | --outline-file`, `--candidates-file`,
`--review`, `--max-rounds N`, `--out-dir DIR`, `--latex`, `--format`, `--json`, `--out`.
Payload keys: `idea`, `experimental_log`, `outline`, `candidates`, `blocks`, `review`, `max_rounds`, `out_dir`.
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

**`edit`** *(run-only)* — revise prose to address feedback (preserves citations). Payload keys: `draft`, `review`, `critic_notes`, `target`.
```bash
CLIO_LLM=claude uv run clio-author run edit \
  --json '{"draft":"We propose a system. It is good.","review":{"weaknesses":["no baseline comparison","unclear evaluation"]}}'
```

**`polish`** — `clio-author polish [--text | --text-file] [--voice V] [--target FILE] [--format] [--json] [--out]`.
Payload keys: `text`, `draft`, `voice`, `target`.
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

**`describe`** (action `describe_figures`) — `clio-author describe [--blocks-json | --blocks-file] [--format] [--json] [--out]`.
Caption figures (Gemini vision *looks at* the image when `CLIO_VISION=gemini`). Payload keys: `blocks`, `figures`, `context`.
```bash
CLIO_VISION=gemini uv run clio-author describe \
  --blocks-json '{"figures":[{"figure_id":1,"image_path":"'"$PWD"'/runbook-out/ingest/img/figure1.png"}]}' \
  --format prose
```
**Expect:** `vision_described:[1]` + a real description.

**`figure_refine`** *(run-only)* — visualizer ↔ critic loop. Payload keys: `spec`, `out_path`, `max_rounds`.
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

**`export`** — `clio-author export [--title T] [--sections-json | --sections-file | --markdown-file] [--bibtex-file F] [--out-dir DIR] [--json] [--out]`.
Markdown → compilable `paper.tex` (+ `references.bib`). Payload keys: `title`, `sections`, `markdown`, `outline`, `bibtex`, `out_dir`.
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

## 4. Where outputs go
- **stdout** always (the JSON result); **`--out FILE`** to also save it.
- **`out_dir` / `out_path`** (payload keys / `--out-dir`) persist structured artifacts:
  ingest → `paper.md`+`blocks.json`+`img/`; cite → `suggested.bib`; kg → `kg.json`+`kg.mmd`;
  compose → `paper.md`+`sections/`(+`paper.tex` with `--latex`); export → `paper.tex`+`references.bib`;
  write/plot/figure_refine → `out_path`.
- Print-only otherwise (ask, review, edit, polish, coherence, meta_review) — use `--out` to capture.

## 5. Tips
- Pretty-print JSON: `… 2>/dev/null | python3 -m json.tool`.
- Any action: `clio-author run <action> --json '{...}'` (the universal escape hatch).
- Big inputs → use the `--*-file` flags (inline JSON can exceed the shell arg limit).
- In-process: `from clio_author.integration.clio_adapter import ClioAuthorSubagent`;
  `ClioAuthorSubagent(llm=…).run("review", {"paper": "..."})`.
- See a subcommand's exact flags anytime: `clio-author <cmd> --help`.

## Appendix — each action's LLM prompt source (to read/tune)
| Action | Prompt constant | File |
|---|---|---|
| ask | `PAPER_QA_SYSTEM_PROMPT` | `clio_author/experts/paper_qa.py` |
| review | `REVIEWER_SYSTEM_PROMPT` | `clio_author/experts/reviewer.py` |
| meta_review | (deterministic, no prompt) | `clio_author/experts/meta_reviewer.py` |
| write / write_review | `WRITER_SYSTEM_PROMPT` | `clio_author/experts/writer.py`, `write_loop.py` |
| edit | `EDITOR_SYSTEM_PROMPT` | `clio_author/experts/editor.py` |
| polish | `POLISH_SYSTEM_PROMPT` | `clio_author/experts/polish.py` |
| coherence | `COHERENCE_SYSTEM_PROMPT` | `clio_author/experts/coherence.py` |
| kg | `KG_SYSTEM_PROMPT` + `KG_PROMPT` | `clio_author/experts/kg.py`, `clio_author/retrieval/kg.py` |
| plot / describe / figure_refine | figure prompts | `clio_author/experts/figure_agent.py` |
| compose | outline-gen prompt | `clio_author/experts/compose.py` |
| cite | (deterministic verify) | `clio_author/retrieval/scholar.py` |
| export | (deterministic Markdown→LaTeX) | `clio_author/export/latex.py` |

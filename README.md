# AUTHOR: Agentic Understanding for Thesis, Hypothesis, and Objective Research

AUTHOR turns a scientific paper — an **arXiv link, a PDF, or even just its title** — into clean
Markdown, then lets specialized AI agents **answer questions about it, check its citations, review
it, and help write, compose, export, and edit it**. It runs on its own, and a larger agent (such as
CLIO) can call it as a **subagent**.

> Runs **offline out of the box** with a built-in echo model (good for trying the plumbing). Add a
> real model (Claude / Codex / Ollama) for real answers. Requires **Python ≥ 3.12**. BSD-3-Clause.

## Why AUTHOR

Today these capabilities are scattered across **separate, non-interoperating tools**: a PDF parser
(Docling/MinerU), a literature-QA tool (PaperQA2/OpenScholar), a citation auditor (CiteCheck), a
writing agent (PaperOrchestra/AutoSurvey), a figure agent (PaperBanana), a LaTeX exporter. A 2024–2026
survey finds **no single system that unifies the whole paper lifecycle — ingest → understand → verify
citations → review → write → figures → export — as one grounded, host-invocable package.** That gap is
what AUTHOR fills: one package, grounded (verified citations, source-grounded writing), and callable by
a host agent. Full argument, capability matrix, and citations: **[`docs/MOTIVATION.md`](docs/MOTIVATION.md)**.

---

## 1. Quickstart — copy & paste, top to bottom

**Step 1. Install `uv`** (the only prerequisite — a fast Python runner). Skip if you have it.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Step 2. Get the code and install the core package.**

```bash
git clone https://github.com/SIslamMun/clio-author.git
cd clio-author
uv sync
```

**Step 3. Confirm it works** (prints the list of 26 things it can do — no model or network needed):

```bash
uv run clio-author capabilities
```

**Step 4. Turn a real paper into Markdown.** The `--extra pdf` flag adds the PDF/arXiv extractor for
this run. (The first ingest also downloads ~500 MB of extraction models; later runs are fast.)

```bash
uv run --extra pdf clio-author ingest 2601.23265
```

This creates a folder you can open and read:

```
clio-out/2601.23265/
├── paper.md          # the clean scientific Markdown
├── blocks.json       # structured sections / figures / equations
├── img/              # extracted figure images (figure1.png, …)
└── 2601.23265.pdf    # the downloaded source PDF
```

You can ingest other ways too:

```bash
uv run --extra pdf clio-author ingest "Attention Is All You Need"   # by paper title
uv run --extra pdf clio-author ingest ./mypaper.pdf                 # a local PDF file
```

**Step 5. Look at what you got.**

```bash
head -40 clio-out/2601.23265/paper.md
ls clio-out/2601.23265/img/
```

**Step 6. Get a real AI review** (this needs a real model — see [§3](#3-use-a-real-model); the
example uses the Claude CLI):

```bash
CLIO_LLM=claude uv run clio-author review \
  --paper-file clio-out/2601.23265/paper.md --format prose --out review.md
```

The `--out FILE` flag saves the result directly to a file in addition to printing JSON on stdout.
Use a `.md` or `.txt` extension to get the prose `content`; use `.json` to get the full JSON
result. This flag is available on every action — it is the convenient alternative to redirecting
stdout for the print-only actions (`ask`, `review`, `edit`, `polish`, `coherence`, `meta_review`)
that have no `out_dir`.

That is the whole loop: **ingest → read → review.** Everything below is variations on this.

---

## 2. Capabilities — 26 actions across the author lifecycle

AUTHOR is a **toolkit you reach into at different moments**, not a fixed pipeline. You wear two hats —
the **Writer** (producing your own paper) and the **Referee** (judging others') — and you can **enter
at any phase**: most jobs do *not* start with `ingest` (you can review pasted text, write from an
idea, polish a draft, or answer reviewers without processing a PDF). Find your phase, then jump to the
action. The full story + copy-paste recipes per phase live in **[`docs/LIFECYCLE.md`](docs/LIFECYCLE.md)**;
`clio-author lifecycle` prints this map, and every action in `clio-author capabilities` carries a
`phase` list and a `needs_source` flag.

| Phase | Your question | Actions |
|---|---|---|
| **① Frame** | *What's my story; what exists?* | `research`, `discover`, `ask`, `kg`, `experiment` |
| **② Gather** | *Pull in what I'll build on* | `ingest`, `gather`, `ask`, `kg`, `cite` |
| **③ Plan** | *Blueprint the paper + evaluation* | `plan`, `experiment`, `research` |
| **④ Draft** | *Write & illustrate* | `write`, `compose`, `plot`, `describe_figures`, `figure_refine` |
| **⑤ Strengthen** | *Make my own paper bulletproof* | `review`, `revise`, `coherence`, `verify_work`, `check_refs`, `cite`, `audit`, `section_review`, `write_review` |
| **⑥ Referee** | *Judge others' papers* | `review`, `section_review`, `meta_review` |
| **⑦ Respond** | *Answer my reviewers* | `rebuttal`, `revise`, `audit` |
| **⑧ Ship** | *Camera-ready* | `compose`, `export` |
| **⟳ Drive** | *Run a multi-step job for me* | `orchestrate` |

The per-action reference below is grouped by mechanism (most actions live in one phase; a few — like
`review`, `revise`, `experiment` — serve several). Add `--format prose` for human-readable text; omit
it for JSON (the default). Text actions need a real model (`CLIO_LLM=…`, see §3); `ingest`, `gather`,
`cite`, `discover`, `check_refs`, `audit`, and `meta_review` work without one.

> **Grounding shortcut — `--sources`.** Every writing/reading action that grounds on memory blocks
> (`ask`, `plan`, `write`, `compose`, `research`, `kg`, `review`, `experiment`) accepts `--sources` (and
> `--sources-file`): point it at any mix of files, folders, globs, git repo URLs, and PDFs/arXiv ids
> and they are auto-ingested and merged into the grounding context before the action runs — no
> separate `ingest`/`gather` step needed. Use the standalone `gather` action when you want to build
> and inspect that merged context once and reuse it.

---

### Read / process — turn a paper into usable data

Use this first. Every other workflow builds on the output.

#### `ingest` — convert a paper into Markdown + memory blocks

Accepts an arXiv id, URL, PDF path, or paper title. Writes `paper.md`, `blocks.json`, and extracted
figure images to an output directory.

| Argument | Meaning |
|---|---|
| `source` (positional) | arXiv id / URL / local PDF path / paper title |
| `--json '{"out_dir":"..."}'` | persist artifacts to a directory |
| `--out FILE` | save the result |

```bash
uv run --extra pdf clio-author ingest 2601.23265
uv run --extra pdf clio-author ingest "Attention Is All You Need"
uv run --extra pdf clio-author ingest ./mypaper.pdf
```

#### `gather` — ingest many sources into one merged context

Takes a whole working set — files, folders, globs, git repo URLs, PDFs/arXiv ids — ingests each, and
merges them into one `MemoryBlocks`. Writes `context.json` (a drop-in `--blocks-file` for the writing
actions) and `context.md`. Deterministic (no LLM). Directories/repos contribute their docs
(`.md`/`.rst`/`.txt`/`.tex` and `README`); an explicit file path of any text/code type is ingested
as given. PDFs/arXiv ids need the `pdf` extra. Per-source failures are reported in `skipped`, never
fatal.

| Argument | Meaning |
|---|---|
| `--sources S [S ...]` | one or more sources: file/folder/glob path, git repo URL, arXiv id, PDF URL/path |
| `--sources-file FILE` | file listing sources (one per line, or a JSON array of strings) |
| `--out-dir DIR` | persist `context.json` (drop-in `--blocks-file`) + `context.md` |
| `--max-files N` | cap on files pulled from folders/globs/repos in total (default 50) |
| `--max-text-chars N` | per-text-file character cap; longer files truncated (default 200000) |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys (`sources`, `out_dir`, `max_files`, `max_text_chars`) |
| `--out FILE` | save the result |

```bash
# Gather a repo's docs + a folder of notes + a paper into one reusable context:
uv run --extra pdf clio-author gather \
  --sources https://github.com/owner/repo ./notes/ 2601.23265 \
  --out-dir clio-out/context

# Then ground any writing action on it:
CLIO_LLM=claude uv run clio-author plan \
  --idea "my thesis" --blocks-file clio-out/context/context.json
```

---

### Understand — question-answer and concept mapping

Use after `ingest` to interrogate or map a paper's content.

#### `ask` — answer a question grounded in the paper's blocks

| Argument | Meaning |
|---|---|
| `--question TEXT` | the question to answer (required) |
| `--blocks-json JSON` | inline MemoryBlocks dump |
| `--blocks-file FILE` | path to `blocks.json` (preferred for real papers) |
| `--sources S [S ...]` | auto-gather files/folders/globs/git/PDFs into grounding blocks |
| `--sources-file FILE` | file listing sources (one per line, or a JSON array) |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge additional payload keys |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author ask \
  --question "What problem does this paper solve?" \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```

#### `kg` — extract a content knowledge graph

Extracts claims/methods/datasets/results and their relations. `--full` runs a 6-stage pipeline
(metadata → ontology → extraction → coref → verify → summary) with checkpoint/resume.

| Argument | Meaning |
|---|---|
| `--blocks-json JSON` | inline MemoryBlocks dump |
| `--blocks-file FILE` | path to `blocks.json` |
| `--full` | run the 6-stage pipeline |
| `--stages LIST` | restrict pipeline to named stages (e.g. `metadata,ontology`) |
| `--resume DIR` | resume from prior checkpoint directory |
| `--out-dir DIR` | persist `kg.json`, `kg.mmd`, and pipeline checkpoints |
| `--format structured\|prose` | `prose` emits a Mermaid `graph TD` rendering |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
# Single-shot extraction:
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file clio-out/2601.23265/blocks.json --format prose

# Full 6-stage pipeline with checkpoints:
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file clio-out/2601.23265/blocks.json \
  --full --out-dir clio-out/2601.23265/kg-pipeline

# Resume an interrupted pipeline run:
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file clio-out/2601.23265/blocks.json \
  --full --resume clio-out/2601.23265/kg-pipeline --out-dir clio-out/2601.23265/kg-pipeline
```

---

### Discover & verify sources — find and validate references

Use to build a real, grounded bibliography before writing.

#### `discover` — find real candidate papers via scholarly search *(no LLM)*

Queries Semantic Scholar → OpenAlex → Crossref → arXiv (the `auto` cascade) for a free-text topic
and returns the records it actually finds. Never fabricates records. Needs `CLIO_SCHOLAR` to be set
(default is `auto`). Writes `discovered.json` + `discovered.bib` when `--out-dir` is given.

| Argument | Meaning |
|---|---|
| `--query TEXT` | the topic/query to search (inline) |
| `--query-file FILE` | file holding the query text |
| `--limit N` | maximum papers to return (default 10) |
| `--cutoff-date YYYY-MM` | keep only papers before this date |
| `--out-dir DIR` | persist `discovered.json` + `discovered.bib` |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys (`query`, `topic`, `limit`, `cutoff_date`, `out_dir`) |
| `--out FILE` | save the result |

```bash
CLIO_SCHOLAR=auto uv run clio-author discover \
  --query "retrieval augmented generation" --limit 5 --out-dir clio-out/discovered
```

#### `cite` — verify citation candidates *(no LLM)*

Given a list of `{title, year?}` dicts, checks them against scholarly backends and returns BibTeX
suggestions. Never overwrites any file.

| Argument | Meaning |
|---|---|
| `--candidates-json JSON` | inline list of `{title, year?, reason?}` |
| `--candidates-file FILE` | same format as a JSON file |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys; use `{"out_dir":"..."}` to persist `suggested.bib` |
| `--out FILE` | save the result |

```bash
uv run --extra scholar clio-author cite \
  --candidates-json '[{"title":"Attention Is All You Need","year":2017}]'
```

#### `check_refs` — lint a BibTeX file against cited keys in prose *(no LLM)*

Flags malformed/duplicate entries, cited-but-missing keys, and uncited entries.

| Argument | Meaning |
|---|---|
| `--bibtex TEXT` | BibTeX bibliography (inline) |
| `--bibtex-file FILE` | path to a `.bib` file |
| `--markdown-file FILE` | Markdown manuscript to scan for `\cite{}` keys |
| `--text TEXT` | prose to scan for `\cite{}` keys (inline) |
| `--sections-json JSON` | list of `{title, draft}` to scan |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
uv run clio-author check-refs \
  --bibtex-file clio-out/mypaper/references.bib \
  --markdown-file clio-out/mypaper/paper.md
```

#### `research` — propose and verify sources for a topic

Produces a grounded literature brief (foundational, recent, competing sources, gaps, synthesis).
When `CLIO_SCHOLAR` is configured, each proposed title is verified against a real backend. Pass
`--json '{"discover":true}'` to seed the `recent` bucket from real discovered papers.

| Argument | Meaning |
|---|---|
| `--topic TEXT` | the topic to research (inline) |
| `--sources S [S ...]` | auto-gather files/folders/globs/git/PDFs into grounding blocks |
| `--sources-file FILE` | file listing sources (one per line, or a JSON array) |
| `--topic-file FILE` | file holding the topic text |
| `--blocks-file FILE` | JSON MemoryBlocks for grounding context |
| `--depth standard\|deep` | `deep` aims for more sources and precise gaps |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys; use `{"discover":true}` to seed from real search |
| `--out FILE` | save the result |

```bash
CLIO_SCHOLAR=auto CLIO_LLM=claude uv run clio-author research \
  --topic "transformer self-attention" --depth deep --format prose
```

---

### Review & assess — judge a paper or draft

> **Which check do I want?** These look similar but answer different questions:
> - **`review`** — LLM peer review of a whole paper (decision, scores, critique).
> - **`section_review`** — layered review of *one section* (it composes `check_refs` + `coherence` +
>   a persona review).
> - **`verify_work`** — does the prose actually *make and support* the claims it planned to? (LLM,
>   goal-backward).
> - **`check_refs`** — deterministic bibliography lint + in-text `\cite{}` cross-check (no LLM).
> - **`audit`** — deterministic manuscript completeness: required sections, word budgets, unresolved
>   `[TODO]`/`[CITE:]` placeholders (no LLM).
> - **`coherence`** — cross-section consistency: terminology drift, contradictions, broken flow.

#### `review` — produce a structured peer review

Outputs Accept/Reject decision, 1–10 overall, 7 per-axis scores, and a full critique. Add
`--ground` to cite real related work. Add `--figures-json`/`--figures-file` with `CLIO_VISION=gemini`
for a multimodal review.

| Argument | Meaning |
|---|---|
| `--paper TEXT` | paper Markdown text (inline) |
| `--paper-file FILE` | path to a paper Markdown file |
| `--ground` | retrieve related prior work and ground the review in it |
| `--figures-json JSON` | list of `[{figure_id?, image_path, caption?}]` to look at |
| `--figures-file FILE` | same format as a JSON file |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys; `{"persona":{"label":"..."}}` sets reviewer persona |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author review \
  --paper-file clio-out/2601.23265/paper.md --format prose --out review.md
```

#### `meta_review` — aggregate reviews into an area-chair decision *(no LLM)*

Reached via the `run` escape hatch (no dedicated subcommand). Payload: `reviews` (list of review
dicts).

```bash
uv run clio-author run meta_review \
  --json '{"reviews":[{"Overall":7,"Decision":"Accept"},{"Overall":5,"Decision":"Reject"}]}'
```

#### `section_review` — three-layer review of a single section

L1 reference check → L2 coherence → L3 persona peer review, with a deterministic severity summary.

| Argument | Meaning |
|---|---|
| `--text TEXT` | section text (inline) |
| `--text-file FILE` | file holding the section text |
| `--bibtex-file FILE` | BibTeX file for the L1 reference check |
| `--persona-json JSON` | a `PersonaSpec` for the L3 reviewer (e.g. `{"label":"harsh reviewer"}`) |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author section-review \
  --text-file clio-out/mypaper/sections/01-introduction.md \
  --bibtex-file clio-out/mypaper/references.bib --format prose
```

#### `rebuttal` — draft an author rebuttal point by point

Addresses each weakness and question strictly from the paper, inventing nothing.

| Argument | Meaning |
|---|---|
| `--paper TEXT` | paper Markdown text (inline) |
| `--paper-file FILE` | path to a paper Markdown file |
| `--review-json JSON` | a `PaperReview` dump or `{weaknesses:[...],questions:[...]}` (inline) |
| `--review-file FILE` | path to a JSON `PaperReview` file |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author rebuttal \
  --paper-file clio-out/2601.23265/paper.md \
  --review-json '{"weaknesses":["no baseline comparison"],"questions":["how is X measured?"]}' \
  --format prose
```

#### `verify_work` — goal-backward claim check

Checks whether each intended claim is actually made and supported in a written section.

| Argument | Meaning |
|---|---|
| `--text TEXT` | written prose to verify (inline) |
| `--text-file FILE` | file holding the written prose |
| `--section-plan-json JSON` | a `SectionPlan` whose `claims` to verify (inline) |
| `--section-plan-file FILE` | path to a JSON `SectionPlan` file |
| `--claims-json JSON` | explicit list of claim strings (inline) |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author verify-work \
  --text-file clio-out/mypaper/sections/01-introduction.md \
  --claims-json '["AUTHOR unifies ingestion, review, and writing"]' --format prose
```

#### `audit` — deterministic manuscript completeness checklist *(no LLM)*

Checks required sections present, word counts vs budgets, unresolved `[TODO]`/`[CITE:]` placeholders,
and citation coverage.

| Argument | Meaning |
|---|---|
| `--sections-json JSON` | inline list of `{title, draft, word_budget?}` |
| `--sections-file FILE` | same format as a JSON file |
| `--markdown-file FILE` | full Markdown manuscript to split and audit |
| `--bibtex-file FILE` | BibTeX file for citation-coverage checking |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys; use `{"outline":{...}}` for required-section check |
| `--out FILE` | save the result |

```bash
uv run clio-author audit \
  --markdown-file clio-out/mypaper/paper.md \
  --bibtex-file clio-out/mypaper/references.bib
```

---

### Write & compose — draft and refine text

#### `plan` — turn an idea into per-section writing plans

Produces tasks, claims, sources, and word budgets for each section before any prose is written.

| Argument | Meaning |
|---|---|
| `--idea TEXT` | research idea / thesis (inline) |
| `--idea-file FILE` | file holding the idea text |
| `--log TEXT` | experimental log / results notes (inline) |
| `--log-file FILE` | file holding the experimental log |
| `--outline-json JSON` | a `PaperOutline` to plan against |
| `--outline-file FILE` | same format as a JSON file |
| `--blocks-file FILE` | JSON MemoryBlocks for grounding |
| `--sources S [S ...]` | auto-gather files/folders/globs/git/PDFs into grounding blocks |
| `--sources-file FILE` | file listing sources (one per line, or a JSON array) |
| `--candidates-file FILE` | JSON citation candidates to fold into citation hints |
| `--out-dir DIR` | persist `plan.json` |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author plan \
  --idea "Propose a new attention mechanism for long-range dependencies." \
  --outline-json '{"title":"Attention++","sections":[{"title":"Introduction","goal":"Motivate the problem."}]}' \
  --out-dir clio-out/mypaper
```

#### `experiment` — recreate an evaluation plan from reference papers

Reads the **design / architecture / experiments** of one or more reference papers (PDFs are
auto-ingested; or pass `--sources`/`--blocks-file`/`--markdown-file`) and extracts each paper's
empirical design (research questions, architecture, datasets, baselines, metrics, ablations,
protocol, compute, limitations). When you also give your **new paper's `--idea`**, it *recreates* a
grounded **evaluation plan** — which datasets to use, baselines to compare against, metrics to
report, ablations to run, the protocol, and threats to validity — each recommendation tagged with the
reference paper it came from. Writes `experiment_designs.json/.md` and (with an idea)
`evaluation_plan.json/.md` (a drop-in evaluation section).

| Argument | Meaning |
|---|---|
| `--sources S [S ...]` | reference papers/folders/globs/git/PDFs (auto-ingested; multi-paper) |
| `--sources-file FILE` | file listing sources (one per line, or a JSON array) |
| `--blocks-file FILE` | a pre-ingested/`gather`ed MemoryBlocks JSON of the reference paper(s) |
| `--blocks-json JSON` | inline MemoryBlocks dump |
| `--markdown-file FILE` | a single reference paper's Markdown (alternative to blocks) |
| `--text TEXT` | a single reference paper's text inline |
| `--idea TEXT` / `--idea-file FILE` | the **new** paper's idea — supplying it recreates the eval plan |
| `--out-dir DIR` | persist `experiment_designs.*` + `evaluation_plan.*` |
| `--format structured\|prose` | `prose` prints the rendered evaluation plan |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
# Read two reference papers and recreate an evaluation plan for a new idea:
CLIO_LLM=claude uv run --extra pdf clio-author experiment \
  --sources 2106.09685 ./related/fastcache.pdf \
  --idea "An RL cache-eviction policy for scientific data workloads" \
  --out-dir clio-out/eval --format prose
```

#### `write` — draft one section from source material

| Argument | Meaning |
|---|---|
| `--source TEXT` | source material (inline) |
| `--source-file FILE` | source-material file (single file only) |
| `--sources S [S ...]` | auto-gather files/folders/globs/git/PDFs into grounding blocks |
| `--sources-file FILE` | file listing sources (one per line, or a JSON array) |
| `--outline TEXT` | section title; richer outlines via `--json '{"outline":{...}}'` |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys; use for `section_plan`, `blocks`, `out_path` |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author write \
  --outline "Introduction" --source-file clio-out/2601.23265/paper.md --format prose
```

#### `revise` — revise existing prose (feedback or style)

One revision action with two modes. `--mode feedback` (default) addresses reviewer critique and may
change content; `--mode style` polishes clarity, flow, and academic voice while preserving meaning
and `\cite{}` placeholders. (This subsumes the older `edit` and `polish` actions, which remain as
back-compatible aliases — `edit` ≡ `revise --mode feedback`, `polish` ≡ `revise --mode style`.)

| Argument | Meaning |
|---|---|
| `--mode feedback\|style` | `feedback` = address review (may change content); `style` = polish voice |
| `--text TEXT` / `--text-file FILE` | the prose to revise |
| `--review-json JSON` / `--review-file FILE` | reviewer feedback to address (feedback mode) |
| `--critic-notes TEXT` | free-form directive feedback (feedback mode) |
| `--voice TEXT` | target voice, e.g. `concise` or `formal` (style mode) |
| `--target FILE` | file (under harness root) to apply the revision to |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
# Style polish:
CLIO_LLM=claude uv run clio-author revise --mode style \
  --text-file clio-out/mypaper/sections/01-introduction.md --voice concise --format prose

# Feedback-driven revision:
CLIO_LLM=claude uv run clio-author revise \
  --text "We propose a system." --review-json '{"weaknesses":["no baseline comparison"]}'
```

#### `coherence` — check cross-section consistency

Finds terminology drift, contradictions, undefined terms, and broken flow.

| Argument | Meaning |
|---|---|
| `--sections-json JSON` | inline list of `{title, draft}` |
| `--sections-file FILE` | same format as a JSON file |
| `--markdown-file FILE` | full Markdown manuscript to split |
| `--text TEXT` | single passage (inline fallback) |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author coherence \
  --markdown-file clio-out/mypaper/paper.md --format prose
```

#### `compose` — draft a whole paper from an idea

One call: idea → outline → cite → (plan) → write each section → (review) → assemble. Use `--latex`
to also emit `paper.tex`; add `--pdf` to compile `paper.pdf` (requires a LaTeX engine).

| Argument | Meaning |
|---|---|
| `--idea TEXT` | research idea / thesis (inline) |
| `--idea-file FILE` | file holding the idea text |
| `--log TEXT` | experimental log / results notes (inline) |
| `--log-file FILE` | file holding the experimental log |
| `--outline-json JSON` | a `PaperOutline` to use instead of generating one |
| `--outline-file FILE` | same format as a JSON file |
| `--sources S [S ...]` | auto-gather files/folders/globs/git/PDFs into grounding blocks |
| `--sources-file FILE` | file listing sources (one per line, or a JSON array) |
| `--candidates-file FILE` | JSON citation candidates to verify and cite |
| `--review` | run a per-section writer/reviewer refine loop |
| `--max-rounds N` | max refine rounds per section when `--review` is set (default 3) |
| `--out-dir DIR` | persist `paper.md` + per-section files |
| `--latex` | also export `paper.tex` (+ `references.bib`) |
| `--pdf` | compile `paper.pdf` from the LaTeX (implies `--latex`; needs a LaTeX engine) |
| `--plan` | plan each section before drafting |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
# Draft and export to LaTeX + PDF in one call:
CLIO_LLM=claude uv run clio-author compose \
  --idea "Propose a new attention mechanism for long-range dependencies." \
  --log "Ran experiments on WikiText-103; BLEU +2.1 over baseline." \
  --review --out-dir clio-out/mypaper --latex --pdf
```

After `compose`, the output directory contains:

```
clio-out/mypaper/
├── paper.md               # assembled Markdown manuscript
├── paper.tex              # (with --latex) standalone LaTeX document
├── references.bib         # (with --latex and citations) BibTeX entries
├── paper.pdf              # (with --pdf and a LaTeX engine) compiled PDF
└── sections/
    ├── 01-introduction.md
    ├── 02-methods.md
    └── …
```

#### `write_review` — writer ↔ reviewer critic-refine loop

Reached via the `run` escape hatch. Payload: `outline`, `section_plan`, `blocks`, `source`,
`max_rounds`.

```bash
CLIO_LLM=claude uv run clio-author run write_review \
  --json '{"outline":{"title":"Introduction","goal":"introduce AUTHOR"},"source":"...","max_rounds":1}'
```

---

### Illustrate (figures) — generate and describe figures

#### `plot` — generate matplotlib code or a diagram image

Reached via the `run` escape hatch. With `CLIO_VISION=gemini` and `spec.kind="diagram"`, generates
a real PNG instead of code. Payload: `spec`, `out_path`.

```bash
CLIO_LLM=claude uv run clio-author run plot \
  --json '{"spec":{"kind":"plot","intent":"training loss vs epoch"}}'
```

#### `describe` (action: `describe_figures`) — caption figures from blocks

With `CLIO_VISION=gemini`, looks at actual figure images.

| Argument | Meaning |
|---|---|
| `--blocks-json JSON` | inline MemoryBlocks dump |
| `--blocks-file FILE` | path to `blocks.json` |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author describe \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```

#### `figure_refine` — figure visualizer ↔ critic refine loop

Reached via the `run` escape hatch. Payload: `spec`, `out_path`, `max_rounds`.

```bash
CLIO_LLM=claude uv run clio-author run figure_refine \
  --json '{"spec":{"kind":"plot","intent":"line chart of loss vs epochs"},"max_rounds":1}'
```

---

### Export & ship — produce LaTeX and PDF

#### `export` — convert Markdown to compilable LaTeX

Converts a `paper.md` or sections list into `paper.tex` + `references.bib`. Add `--pdf` to also
compile `paper.pdf` (needs `--out-dir` and a LaTeX engine: tectonic, latexmk, or pdflatex; never
fails the export if compilation fails).

| Argument | Meaning |
|---|---|
| `--title TEXT` | manuscript title (optional) |
| `--sections-json JSON` | inline list of `{title, draft}` |
| `--sections-file FILE` | same format as a JSON file |
| `--markdown-file FILE` | full Markdown manuscript to split and export |
| `--bibtex-file FILE` | BibTeX file to emit as `references.bib` |
| `--out-dir DIR` | persist `paper.tex` (+ `references.bib`, + `paper.pdf` with `--pdf`) |
| `--pdf` | compile `paper.pdf` (needs `--out-dir` and a LaTeX engine) |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

Note: `export` has no `--format` flag.

```bash
# Export Markdown to LaTeX and compile PDF:
uv run clio-author export \
  --markdown-file clio-out/mypaper/paper.md \
  --bibtex-file clio-out/mypaper/references.bib \
  --out-dir clio-out/mypaper --pdf
```

`compose --latex` / `compose --pdf` produce both Markdown and LaTeX in one pipeline call:

```bash
CLIO_LLM=claude uv run clio-author compose \
  --idea-file idea.txt --log-file log.txt \
  --candidates-file refs.json \
  --review --out-dir clio-out/mypaper --latex --pdf
```

---

### Drive (orchestration) — hand it a goal

#### `orchestrate` — plan and run a sequence of actions from a natural-language goal

| Argument | Meaning |
|---|---|
| `--goal TEXT` | the goal to achieve (inline) |
| `--goal-file FILE` | file holding the goal text |
| `--inputs-json JSON` | named inputs dict (inline), e.g. `{"source":"2601.23265"}` |
| `--inputs-file FILE` | same format as a JSON file |
| `--max-steps N` | maximum planned steps to execute (default 6) |
| `--out-dir DIR` | persist `orchestrate.json` |
| `--format structured\|prose` | default `structured` |
| `--json '{...}'` | merge payload keys |
| `--out FILE` | save the result |

```bash
CLIO_LLM=claude uv run clio-author orchestrate \
  --goal "Ingest 2601.23265 then produce a peer review." \
  --inputs-json '{"source":"2601.23265"}' --max-steps 4 --out-dir clio-out/orchestrate
```

---

**Single-file rule.** Every `--*-file` flag reads exactly **one** file. To supply several files as
context, concatenate them first or `ingest` each one and pass the resulting `blocks.json`.

**Saving results to a file.** Every action accepts `--out FILE`. A `.json` extension saves the
full indented JSON result; any other extension (`.md`, `.txt`, …) saves the prose `content` when
present, otherwise the full JSON. On success, `[saved to FILE]` is printed to stderr so stdout
stays clean JSON.

**Run-only actions.** `edit`, `meta_review`, `plot`, `write_review`, and `figure_refine` have no
dedicated subcommand; reach them with `clio-author run <action> --json '{...}'`.

The complete payload reference for every action is in [`docs/USAGE.md`](docs/USAGE.md).

---

## 3. Use a real model

By default clio-author uses an **offline echo model**, so `review`/`ask`/`write`/`compose` return a
placeholder instead of real text. Pick a real one with the `CLIO_LLM` environment variable:

| `CLIO_LLM` | What it uses | How to get it |
|---|---|---|
| `echo` *(default)* | nothing — offline placeholder | already works |
| `claude` | the `claude` CLI (no API key) | install Claude Code so `claude` is on your PATH |
| `codex` | the `codex` CLI | install the Codex CLI |
| `ollama` | a local model server | install [Ollama](https://ollama.com), then `ollama pull llama3.1:8b` |

```bash
CLIO_LLM=claude uv run clio-author review --paper-file clio-out/2601.23265/paper.md --format prose
CLIO_LLM=ollama CLIO_LLM_MODEL=llama3.1:8b uv run clio-author ask \
  --question "..." --blocks-file clio-out/2601.23265/blocks.json
```

Other useful variables:

| Variable | Purpose | Default |
|---|---|---|
| `CLIO_LLM_MODEL` | Override the model name for the selected provider | provider default |
| `CLIO_OLLAMA_URL` | Ollama server address | `http://localhost:11434` |
| `CLIO_VISION` | Gemini vision for `describe_figures`, `review` (with figures), and diagram generation | `off` |
| `CLIO_VISION_MODEL` | Gemini describe model | `gemini-2.5-flash` |
| `CLIO_IMAGE_MODEL` | Gemini image generation model | `gemini-2.5-flash-image` |

### Citation backends (`CLIO_SCHOLAR`)

| `CLIO_SCHOLAR` | What it uses |
|---|---|
| `auto` *(default)* | cascade: Semantic Scholar → OpenAlex → Crossref → arXiv |
| `semantic` / `s2` | Semantic Scholar only; set `SEMANTIC_SCHOLAR_API_KEY` to avoid rate limits |
| `openalex` | OpenAlex only; no key required |
| `crossref` | Crossref only; no key required |
| `arxiv` | arXiv only; no key required, preprint-focused |
| `off` / `none` / `offline` | disable citation lookup |

For polite no-key usage, set `OPENALEX_MAILTO` and/or `CROSSREF_MAILTO` to an email address.

`CLIO_SCHOLAR` is used by `cite`, `discover`, `review --ground`, and `research` (when scholar
grounding or `discover` seeding is enabled).

### Gemini vision (`CLIO_VISION=gemini`)

When `CLIO_VISION=gemini` is set and a `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is in the
environment, `describe_figures` *looks at* real figure images using the Gemini REST API, and `plot`
with `spec.kind="diagram"` generates a real image PNG instead of matplotlib code. Without this,
both actions use the hermetic text/code path and no image API is ever called.

```bash
CLIO_VISION=gemini GEMINI_API_KEY=... uv run clio-author describe \
  --blocks-file clio-out/2601.23265/blocks.json
```

### Keeping secrets local

Keep secrets in a local ignored env file instead of pasting them into commands:

```bash
cp .env.local.example .env.local
chmod 600 .env.local
```

Then edit `.env.local` with your keys. `uv run clio-author ...` loads it automatically. Use
`CLIO_ENV_FILE=/path/to/file` if you want a different file. Never paste API keys into chat, issues,
PRs, or commands; rotate any key that was exposed. See [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 4. Use it as a subagent (from another program)

clio-author is meant to be **called by a host agent**. Two ways:

### A. In-process (Python) — recommended

Save this as `use_clio.py` and run it with `uv run python use_clio.py`:

```python
from clio_author.integration.clio_adapter import ClioAuthorSubagent
from clio_author.llm.providers import resolve_llm

# Build the subagent. resolve_llm("claude") | "codex" | "ollama" | None (offline echo).
sub = ClioAuthorSubagent(llm=resolve_llm("claude"))

# 1) Discover what it can do (26 actions).
for a in sub.capabilities()["actions"]:
    print(a["action"], "—", a["description"])

# 2) Ingest a paper (needs the `pdf` extra: uv sync --extra pdf).
ingested = sub.run("ingest", {"source": "2601.23265", "out_dir": "clio-out/demo"})
blocks = ingested["structured"]              # the memory blocks
print("wrote:", ingested["metadata"]["wrote"])

# 3) Ask a grounded question.
answer = sub.run("ask", {"question": "What is the main contribution?", "blocks": blocks})
print(answer["content"])

# 4) Review the paper.
review = sub.run("review", {"paper": ingested["content"]})
print(review["metadata"].get("decision"), review["structured"])

# 5) Discover candidate papers for a topic (needs CLIO_SCHOLAR configured).
discovered = sub.run("discover", {"query": "retrieval augmented generation", "limit": 5})
print(discovered["metadata"]["count"], "papers found")

# 6) Draft a whole paper from an idea.
result = sub.run("compose", {
    "idea": "Propose a new attention mechanism for long-range dependencies.",
    "experimental_log": "Ran experiments on WikiText-103; BLEU +2.1 over baseline.",
    "review": True,
    "out_dir": "clio-out/mypaper",
    "latex": True,
})
print("sections:", result["metadata"]["num_sections"])
print("wrote:", result["metadata"]["wrote"])
```

Every `sub.run(action, payload)` returns a JSON-serializable dict
`{"action", "content", "structured", "metadata"}` and **never raises** — failures show up in
`result["metadata"]["error"]` (or a top-level `"error"`). The adapter imports nothing from the host,
so the coupling is one-directional.

### B. As a subprocess (any language)

Call the CLI and read JSON from stdout (exit code `0` = ok, `1` = error):

```bash
CLIO_LLM=claude uv run clio-author review --paper-file clio-out/2601.23265/paper.md
# -> {"action": "review", "content": "...", "structured": {...}, "metadata": {...}}
```

---

## 5. The 26 actions at a glance

| # | Action | What it's for | Subcommand |
|---|--------|---------------|------------|
| 1 | `ingest` | **Read a paper.** arXiv id / URL / PDF / title → Markdown + blocks + figures. | `clio-author ingest <source>` |
| 2 | `gather` | **Build context.** Many sources (files/folders/globs/git/PDFs) → one merged `context.json`. | `clio-author gather` |
| 3 | `ask` | **Question answering.** Grounded answer from the paper's memory blocks. | `clio-author ask` |
| 4 | `kg` | **Map content.** Claims/methods/datasets/results graph; `--full` for the 6-stage pipeline. | `clio-author kg` |
| 5 | `discover` | **Find real papers.** Scholarly search (S2/OpenAlex/Crossref/arXiv); no LLM. | `clio-author discover` |
| 6 | `cite` | **Verify citations.** Check candidates against scholarly backends; suggestions only. | `clio-author cite` |
| 7 | `check_refs` | **Lint bibliography.** Malformed/duplicate entries, missing/uncited keys; no LLM. | `clio-author check-refs` |
| 8 | `research` | **Survey literature.** Foundational/recent/competing sources, gaps, synthesis. | `clio-author research` |
| 9 | `review` | **Peer review.** Accept/Reject + scores + critique; optional grounding and vision. | `clio-author review` |
| 10 | `meta_review` | **Area-chair decision.** Aggregate several reviews; offline arithmetic. | `clio-author run meta_review` |
| 11 | `section_review` | **Section review.** L1 refs → L2 coherence → L3 persona; severity summary. | `clio-author section-review` |
| 12 | `rebuttal` | **Author rebuttal.** Point-by-point response grounded in the paper. | `clio-author rebuttal` |
| 13 | `verify_work` | **Claim audit.** Per-claim made/supported check → VERIFIED/GAPS verdict. | `clio-author verify-work` |
| 14 | `audit` | **Manuscript checklist.** Sections, word counts, placeholders, coverage; no LLM. | `clio-author audit` |
| 15 | `plan` | **Section blueprints.** Tasks, claims, sources, word budgets before drafting. | `clio-author plan` |
| 16 | `experiment` | **Recreate evaluation.** Extract reference papers' design/experiments → grounded eval plan (datasets/baselines/metrics/ablations). | `clio-author experiment` |
| 17 | `write` | **Draft a section.** Grounded in supplied source material. | `clio-author write` |
| 18 | `revise` | **Revise prose.** `--mode feedback` (address review) or `style` (polish voice). Aliases: `edit`, `polish`. | `clio-author revise` |
| 19 | `coherence` | **Consistency check.** Terminology drift, contradictions, broken flow. | `clio-author coherence` |
| 20 | `compose` | **Write a whole paper.** idea → outline → cite → write → assemble; `--latex`/`--pdf`. | `clio-author compose` |
| 21 | `write_review` | **Self-improve a draft.** Writer ↔ reviewer critic-refine loop. | `clio-author run write_review` |
| 22 | `plot` | **Make a plot/diagram.** Matplotlib code (or real PNG with vision). | `clio-author run plot` |
| 23 | `describe_figures` | **Caption figures.** Text or Gemini vision descriptions. | `clio-author describe` |
| 24 | `figure_refine` | **Self-improve a figure.** Visualizer ↔ critic refine loop. | `clio-author run figure_refine` |
| 25 | `export` | **Ship LaTeX.** `paper.md` → `paper.tex` + `references.bib`; `--pdf` compiles PDF. | `clio-author export` |
| 26 | `orchestrate` | **Goal-driven.** Plan and run a sequence of actions from a natural-language goal. | `clio-author orchestrate` |

Actions without a dedicated subcommand are reachable via `clio-author run <action> --json '...'`.

---

## 6. Optional extras (install only what you need)

The core install is tiny and offline. Each heavy capability is opt-in:

```bash
uv sync --extra pdf        # real PDF/arXiv extraction (Docling + PyMuPDF) — needed for `ingest`
uv sync --extra rag        # real semantic search for `ask` (sentence-transformers + LanceDB)
uv sync --extra scholar    # live Semantic Scholar for `cite` (httpx + thefuzz)
uv sync --extra viz        # actually render plot images (matplotlib)
uv sync --extra mcp        # the MCP bridge so MCP-only hosts (e.g. CLIO) can invoke it (fastmcp)
uv sync --all-extras       # everything at once
```

`torch` is pinned to the CPU build, so `uv sync --all-extras` resolves cleanly. (GPU users: see the
`[tool.uv.index]` note in `pyproject.toml`.)

---

## 7. Test it

```bash
uv run pytest                        # the offline test suite (no network, no model downloads)
uv run pytest -m live                # real-backend tests (need the extras + network)
uv run python scripts/real_test.py   # full real end-to-end run; set CLIO_TEST_LLM=claude|codex|ollama
```

---

## 8. Troubleshooting

- **`clio-author: command not found`** — it lives in the project's venv; always call it as
  `uv run clio-author …` (or `source .venv/bin/activate` first).
- **`ingest` says a dependency is missing** — run `uv sync --extra pdf`.
- **First `ingest` is slow** — Docling downloads ~500 MB of models once; subsequent runs are fast.
- **`review`/`ask`/`write`/`compose` output looks like a placeholder** — you're on the default echo
  model; set `CLIO_LLM=claude` (or `codex`/`ollama`).
- **`cite` or `discover` returns nothing** — try `CLIO_SCHOLAR=openalex` or `CLIO_SCHOLAR=arxiv`;
  for Semantic Scholar specifically, set `SEMANTIC_SCHOLAR_API_KEY` to reduce rate limits.
- **`torchvision::nms` error after installing `rag`/`pdf`** — reinstall the matching CPU wheel:
  `uv pip install --reinstall torchvision --index-url https://download.pytorch.org/whl/cpu`.
- **`compose` / `export` produce no `.tex` file** — `--latex` requires `--out-dir` to be set so a
  `SafeFiles` can be rooted there; or use `export --markdown-file` to convert an existing `paper.md`.
- **`--pdf` reports a `pdf_error`** — no LaTeX engine (tectonic, latexmk, or pdflatex) was found on
  the PATH. The export still succeeds; install one of those tools to compile PDF.
- **A host invoking AUTHOR hangs** — don't point AUTHOR's nested model at the *same* host (e.g.
  `CLIO_LLM=codex` while the host is Codex) — it recurses. For grounding inside a host, prefer a
  no-LLM action like `cite` or `discover`, or set the nested `CLIO_LLM` to a different provider.

---

## More

- **Why AUTHOR — motivation, the gap, capability matrix** → [`docs/MOTIVATION.md`](docs/MOTIVATION.md)
- **What AUTHOR took from each source project (have / partial / missing)** → [`docs/SOURCE-COVERAGE.md`](docs/SOURCE-COVERAGE.md)
- **Full action & payload reference, providers, output details** → [`docs/USAGE.md`](docs/USAGE.md)
- **Copy-paste runbook (every command, every flag)** → [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- **Invoking AUTHOR as a subagent (in-process / CLI / MCP)** → [`docs/INTEGRATION.md`](docs/INTEGRATION.md)
- **Evaluation plan vs. the reference systems** → [`docs/BENCHMARK-PLAN.md`](docs/BENCHMARK-PLAN.md)
- **With-vs-without comparison across hosts** → [`docs/ABLATION.md`](docs/ABLATION.md) · agentic test in [`eval/agentic/`](eval/agentic/)
- **API keys and local env-file handling** → [`docs/SECURITY.md`](docs/SECURITY.md)
- **Design and architecture** → [`artifact/notes/DESIGN.md`](artifact/notes/DESIGN.md)
- **Presentation** → [`docs/AUTHOR.pdf`](docs/AUTHOR.pdf) / [`docs/AUTHOR.pptx`](docs/AUTHOR.pptx)
- **Working in this repo (for agents/contributors)** → [`AGENTS.md`](AGENTS.md)
- **Changes** → [`CHANGELOG.md`](CHANGELOG.md)

## License

BSD-3-Clause. Adapts MIT / Apache-2.0 sources with attribution (see module headers); no AGPL code.

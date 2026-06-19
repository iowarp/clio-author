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

**Step 3. Confirm it works** (prints the list of 19 things it can do — no model or network needed):

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

## 2. Every command, with a real example

Run any of these after Step 4 above. Add `--format prose` for human-readable text; omit it to get
JSON (the default, handy for programs). Anything that produces text needs a real model
(`CLIO_LLM=…`, see §3); `ingest`, `cite`, and `meta_review` work without one.

### Processing

```bash
# Convert a paper to Markdown + memory blocks (arXiv id | URL | title | topic | local PDF):
uv run --extra pdf clio-author ingest 2601.23265
```

### Question answering

```bash
# Ask a question, grounded in that paper's blocks:
CLIO_LLM=claude uv run clio-author ask \
  --question "What problem does this paper solve?" \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```

### Citation verification

```bash
# Verify citations against Semantic Scholar + fallback backends (suggestions only):
uv run --extra scholar clio-author cite \
  --candidates-json '[{"title": "Attention Is All You Need", "year": 2017}]'
```

### Content knowledge graph

```bash
# Extract a content knowledge graph (claims/methods/datasets/results + relations)
# from a paper's memory blocks (distinct from a citation graph).
uv run clio-author kg --blocks-file clio-out/<id>/blocks.json

# Add --format prose to print a Mermaid `graph TD` rendering for a human view.
```

### Review

```bash
# Peer-review a paper (structured JSON, or --format prose):
CLIO_LLM=claude uv run clio-author review \
  --paper-file clio-out/2601.23265/paper.md --format prose

# Multimodal review — reviewer also looks at figures (needs CLIO_VISION=gemini):
CLIO_VISION=gemini GEMINI_API_KEY=... CLIO_LLM=claude uv run clio-author review \
  --paper-file clio-out/2601.23265/paper.md \
  --figures-json '[{"figure_id":1,"image_path":"clio-out/2601.23265/img/figure1.png","caption":"Overview diagram"}]' \
  --format prose

# Draft an author rebuttal to a review, point by point:
CLIO_LLM=claude uv run clio-author rebuttal \
  --paper-file clio-out/2601.23265/paper.md \
  --review-json '{"weaknesses":["no baseline comparison"],"questions":["how is X measured?"]}' \
  --format prose

# Aggregate several reviews into a single meta-review (no model needed):
uv run clio-author run meta_review \
  --json '{"reviews": [{"Overall": 7, "Decision": "Accept"}, {"Overall": 5, "Decision": "Reject"}]}'
```

### Writing, composing, and exporting

```bash
# Turn an idea into per-section writing plans (tasks, claims, sources, word budgets):
CLIO_LLM=claude uv run clio-author plan \
  --idea "Propose a new attention mechanism for long-range dependencies." \
  --outline-json '{"title":"Attention++","sections":[{"title":"Introduction","goal":"Motivate the problem."}]}' \
  --out-dir clio-out/mypaper

# Draft one section from an outline + source material:
CLIO_LLM=claude uv run clio-author write \
  --outline "Introduction" --source-file clio-out/2601.23265/paper.md --format prose

# Polish a draft for clarity, flow, and academic voice:
CLIO_LLM=claude uv run clio-author polish \
  --text-file clio-out/2601.23265/paper.md --voice concise --format prose

# Check cross-section consistency of a manuscript:
CLIO_LLM=claude uv run clio-author coherence \
  --markdown-file clio-out/2601.23265/paper.md --format prose

# Draft a WHOLE paper from an idea (outline → cite → write per section → assemble):
CLIO_LLM=claude uv run clio-author compose \
  --idea "Propose a new attention mechanism for long-range dependencies." \
  --log "Ran experiments on WikiText-103; BLEU +2.1 over baseline." \
  --review --out-dir clio-out/mypaper --format prose

# Same, but also emit paper.tex + references.bib:
CLIO_LLM=claude uv run clio-author compose \
  --idea-file idea.txt --log-file log.txt \
  --candidates-file refs.json \
  --review --out-dir clio-out/mypaper --latex

# Export an existing paper.md to LaTeX directly:
uv run clio-author export \
  --markdown-file clio-out/mypaper/paper.md \
  --bibtex-file clio-out/mypaper/references.bib \
  --out-dir clio-out/mypaper
```

After `compose`, the output directory contains:

```
clio-out/mypaper/
├── paper.md               # assembled Markdown manuscript
├── paper.tex              # (with --latex) standalone LaTeX document
├── references.bib         # (with --latex and citations) BibTeX entries
└── sections/
    ├── 01-introduction.md
    ├── 02-methods.md
    └── …
```

### Figures

```bash
# Generate matplotlib plot code (code text only; never executed by default):
CLIO_LLM=claude uv run clio-author run plot \
  --json '{"spec": {"kind": "plot", "intent": "training loss vs epoch"}}'

# Describe figures in a paper's memory blocks:
CLIO_LLM=claude uv run clio-author describe \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```

### Goal-driven orchestration

```bash
# Plan and run a sequence of actions from a natural-language goal:
CLIO_LLM=claude uv run clio-author orchestrate \
  --goal "Ingest 2601.23265 then produce a peer review." \
  --inputs-json '{"source":"2601.23265"}' --max-steps 4 --out-dir clio-out/orchestrate
```

### Generic escape hatch

```bash
# Any action by name (edit, write_review, figure_refine, …):
uv run clio-author run write_review \
  --json '{"outline": {"title": "Methods"}, "source": "...", "max_rounds": 2}'
```

**Single-file rule.** Every `--*-file` flag reads exactly **one** file. To supply several files as
context, concatenate them first or `ingest` each one and pass the resulting `blocks.json`.

**Saving results to a file.** Every action accepts `--out FILE`. A `.json` extension saves the
full indented JSON result; any other extension (`.md`, `.txt`, …) saves the prose `content` when
present, otherwise the full JSON. On success, `[saved to FILE]` is printed to stderr so stdout
stays clean JSON:

```bash
# Save a prose review to review.md:
CLIO_LLM=claude uv run clio-author review \
  --paper-file clio-out/2601.23265/paper.md --format prose --out review.md

# Save the full JSON result to a .json file:
CLIO_LLM=claude uv run clio-author ask \
  --question "What is the main contribution?" \
  --blocks-file clio-out/2601.23265/blocks.json --out answer.json
```

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

# 1) Discover what it can do (19 actions).
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

# 5) Draft a whole paper from an idea.
result = sub.run("compose", {
    "idea": "Propose a new attention mechanism for long-range dependencies.",
    "experimental_log": "Ran experiments on WikiText-103; BLEU +2.1 over baseline.",
    "review": True,
    "out_dir": "clio-out/mypaper",
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

## 5. The 19 actions at a glance

| # | Action | What it's for — use it to… | Subcommand |
|---|--------|-----------------------------|------------|
| 1 | `ingest` | **Read a paper.** Turn an arXiv id / URL / PDF / title into clean Markdown + structured memory blocks + extracted figures — the substrate every other action builds on. | `clio-author ingest <source>` |
| 2 | `ask` | **Understand a paper.** Get an answer to a question, grounded only in the paper's blocks, with the blocks it used cited. | `clio-author ask` |
| 3 | `cite` | **Check the scholarship.** Verify citation candidates against scholarly databases and get BibTeX *suggestions* — never edits your refs; fights fabricated citations. | `clio-author cite` |
| 4 | `review` | **Judge a paper.** Produce a peer review: an Accept/Reject decision, 1–10 + per-axis scores, and a structured critique (add `--ground` to cite real related work; add `--figures-json`/`--figures-file` with `CLIO_VISION=gemini` for a multimodal review that looks at the actual figure images). | `clio-author review` |
| 5 | `meta_review` | **Decide as a panel.** Aggregate several reviews into one area-chair decision (offline, no model). | `clio-author run meta_review` |
| 6 | `rebuttal` | **Respond to a review.** Draft an author rebuttal addressing each weakness and question point by point, grounded strictly in the paper, inventing nothing. | `clio-author rebuttal` |
| 7 | `plan` | **Blueprint a section.** Turn an idea/outline into per-section writing plans — tasks, claims, sources, word budgets — before any prose is written. | `clio-author plan` |
| 8 | `write` | **Draft a section.** Write one section grounded strictly in supplied source material (optionally following a `plan`). | `clio-author write` |
| 9 | `edit` | **Revise to feedback.** Rewrite existing prose to address specific reviewer weaknesses, preserving citations/claims. | `clio-author run edit` |
| 10 | `polish` | **Improve the prose.** Tighten clarity, flow, and academic voice (optional target voice) without changing meaning. | `clio-author polish` |
| 11 | `coherence` | **Catch contradictions.** Check a manuscript's sections for terminology drift, contradictions, undefined terms, and broken flow. | `clio-author coherence` |
| 12 | `kg` | **Map a paper's content.** Extract a knowledge graph of claims/methods/datasets/results + relations (distinct from a citation graph). | `clio-author kg` |
| 13 | `describe_figures` | **Caption figures.** Fill in figure descriptions (Gemini vision *looks at* the image when enabled) for context injection. | `clio-author describe` |
| 14 | `plot` | **Make a plot/diagram.** Generate matplotlib code (or, with vision, a real diagram image). | `clio-author run plot` |
| 15 | `compose` | **Write a whole paper.** One call: idea → outline → cite → (plan) → write each section → (review) → assemble. | `clio-author compose` |
| 16 | `export` | **Ship LaTeX.** Convert a Markdown manuscript into a compilable `paper.tex` (+ `references.bib`). | `clio-author export` |
| 17 | `write_review` | **Self-improve a draft.** Writer↔reviewer loop: draft → critique → revise, to better prose. | `clio-author run write_review` |
| 18 | `figure_refine` | **Self-improve a figure.** Visualizer↔critic loop on a figure spec. | `clio-author run figure_refine` |
| 19 | `orchestrate` | **Hand it a goal.** Plan and run a sequence of the above actions to achieve a natural-language goal (dynamic multi-step). | `clio-author orchestrate` |

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
- **`cite` returns nothing** — try `CLIO_SCHOLAR=openalex` or `CLIO_SCHOLAR=arxiv`; for Semantic
  Scholar specifically, set `SEMANTIC_SCHOLAR_API_KEY` to reduce rate limits.
- **`torchvision::nms` error after installing `rag`/`pdf`** — reinstall the matching CPU wheel:
  `uv pip install --reinstall torchvision --index-url https://download.pytorch.org/whl/cpu`.
- **`compose` / `export` produce no `.tex` file** — `--latex` requires `--out-dir` to be set so a
  `SafeFiles` can be rooted there; or use `export --markdown-file` to convert an existing `paper.md`.
- **A host invoking AUTHOR hangs** — don't point AUTHOR's nested model at the *same* host (e.g.
  `CLIO_LLM=codex` while the host is Codex) — it recurses. For grounding inside a host, prefer a
  no-LLM action like `cite`, or set the nested `CLIO_LLM` to a different provider.

---

## More

- **Why AUTHOR — motivation, the gap, capability matrix** → [`docs/MOTIVATION.md`](docs/MOTIVATION.md)
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

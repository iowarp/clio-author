# AUTHOR

**The whole scientific-paper lifecycle — read, review, write, illustrate, and ship — in one AI subagent.**

![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-BSD--3--Clause-green)
![Actions](https://img.shields.io/badge/actions-26-orange)
![Tests](https://img.shields.io/badge/tests-602%20passing-brightgreen)
![Offline](https://img.shields.io/badge/runs-offline%20out%20of%20the%20box-lightgrey)

AUTHOR (*Agentic Understanding for Thesis, Hypothesis, and Objective Research*) is a standalone,
pure-Python multi-agent harness for the scientific-paper lifecycle. It turns a paper — an arXiv link,
a PDF, or just a title — into clean Markdown, then puts specialized AI agents to work: answering
questions, verifying citations, reviewing, planning, drafting, illustrating, and exporting. It runs
on its own, and a larger agent (such as CLIO) can call it as a **subagent**.

Think of it as a research collaborator that never sleeps. Hand it your idea and results, and it
plans, drafts, and self-reviews a paper. Hand it someone else's PDF, and it gives you the kind of
feedback a program committee would — scores, strengths, weaknesses, and revision suggestions. You
don't have to start from scratch, and you don't have to start with ingestion: **enter at whatever
phase of the work you're in.**

> Runs **offline out of the box** with a built-in echo model (good for trying the plumbing). Add a
> real model (Claude / Codex / Ollama) for real output. Requires **Python ≥ 3.12**. BSD-3-Clause.
> Why one package instead of a dozen tools? → [`docs/MOTIVATION.md`](docs/MOTIVATION.md).

---

## Quickstart

**1. Install [`uv`](https://astral.sh/uv)** (the only prerequisite — a fast Python runner):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Get the code and install the core package:**

```bash
git clone https://github.com/SIslamMun/clio-author.git
cd clio-author
uv sync
```

**3. Confirm it works** (lists the 26 things it can do — no model or network needed):

```bash
uv run clio-author capabilities      # what it can do
uv run clio-author lifecycle         # which actions serve each phase of the author's journey
```

**4. Turn a real paper into Markdown** (`--extra pdf` adds the PDF/arXiv extractor; the first run
downloads ~500 MB of extraction models, later runs are fast):

```bash
uv run --extra pdf clio-author ingest 2601.23265
# also: ingest "Attention Is All You Need"  (by title) · ingest ./mypaper.pdf  (a local file)
```

This writes a folder you can open and read:

```
clio-out/2601.23265/
├── paper.md          # clean scientific Markdown
├── blocks.json       # structured sections / figures / equations
├── img/              # extracted figure images
└── 2601.23265.pdf    # the downloaded source PDF
```

**5. Get a real AI review** (needs a real model — see [Use a real model](#use-a-real-model)):

```bash
CLIO_LLM=claude uv run clio-author review \
  --paper-file clio-out/2601.23265/paper.md --format prose --out review.md
```

`--out FILE` saves the result alongside the JSON printed to stdout (`.md`/`.txt` → the prose, `.json`
→ the full result). It's available on every action.

---

## What it does — the author lifecycle

AUTHOR is a **toolkit you reach into at different moments**, not a fixed pipeline. You wear two hats —
the **Writer** (producing your own paper) and the **Referee** (judging others') — and you can **enter
at any phase**. Most jobs don't even need `ingest`: only `ask`, `kg`, `experiment`, and
`describe_figures` operate on a processed paper; everything else works from text, an idea, or JSON.

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

The full story, with copy-paste recipes per phase, is in **[`docs/LIFECYCLE.md`](docs/LIFECYCLE.md)**.

### The 26 actions at a glance

| Action | What it's for | Subcommand |
|--------|---------------|------------|
| `ingest` | **Read a paper.** arXiv id / URL / PDF / title → Markdown + blocks + figures. | `clio-author ingest <source>` |
| `gather` | **Build context.** Many sources (files/folders/globs/git/PDFs) → one merged `context.json`. | `clio-author gather` |
| `ask` | **Question answering.** Grounded answer from the paper's memory blocks. | `clio-author ask` |
| `kg` | **Map content.** Claims/methods/datasets/results graph; `--full` for the 6-stage pipeline. | `clio-author kg` |
| `discover` | **Find real papers.** Scholarly search (S2/OpenAlex/Crossref/arXiv); no LLM. | `clio-author discover` |
| `cite` | **Verify citations.** Check candidates against scholarly backends; suggestions only. | `clio-author cite` |
| `check_refs` | **Lint bibliography.** Malformed/duplicate entries, missing/uncited keys; no LLM. | `clio-author check-refs` |
| `research` | **Survey literature.** Foundational/recent/competing sources, gaps, synthesis. | `clio-author research` |
| `experiment` | **Recreate evaluation.** Extract reference papers' design/experiments → grounded eval plan. | `clio-author experiment` |
| `plan` | **Section blueprints.** Tasks, claims, sources, word budgets before drafting. | `clio-author plan` |
| `write` | **Draft a section.** Grounded in supplied source material. | `clio-author write` |
| `compose` | **Write a whole paper.** idea → outline → cite → write → assemble; `--latex`/`--pdf`. | `clio-author compose` |
| `revise` | **Revise prose.** `--mode feedback` (address review) or `style` (polish). Aliases: `edit`, `polish`. | `clio-author revise` |
| `coherence` | **Consistency check.** Terminology drift, contradictions, broken flow. | `clio-author coherence` |
| `verify_work` | **Claim audit.** Per-claim made/supported check → VERIFIED/GAPS verdict. | `clio-author verify-work` |
| `audit` | **Manuscript checklist.** Sections, word counts, placeholders, coverage; no LLM. | `clio-author audit` |
| `review` | **Peer review.** Accept/Reject + scores + critique; optional grounding and vision. | `clio-author review` |
| `section_review` | **Section review.** L1 refs → L2 coherence → L3 persona; severity summary. | `clio-author section-review` |
| `meta_review` | **Area-chair decision.** Aggregate several reviews; offline arithmetic. | `clio-author run meta_review` |
| `rebuttal` | **Author rebuttal.** Point-by-point response grounded in the paper. | `clio-author rebuttal` |
| `write_review` | **Self-improve a draft.** Writer ↔ reviewer critic-refine loop. | `clio-author run write_review` |
| `plot` | **Make a plot/diagram.** Matplotlib code (or real PNG with vision). | `clio-author run plot` |
| `describe_figures` | **Caption figures.** Text or Gemini vision descriptions. | `clio-author describe` |
| `figure_refine` | **Self-improve a figure.** Visualizer ↔ critic refine loop. | `clio-author run figure_refine` |
| `export` | **Ship LaTeX.** `paper.md` → `paper.tex` + `references.bib`; `--pdf` compiles PDF. | `clio-author export` |
| `orchestrate` | **Goal-driven.** Plan and run a sequence of actions from a natural-language goal. | `clio-author orchestrate` |

Every flag of every subcommand is documented in **[`docs/RUNBOOK.md`](docs/RUNBOOK.md)**; the action +
payload-key reference (for calling AUTHOR as a library) is in **[`docs/USAGE.md`](docs/USAGE.md)**.
Actions without a dedicated subcommand are reachable via `clio-author run <action> --json '...'`.

---

## Use a real model

By default AUTHOR uses an **offline echo model**, so text actions return a placeholder. Pick a real
one with `CLIO_LLM`:

| `CLIO_LLM` | What it uses | How to get it |
|---|---|---|
| `echo` *(default)* | nothing — offline placeholder | already works |
| `claude` | the `claude` CLI (no API key) | install Claude Code so `claude` is on your PATH |
| `codex` | the `codex` CLI | install the Codex CLI |
| `ollama` | a local model server | install [Ollama](https://ollama.com), then `ollama pull llama3.1:8b` |

```bash
CLIO_LLM=claude uv run clio-author review --paper-file clio-out/2601.23265/paper.md --format prose
```

Other variables: `CLIO_LLM_MODEL` (override model name), `CLIO_OLLAMA_URL` (default
`http://localhost:11434`), and the Gemini-vision trio `CLIO_VISION` / `CLIO_VISION_MODEL` /
`CLIO_IMAGE_MODEL` (set `CLIO_VISION=gemini` + `GEMINI_API_KEY` to let `describe_figures` and
diagram `plot` use real images).

**Citation backends (`CLIO_SCHOLAR`)** — default `auto` cascades Semantic Scholar → OpenAlex →
Crossref → arXiv; pin one with `semantic`/`s2`, `openalex`, `crossref`, `arxiv`, or disable with
`off`. Used by `cite`, `discover`, `review --ground`, and `research`. For Semantic Scholar at scale,
set `SEMANTIC_SCHOLAR_API_KEY`.

**Secrets** — keep keys in a local ignored env file (`cp .env.local.example .env.local`); it loads
automatically. Never paste keys into commands, issues, or commits. See
[`docs/SECURITY.md`](docs/SECURITY.md).

---

## Use it as a subagent

AUTHOR is meant to be **called by a host agent**. In-process (Python) is the recommended path:

```python
from clio_author.integration.clio_adapter import ClioAuthorSubagent
from clio_author.llm.providers import resolve_llm

# resolve_llm("claude") | "codex" | "ollama" | None (offline echo)
sub = ClioAuthorSubagent(llm=resolve_llm("claude"))

# Discover capabilities (each action carries lifecycle `phase` + `needs_source` metadata).
for a in sub.capabilities()["actions"]:
    print(a["action"], "—", a["description"])

# Ingest → ask → review (needs `uv sync --extra pdf` for real extraction).
ingested = sub.run("ingest", {"source": "2601.23265", "out_dir": "clio-out/demo"})
answer   = sub.run("ask", {"question": "What is the main contribution?", "blocks": ingested["structured"]})
review   = sub.run("review", {"paper": ingested["content"]})

# Draft a whole paper from an idea.
paper = sub.run("compose", {
    "idea": "Propose a new attention mechanism for long-range dependencies.",
    "experimental_log": "Ran on WikiText-103; BLEU +2.1 over baseline.",
    "review": True, "out_dir": "clio-out/mypaper", "latex": True,
})
```

Every `sub.run(action, payload)` returns a JSON-serializable
`{"action", "content", "structured", "metadata"}` and **never raises** — failures surface in
`metadata["error"]` (or a top-level `"error"`). The adapter imports nothing from the host, so the
coupling is one-directional. Any language can also call the CLI and read JSON from stdout
(exit `0` = ok, `1` = error). MCP-only hosts can use the bridge — `uv sync --extra mcp`.

---

## Optional extras

The core install is tiny and offline. Each heavy capability is opt-in:

```bash
uv sync --extra pdf        # real PDF/arXiv extraction (Docling + PyMuPDF) — needed for `ingest`
uv sync --extra rag        # real semantic search for `ask` (sentence-transformers + LanceDB)
uv sync --extra scholar    # live citation backends for `cite`/`discover` (httpx + thefuzz)
uv sync --extra viz        # actually render plot images (matplotlib)
uv sync --extra mcp        # the MCP bridge so MCP-only hosts (e.g. CLIO) can invoke it (fastmcp)
uv sync --all-extras       # everything at once
```

`torch` is pinned to the CPU build, so `--all-extras` resolves cleanly.

---

## Test it

```bash
uv run pytest                        # the offline test suite (no network, no model downloads)
uv run pytest -m live                # real-backend tests (need the extras + network)
```

---

## Troubleshooting

- **`clio-author: command not found`** — call it as `uv run clio-author …` (it lives in the venv).
- **`ingest` says a dependency is missing** — run `uv sync --extra pdf`. The first run downloads
  ~500 MB of Docling models once.
- **Output looks like a placeholder** — you're on the default echo model; set `CLIO_LLM=claude`
  (or `codex`/`ollama`).
- **`cite`/`discover` returns nothing** — try `CLIO_SCHOLAR=openalex` or `arxiv`; for Semantic
  Scholar set `SEMANTIC_SCHOLAR_API_KEY`.
- **`compose`/`export` produce no `.tex`** — `--latex` needs `--out-dir`; or use
  `export --markdown-file` on an existing `paper.md`.
- **`--pdf` reports a `pdf_error`** — no LaTeX engine (tectonic/latexmk/pdflatex) on PATH; the export
  still succeeds, install one to compile PDF.
- **A host invoking AUTHOR hangs** — don't point AUTHOR's nested `CLIO_LLM` at the *same* host (e.g.
  `CLIO_LLM=codex` under Codex) — it recurses. Use a no-LLM action (`cite`/`discover`) or a different
  nested provider.

---

## Docs

- **The author lifecycle — the story + per-phase recipes** → [`docs/LIFECYCLE.md`](docs/LIFECYCLE.md)
- **Runbook — every command, every flag** → [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- **Action & payload reference (library use)** → [`docs/USAGE.md`](docs/USAGE.md)
- **Why AUTHOR — motivation, the gap, capability matrix** → [`docs/MOTIVATION.md`](docs/MOTIVATION.md)
- **API keys & local env handling** → [`docs/SECURITY.md`](docs/SECURITY.md)
- **Design & architecture** → [`artifact/notes/DESIGN.md`](artifact/notes/DESIGN.md)
- **Working in this repo (for agents/contributors)** → [`AGENTS.md`](AGENTS.md) · **Changes** → [`CHANGELOG.md`](CHANGELOG.md)

## License

BSD-3-Clause. Adapts MIT / Apache-2.0 sources with attribution (see module headers); no AGPL code.

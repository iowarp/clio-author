<p align="center">
  <strong>AUTHOR</strong><br>
  <em>Agentic Understanding for Thesis, Hypothesis, and Objective Research</em><br>
  <em>The whole scientific-paper lifecycle — read, review, write, and ship — in one AI subagent.</em>
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.4.0-blue" />
  <img alt="Python" src="https://img.shields.io/badge/python-%E2%89%A53.12-3776ab" />
  <img alt="License" src="https://img.shields.io/badge/license-BSD--3--Clause-green" />
  <img alt="Actions" src="https://img.shields.io/badge/actions-26-orange" />
  <img alt="Tests" src="https://img.shields.io/badge/tests-602%20passing-brightgreen" />
  <img alt="Platform" src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey" />
</p>

---

AUTHOR is a standalone, pure-Python multi-agent harness for the scientific-paper lifecycle. It turns
a paper — an arXiv link, a PDF, or just a title — into clean Markdown, then puts specialized AI agents
to work: answering questions, verifying citations, reviewing, planning, drafting, illustrating, and
exporting. It runs on its own, and a larger agent (such as CLIO) can call it as a **subagent**.

Think of it as a research collaborator that never sleeps. Hand it your idea and results, and it
plans, drafts, and self-reviews a paper. Hand it someone else's PDF, and it gives you the kind of
feedback a program committee would — scores, strengths, weaknesses, and revision suggestions. You
don't have to start from scratch, and you don't have to start with ingestion: **enter at whatever
phase of the work you're in.**

## What You Get

- **26 actions across the author lifecycle** — frame · gather · plan · draft · strengthen · referee · respond · ship, all behind one interface
- **PDF/arXiv → clean scientific Markdown** with structured memory blocks (sections, figures, equations)
- **Grounded peer review** — Accept/Reject, per-axis scores, strengths/weaknesses, optional vision on figures
- **Source-grounded writing** — outline → plan → draft → self-review → LaTeX/PDF, with verified citations
- **Citations that are real** — a 4-backend scholarly cascade (Semantic Scholar / OpenAlex / Crossref / arXiv); never fabricated
- **A content knowledge graph** of a paper's claims/methods/datasets/results (6-stage pipeline)
- **Runs offline out of the box** (built-in echo model); add Claude / Codex / Ollama for real output
- **Callable as a subagent** in-process, over the CLI, or via an MCP bridge — imports nothing from the host

> Requires **Python ≥ 3.12** · BSD-3-Clause. Why one package instead of a dozen tools? →
> [`docs/MOTIVATION.md`](docs/MOTIVATION.md).

---

## Quickstart

**1. Install [`uv`](https://astral.sh/uv)** (the only prerequisite — a fast Python runner):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Get the code and install the core package:**

```bash
git clone <repo-url>          # the clio-author repository
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

| Action | What it's for |
|--------|---------------|
| `ingest` | **Read a paper.** arXiv id / URL / PDF / title → Markdown + blocks + figures. |
| `gather` | **Build context.** Many sources (files/folders/globs/git/PDFs) → one merged `context.json`. |
| `ask` | **Question answering.** Grounded answer from the paper's memory blocks. |
| `kg` | **Map content.** Claims/methods/datasets/results graph; `--full` for the 6-stage pipeline. |
| `discover` | **Find real papers.** Scholarly search (S2/OpenAlex/Crossref/arXiv); no LLM. |
| `cite` | **Verify citations.** Check candidates against scholarly backends; suggestions only. |
| `check_refs` | **Lint bibliography.** Malformed/duplicate entries, missing/uncited keys; no LLM. |
| `research` | **Survey literature.** Foundational/recent/competing sources, gaps, synthesis. |
| `experiment` | **Recreate evaluation.** Extract reference papers' design/experiments → grounded eval plan. |
| `plan` | **Section blueprints.** Tasks, claims, sources, word budgets before drafting. |
| `write` | **Draft a section.** Grounded in supplied source material. |
| `compose` | **Write a whole paper.** idea → outline → cite → write → assemble; `--latex`/`--pdf`. |
| `revise` | **Revise prose.** `--mode feedback` (address review) or `style` (polish). Aliases: `edit`, `polish`. |
| `coherence` | **Consistency check.** Terminology drift, contradictions, broken flow. |
| `verify_work` | **Claim audit.** Per-claim made/supported check → VERIFIED/GAPS verdict. |
| `audit` | **Manuscript checklist.** Sections, word counts, placeholders, coverage; no LLM. |
| `review` | **Peer review.** Accept/Reject + scores + critique; optional grounding and vision. |
| `section_review` | **Section review.** L1 refs → L2 coherence → L3 persona; severity summary. |
| `meta_review` | **Area-chair decision.** Aggregate several reviews; offline arithmetic. |
| `rebuttal` | **Author rebuttal.** Point-by-point response grounded in the paper. |
| `write_review` | **Self-improve a draft.** Writer ↔ reviewer critic-refine loop. |
| `plot` | **Make a plot/diagram.** Matplotlib code (or real PNG with vision). |
| `describe_figures` | **Caption figures.** Text or Gemini vision descriptions. |
| `figure_refine` | **Self-improve a figure.** Visualizer ↔ critic refine loop. |
| `export` | **Ship LaTeX.** `paper.md` → `paper.tex` + `references.bib`; `--pdf` compiles PDF. |
| `orchestrate` | **Goal-driven.** Plan and run a sequence of actions from a natural-language goal. |

Every action's **full command, every flag, and a runnable example** is in
**[`docs/RUNBOOK.md`](docs/RUNBOOK.md)** (copy-paste, grouped by lifecycle phase). The action +
payload-key reference for calling AUTHOR as a library is in **[`docs/USAGE.md`](docs/USAGE.md)**.

---

## Commands & arguments

Three flags are available on (almost) every command and are omitted below for brevity:
`--format {structured,prose}` (JSON vs. human-readable text), `--json '{...}'` (merge extra payload
keys), and `--out FILE` (also save the result). `A | B` means "either"; `…` means repeatable. Actions
without a dedicated subcommand are reached with `clio-author run <action> --json '{...}'`.

**Read & gather**
- `ingest <source>` — `<source>` = arXiv id / URL / local PDF path / paper title
- `gather [--sources S … | --sources-file FILE] [--out-dir DIR] [--max-files N] [--max-text-chars N]`

**Understand**
- `ask --question Q [--blocks-file FILE | --blocks-json JSON] [--sources S … | --sources-file FILE]`
- `kg [--blocks-file FILE | --blocks-json JSON] [--full] [--stages LIST] [--resume DIR] [--out-dir DIR] [--sources …]`
- `experiment [--sources S … | --blocks-file FILE | --markdown-file FILE | --text T] [--idea I | --idea-file FILE] [--out-dir DIR]`

**Sources & citations**
- `discover [--query Q | --query-file FILE] [--limit N] [--cutoff-date YYYY-MM] [--out-dir DIR]`
- `cite [--candidates-json JSON | --candidates-file FILE]`
- `check-refs [--bibtex TEXT | --bibtex-file FILE] [--markdown-file FILE | --text T]`
- `research [--topic T | --topic-file FILE] [--blocks-file FILE] [--depth {standard,deep}] [--sources …]`

**Plan & write**
- `plan [--idea I | --idea-file FILE] [--log L | --log-file FILE] [--outline-json JSON | --outline-file FILE] [--blocks-file FILE] [--candidates-file FILE] [--out-dir DIR] [--sources …]`
- `write [--source T | --source-file FILE] [--outline TITLE] [--sources …]`
- `compose [--idea I | --idea-file FILE] [--log L | --log-file FILE] [--outline-json JSON | --outline-file FILE] [--candidates-file FILE] [--review] [--max-rounds N] [--plan] [--latex] [--pdf] [--out-dir DIR] [--sources …]`
- `revise [--mode {feedback,style}] [--text T | --text-file FILE] [--review-json JSON | --review-file FILE] [--critic-notes TEXT] [--voice V] [--target FILE]`
- `polish [--text T | --text-file FILE] [--voice V] [--target FILE]` — alias of `revise --mode style`
- `coherence [--sections-json JSON | --sections-file FILE] [--markdown-file FILE | --text T]`

**Review & verify**
- `review [--paper T | --paper-file FILE] [--ground] [--figures-json JSON | --figures-file FILE] [--sources …]`
- `section-review [--text T | --text-file FILE] [--bibtex-file FILE] [--persona-json JSON]`
- `verify-work [--text T | --text-file FILE] [--section-plan-json JSON | --section-plan-file FILE] [--claims-json JSON]`
- `audit [--sections-json JSON | --sections-file FILE] [--markdown-file FILE] [--bibtex-file FILE]`
- `rebuttal [--paper T | --paper-file FILE] [--review-json JSON | --review-file FILE]`
- `run meta_review --json '{"reviews":[ … ]}'`
- `run write_review --json '{"outline":{…},"section_plan":{…},"blocks":{…},"max_rounds":N}'` — also `source` / `sources`

**Figures**
- `describe [--blocks-file FILE | --blocks-json JSON]` — fills figure descriptions (`describe_figures`)
- `run plot --json '{"spec":{…},"out_path":"…"}'`
- `run figure_refine --json '{"spec":{…},"out_path":"…","max_rounds":N}'`

**Ship & drive**
- `export [--title T] [--markdown-file FILE | --sections-json JSON | --sections-file FILE] [--bibtex-file FILE] [--out-dir DIR] [--pdf]`
- `orchestrate [--goal G | --goal-file FILE] [--inputs-json JSON | --inputs-file FILE] [--max-steps N] [--out-dir DIR]`

**Discovery**
- `capabilities` — list every action (with lifecycle `phase` + `needs_source` metadata)
- `lifecycle` — print the phase → actions map
- `run <action> [--json '{...}']` — dispatch any action by name (the generic escape hatch)

---

## Use a real model

By default AUTHOR uses an **offline echo model**, so text actions return a placeholder. Pick a real
one with `CLIO_LLM`:

| `CLIO_LLM` | What it uses | How to get it |
|---|---|---|
| `echo` *(default)* | nothing — offline placeholder | already works |
| `claude` | the `claude` CLI (no API key) | install Claude Code so `claude` is on your PATH |
| `codex` | the `codex` CLI | install the Codex CLI |
| `ollama` | a local Ollama server | install [Ollama](https://ollama.com), then `ollama pull llama3.1:8b` |
| `lmstudio` | a local [LM Studio](https://lmstudio.ai) server (OpenAI-compatible) | load a model in LM Studio, start its server; URL via `CLIO_LMSTUDIO_URL` (default `http://localhost:1234/v1`) |
| `openrouter` | the hosted [OpenRouter](https://openrouter.ai) gateway | set `OPENROUTER_API_KEY`; pick a model via `CLIO_LLM_MODEL` (default `openai/gpt-4o-mini`) |
| `litellm` | a [LiteLLM](https://docs.litellm.ai) proxy (OpenAI-compatible) | run the proxy; URL via `CLIO_LITELLM_URL` (default `http://localhost:4000/v1`), optional `LITELLM_API_KEY` |

```bash
CLIO_LLM=claude uv run clio-author review --paper-file clio-out/2601.23265/paper.md --format prose
CLIO_LLM=lmstudio CLIO_LLM_MODEL=qwen2.5-7b-instruct uv run clio-author ask --question "..." --blocks-file clio-out/2601.23265/blocks.json
CLIO_LLM=openrouter CLIO_LLM_MODEL=anthropic/claude-3.5-sonnet OPENROUTER_API_KEY=sk-... uv run clio-author review --paper-file paper.md --format prose
```

`lmstudio` / `openrouter` / `litellm` all speak the OpenAI-compatible `/chat/completions` API, so any
model they serve works. Other variables: `CLIO_LLM_MODEL` (override model name), `CLIO_OLLAMA_URL`,
and the Gemini-vision trio `CLIO_VISION` / `CLIO_VISION_MODEL` / `CLIO_IMAGE_MODEL` (set
`CLIO_VISION=gemini` + `GEMINI_API_KEY` to let `describe_figures` and diagram `plot` use real images).

**Citation backends (`CLIO_SCHOLAR`)** — default `auto` cascades Semantic Scholar → OpenAlex →
Crossref → arXiv; pin one with `semantic`/`s2`, `openalex`, `crossref`, `arxiv`, or disable with
`off`. Used by `cite`, `discover`, `review --ground`, and `research`. For Semantic Scholar at scale,
set `SEMANTIC_SCHOLAR_API_KEY`.

**Secrets** — keep keys in a local ignored env file (`cp .env.local.example .env.local`); it loads
automatically. Never paste keys into commands, issues, or commits. See
[`docs/SECURITY.md`](docs/SECURITY.md).

---

## Invoke it from a host — Codex · Claude · CLIO

AUTHOR is meant to be **driven by a host agent**, four ways. Full setup for each is in
**[`integration/README.md`](integration/README.md)**.

| Mode | Best for | Entry point |
|---|---|---|
| **Subagent** (in-process Python) | CLIO, any Python host | `ClioAuthorSubagent` |
| **Tool** (CLI / subprocess) | any language, any host | the `clio-author` console script |
| **Slash command** | Codex, Claude Code | `integration/codex/author.md`, `integration/claude/author.md` |
| **MCP** | MCP-only hosts | `clio_author.integration.mcp_bridge` (`uv sync --extra mcp`) |

### As a subagent (in-process Python) — recommended for CLIO

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
```

Every `sub.run(action, payload)` returns a JSON-serializable
`{"action", "content", "structured", "metadata"}` and **never raises** — failures surface in
`metadata["error"]`. The adapter imports nothing from the host, so the coupling is one-directional.

### As a tool (CLI / subprocess) — any language

```bash
uv run clio-author run review --json '{"paper":"# My paper\n..."}'   # JSON on stdout; exit 0 ok / 1 error
```

### As a slash command (Codex / Claude Code)

Both files are ready-to-use command prompts that drive the CLI and report the result — install, then
run `/author <task>`:

- **Codex** — install `integration/codex/author.md` as a Codex prompt/command.
- **Claude Code** — copy `integration/claude/author.md` to `.claude/commands/author.md` (project) or
  `~/.claude/commands/author.md` (user).

### Over MCP (MCP-only hosts, e.g. CLIO's tool gateway)

```bash
uv sync --extra mcp
uv run python -m clio_author.integration.mcp_bridge          # stdio; CLIO_MCP_TRANSPORT=http for HTTP
```

> **Avoid nesting deadlock:** don't set AUTHOR's nested `CLIO_LLM` to the *same* provider as the host
> (e.g. `CLIO_LLM=codex` under Codex). Use a no-LLM action (`cite`/`discover`) or a different provider.

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

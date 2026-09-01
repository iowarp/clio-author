<p align="center">
  <strong>AUTHOR</strong><br>
  <em>Agentic Understanding for Thesis, Hypothesis, and Objective Research</em><br>
  <em>The whole scientific-paper lifecycle — read, review, write, and ship — in one AI subagent.</em>
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.4.0-blue" />
  <img alt="Python" src="https://img.shields.io/badge/python-%E2%89%A53.12-3776ab" />
  <img alt="License" src="https://img.shields.io/badge/license-BSD--3--Clause-green" />
  <img alt="Actions" src="https://img.shields.io/badge/actions-24-orange" />
  <img alt="Roles" src="https://img.shields.io/badge/roles-7-orange" />
  <img alt="Tests" src="https://img.shields.io/badge/tests-683%20passing-brightgreen" />
  <img alt="Platform" src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey" />
</p>

---

AUTHOR is a standalone, pure-Python multi-agent harness for the scientific-paper lifecycle. It turns
a paper — an arXiv link, a PDF, or just a title — into clean Markdown, then puts specialized AI agents
to work: answering questions, verifying citations, reviewing, planning, drafting, illustrating, and
exporting. It runs on its own, and a larger agent — Clio Coder, Claude Code, Codex, or any Python
host — can drive it as a **subagent**.

Think of it as a research collaborator that never sleeps. Hand it your idea and results, and it
plans, drafts, and self-reviews a paper. Hand it someone else's PDF, and it gives you the kind of
feedback a program committee would — scores, strengths, weaknesses, and revision suggestions. You
don't have to start from scratch, and you don't have to start with ingestion: **enter at whatever
phase of the work you're in.**

## What You Get

- **24 tools + 7 roles across the author lifecycle** — frame · gather · plan · draft · strengthen · referee · respond · ship, all behind one interface
- **Guided pipeline** — every command suggests what to run next (on stderr + as `metadata.suggested_next` for host agents)
- **PDF/arXiv → clean scientific Markdown** with structured memory blocks (sections, figures, equations)
- **Grounded peer review** — Accept/Reject, per-axis scores, strengths/weaknesses, optional vision on figures
- **Source-grounded writing** — outline → plan → draft → self-review → LaTeX/PDF, with verified citations
- **Citations that are real** — a 4-backend scholarly cascade (Semantic Scholar / OpenAlex / Crossref / arXiv); never fabricated
- **A content knowledge graph** of a paper's claims/methods/datasets/results (6-stage pipeline)
- **Runs offline out of the box** (built-in echo model); add Claude / Codex / Ollama for real output
- **Callable from any host** — in-process subagent, CLI, MCP, A2A, a Claude Code plugin, or a Clio Coder skill; imports nothing from the host

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
git clone https://github.com/iowarp/clio-author.git
cd clio-author
uv sync
```

**3. Confirm it works** (lists the 24 things it can do — no model or network needed):

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

| Phase                   | Your question                        | Actions                                                                                                                                          |
| ----------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **① Frame**      | *What's my story; what exists?*    | `research`, `discover`, `ask`, `kg`, `experiment`                                                                                      |
| **② Gather**     | *Pull in what I'll build on*       | `ingest`, `gather`, `ask`, `kg`, `cite`                                                                                                |
| **③ Plan**       | *Blueprint the paper + evaluation* | `plan`, `plan_check`, `experiment`, `research` · role `writer`                                                                        |
| **④ Draft**      | *Write & illustrate*               | `write`, `plot`, `describe_figures` · roles `writer`, `viz`                                                                           |
| **⑤ Strengthen** | *Make my own paper bulletproof*    | `review`, `revise`, `coherence`, `verify_work`, `check_refs`, `cite`, `cite_support`, `audit` · roles `verifier`, `refiner` |
| **⑥ Referee**    | *Judge others' papers*             | `review`, `meta_review` · role `reviewer`                                                                                                 |
| **⑦ Respond**    | *Answer my reviewers*              | `rebuttal`, `revise`, `audit`                                                                                                              |
| **⑧ Ship**       | *Camera-ready*                     | `export` · role `writer`                                                                                                                    |
| **⟳ Drive**      | *Run a multi-step job for me*      | `orchestrate`                                                                                                                                  |

The full story, with copy-paste recipes per phase, is in **[`docs/LIFECYCLE.md`](docs/LIFECYCLE.md)**.

### Two layers: 24 tools + 7 roles

**Tools** 🔧 each do one specific job nothing else can. **Roles** 🧩 are fixed policies that run several
tools *for* you — the easy path through the pipeline (a role adds no new ability; it coordinates tools
and shares project memory). `orchestrate` is the one planner that chains tools/roles toward a goal.

**The 24 tools:**

| Action               | What it's for                                                                                                               |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `ingest`           | **Read a paper.** arXiv id / URL / PDF / title → Markdown + blocks + figures.                                        |
| `gather`           | **Build context.** Many sources (files/folders/globs/git/PDFs) → one merged `context.json`.                        |
| `ask`              | **Question answering.** Grounded answer from the paper's memory blocks.                                               |
| `kg`               | **Map content.** Claims/methods/datasets/results graph; `--full` for the 6-stage pipeline.                          |
| `discover`         | **Find real papers.** Scholarly search (S2/OpenAlex/Crossref/arXiv); no LLM.                                          |
| `cite`             | **Verify citations exist.** Check candidate titles against scholarly backends; suggestions only.                      |
| `check_refs`       | **Lint bibliography.** Malformed/duplicate entries, missing/uncited keys; no LLM.                                     |
| `cite_support`     | **Citation faithfulness.** Does each cited source actually support the claim? vs. abstract or (`--deep`) full text. |
| `verify_work`      | **Claim check.** Did the prose make + back the claims you planned? VERIFIED/GAPS.                                     |
| `audit`            | **Completeness checklist.** Sections, word counts, placeholders, coverage; no LLM.                                    |
| `research`         | **Survey literature.** Foundational/recent/competing sources, gaps, synthesis.                                        |
| `experiment`       | **Recreate evaluation.** Reference papers' design/experiments → grounded eval plan.                                  |
| `plan`             | **Section blueprints.** Tasks, claims, sources, word budgets before drafting.                                         |
| `plan_check`       | **Validate the plan before writing.** Deterministic: claim/citation coverage, word budgets, outline match; no LLM.    |
| `write`            | **Draft a section.** Grounded in supplied source material.                                                            |
| `revise`           | **Revise prose.** `--mode feedback` (address review) or `style` (polish). Replaces the old `edit`/`polish`.   |
| `coherence`        | **Consistency check.** Terminology drift, contradictions, broken flow.                                                |
| `review`           | **Peer review.** Accept/Reject + scores + critique; optional grounding and vision.                                    |
| `meta_review`      | **Area-chair decision.** Aggregate several reviews; offline arithmetic.                                               |
| `rebuttal`         | **Author rebuttal.** Point-by-point response grounded in the paper.                                                   |
| `plot`             | **Make a plot/diagram.** Matplotlib code (or real PNG with vision).                                                   |
| `describe_figures` | **Caption figures.** Text or Gemini vision descriptions.                                                              |
| `export`           | **Ship LaTeX.** `paper.md` → `paper.tex` + `references.bib`; `--pdf` compiles PDF.                           |
| `orchestrate`      | **Goal-driven.** Plans and runs a sequence of tools/roles from a natural-language goal.                               |

**The 7 roles** (`clio-author role <name>` — each runs the right tools, in order, and tells you what to run next):

| Role         | What it runs                                                                            |
| ------------ | --------------------------------------------------------------------------------------- |
| `reader`   | ingest/gather → kg (or ask) — understand sources                                      |
| `scholar`  | discover · research · cite · experiment — find + verify the literature              |
| `writer`   | plan → plan_check → draft the whole paper                                             |
| `verifier` | check_refs · cite_support · verify_work · audit · coherence → one grounding report |
| `reviewer` | review (or per-section) · meta_review — referee it                                    |
| `refiner`  | revise → coherence — apply feedback / polish                                          |
| `viz`      | plot (with critic refinement) · describe_figures                                       |

Every action's **full command, every flag, and a runnable example** is in
**[`docs/RUNBOOK.md`](docs/RUNBOOK.md)** (copy-paste, grouped by lifecycle phase). The action +
payload-key reference for calling AUTHOR as a library is in **[`docs/USAGE.md`](docs/USAGE.md)**.

---

## Commands & arguments

Every tool is `clio-author <name> …`; every role is `clio-author role <name> …`; anything else is
`clio-author run <action> --json '{...}'`. Discover the surface at runtime, and see the full
flag-by-flag reference in the RUNBOOK:

```bash
clio-author capabilities          # every tool + role, with lifecycle metadata
clio-author lifecycle             # the phase → actions map
clio-author <command> --help      # exact flags for any command
```

→ **[`docs/RUNBOOK.md`](docs/RUNBOOK.md)** — every command, flag, and a runnable example.
→ **[`docs/USAGE.md`](docs/USAGE.md)** — the payload-key reference for calling it as a library.

---

## Use a real model

By default AUTHOR uses an **offline echo model**, so text actions return a placeholder. Pick a real
one with `CLIO_LLM`:

| `CLIO_LLM`           | What it uses                                                      | How to get it                                                                                                    |
| ---------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `echo` *(default)* | nothing — offline placeholder                                    | already works                                                                                                    |
| `claude`             | the`claude` CLI (no API key)                                    | install Claude Code so`claude` is on your PATH                                                                 |
| `codex`              | the`codex` CLI                                                  | install the Codex CLI                                                                                            |
| `ollama`             | a local Ollama server                                             | install[Ollama](https://ollama.com), then `ollama pull llama3.1:8b`                                             |
| `lmstudio`           | a local[LM Studio](https://lmstudio.ai) server (OpenAI-compatible) | load a model in LM Studio, start its server; URL via`CLIO_LMSTUDIO_URL` (default `http://localhost:1234/v1`) |
| `openrouter`         | the hosted[OpenRouter](https://openrouter.ai) gateway              | set`OPENROUTER_API_KEY`; pick a model via `CLIO_LLM_MODEL` (default `openai/gpt-4o-mini`)                  |
| `litellm`            | a[LiteLLM](https://docs.litellm.ai) proxy (OpenAI-compatible)      | run the proxy; URL via`CLIO_LITELLM_URL` (default `http://localhost:4000/v1`), optional `LITELLM_API_KEY`  |

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

## Invoke it from a host — Clio Coder · Claude Code · Codex

AUTHOR is meant to be **driven by a host agent**. Pick by host; full setup for each is in
**[`integration/README.md`](integration/README.md)**.

| Host                    | Wire it in with                                                          | Entry point                                                          |
| ----------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| **Clio Coder**    | a**skill** (smallest unit), or the full extension + `author` agent | `integration/clio-coder/`                                        |
| **Claude Code**   | a**plugin** (bundles the MCP server + an `author` subagent)      | `integration/claude-plugin/`                                       |
| **Codex**         | an**MCP server** in `~/.codex/config.toml`                       | `codex mcp add clio_author -- clio-author-mcp`                     |
| any Python host         | **in-process subagent**                                            | `ClioAuthorSubagent`                                               |
| any agent               | **A2A** (Agent Card + `message/send`; one skill per tool + role) | `clio-author-a2a`                                                  |
| any MCP host            | **MCP** (stdio or HTTP)                                            | `clio-author-mcp`                                                  |
| any language            | **CLI / subprocess** (JSON on stdout)                              | the`clio-author` console script                                    |

### Clio Coder — as a skill

Clio Coder has **no MCP client**, so it drives the CLI directly. One command makes every Clio
Coder session on your machine able to use AUTHOR:

```bash
uv tool install 'clio-author[pdf,scholar,viz]'      # puts `clio-author` on PATH
clio-coder skills install \
  https://github.com/iowarp/clio-author/tree/main/integration/clio-coder/skills/clio-author \
  --user
```

Then, in any repository:

```text
/skill clio-author verify the citation "Attention Is All You Need"
```

For the full wiring — an `author` agent you can `/run`, an `/author-demo` prompt, and the demo
acts as declared `verify` checks — install the extension instead:

```bash
clio-coder extensions install integration/clio-coder --project
clio-coder extensions enable clio-author --project
mkdir -p .clio-coder/agents && cp integration/clio-coder/agents/author.md .clio-coder/agents/
```

See [`integration/clio-coder/`](integration/clio-coder/README.md).

### Any Python host — as a subagent (in-process)

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

### Claude Code — as a plugin

A real plugin (not a slash command) that registers the clio-author MCP server and an `author`
subagent. See [`integration/claude-plugin/`](integration/claude-plugin/README.md):

```bash
uv tool install 'clio-author[mcp]'                       # puts clio-author-mcp on PATH
claude --plugin-dir integration/claude-plugin            # local dev
# …or: /plugin marketplace add iowarp/clio-author  then  /plugin install clio-author@clio-author
```

### Codex — as an MCP server

Codex has no tool-server plugin API; MCP is the path. Register it in one line (config in
[`integration/codex/config.toml`](integration/codex/config.toml); guidance in
[`integration/codex/AGENTS.md`](integration/codex/AGENTS.md)):

```bash
uv tool install 'clio-author[mcp]'
codex mcp add clio_author -- clio-author-mcp
```

### MCP / A2A / CLI directly

```bash
clio-author-mcp                                              # MCP (stdio; CLIO_MCP_TRANSPORT=http for HTTP)
clio-author-a2a                                              # A2A Agent Card + message/send
clio-author run review --json '{"paper":"# My paper\n..."}' # CLI: JSON on stdout, exit 0 ok / 1 error
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
uv sync --extra mcp        # the MCP bridge for MCP hosts — Claude Code, Codex (fastmcp)
uv sync --all-extras       # everything at once
```

`torch` is pinned to the CPU build, so `--all-extras` resolves cleanly.

---

## Test it

```bash
uv run pytest                        # the offline test suite (no network, no model downloads)
uv run pytest -m live                # real-backend tests (need the extras + network)
```

**Grounding benchmark** — the experiment behind the headline claim (how much of a paper traces to a
real source end-to-end, vs single-slice tools that only see one half):

```bash
uv run python scripts/benchmark_grounding.py     # see eval/grounding/ for cases + the finding
```

---

## Troubleshooting

- **`clio-author: command not found`** — call it as `uv run clio-author …` (it lives in the venv).
- **`ingest` says a dependency is missing** — run `uv sync --extra pdf`. The first run downloads
  ~500 MB of Docling models once.
- **Output looks like a placeholder** — you're on the default echo model; set `CLIO_LLM=claude`
  (or `codex`/`ollama`). Since v0.4.1 the CLI warns on stderr when a model-backed action runs on
  the stub, so this no longer passes silently.
- **A re-run wrote nothing** — writes never clobber. A path that already exists is refused and
  listed in `metadata.write_skipped` (with a stderr warning). Re-run with **`--force`** to
  overwrite, or point `--out-dir` at a fresh directory.
- **`cite`/`discover` returns nothing** — try `CLIO_SCHOLAR=openalex` or `arxiv`; for Semantic
  Scholar set `SEMANTIC_SCHOLAR_API_KEY`.
- **`export` produces no `.tex`** — it needs `--out-dir`; run
  `export --markdown-file` on an existing `paper.md` (e.g. from `role writer`).
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
- **Host wiring — Clio Coder, Claude Code, Codex, MCP, A2A** → [`integration/README.md`](integration/README.md)
- **Design & architecture** → [`artifact/notes/DESIGN.md`](artifact/notes/DESIGN.md)
- **Working in this repo (for agents/contributors)** → [`AGENTS.md`](AGENTS.md) · **Changes** → [`CHANGELOG.md`](CHANGELOG.md)

## License

BSD-3-Clause. Adapts MIT / Apache-2.0 sources with attribution (see module headers); no AGPL code.

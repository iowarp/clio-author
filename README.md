# clio-parser

A standalone, pure-Python **multi-agent harness for processing, reviewing, and writing scientific
papers**. A main agent routes work to specialized **expert subagents**, backed by **retrieval** (RAG
+ Semantic Scholar) and **read/write/edit** file tools.

clio-parser is a *harness invoked by a host* (e.g. the CLIO agent). It is **not** an MCP server and
**not** a Markdown/blueprint agent — it is a normal Python package a host can call either in-process
or as a subprocess. It runs **standalone** and is tested on its own.

> **Status:** feature-complete through the planned roadmap (milestones **M0–M8**). 300+ hermetic
> tests pass; `ruff` + `mypy` clean. Releases: v0.1.0, v0.1.1, v0.1.2.
> See [`artifact/notes/PROGRESS.md`](artifact/notes/PROGRESS.md).

---

## Table of contents

1. [What it does](#what-it-does)
2. [Capabilities — the 11 actions](#capabilities--the-11-actions)
3. [Install](#install)
4. [Choosing a model](#choosing-a-model)
5. [Quickstart](#quickstart)
6. [Where output goes](#where-output-goes)
7. [Testing](#testing)
8. [Development](#development)
9. [Architecture](#architecture)
10. [Troubleshooting](#troubleshooting)
11. [License](#license)

---

## What it does

The full capability chain is built and invokable:

**ingest → retrieve / Q&A → cite → review → write / edit → figures**

- **Ingest** — convert an arXiv id / URL / PDF / paper title / topic into clean scientific Markdown
  plus structured *memory blocks* (sections, figures, equations). Figures are saved as PNG images.
- **Retrieve / Q&A** — index memory blocks and answer questions grounded only in retrieved blocks,
  citing the block ids used (selective context injection).
- **Cite** — verify citation candidates against Semantic Scholar (fuzzy title match + recency gate)
  and emit **suggestions only** (a `suggested.bib`); never overwrites a user bibliography.
- **Review** — produce structured, persona-conditioned peer reviews (AgentReview-style rubric) and
  aggregate multiple reviews into an area-chair meta-review.
- **Write / edit** — draft a single paper section grounded in scoped source material, and revise
  existing prose to address reviewer feedback (diff-based file edits via a sandboxed `SafeFiles`).
  A writer ↔ reviewer **critic-refine** loop is available.
- **Figures** — describe/caption figures for context injection, and generate matplotlib **plot code**
  (text only on the default path — generated code is never executed unless you call the gated
  `render_plot_code` helper).

---

## Capabilities — the 11 actions

All actions are reachable via `ClioParserSubagent.run(action, payload)`, the `clio-parser` CLI, or
the typed `ClioParserAgent` convenience methods. `clio-parser capabilities` prints the full manifest.

| # | Action | What it does | Key payload inputs | Key return fields |
|---|--------|-------------|-------------------|-------------------|
| 1 | `ingest` | PDF/arXiv/title → Markdown + memory blocks | `source`, `out_dir`* | `content` (Markdown), `structured` (MemoryBlocks), `metadata.extractor`, `metadata.wrote` |
| 2 | `ask` | Grounded Q&A over memory blocks | `question`, `blocks` | `content` (answer), `structured.cited_block_ids` |
| 3 | `review` | Structured peer review (AgentReview rubric) | `paper`, `persona`* | `structured` (PaperReview), `metadata.decision`, `metadata.overall` |
| 4 | `meta_review` | Aggregate reviews → area-chair meta-review | `reviews` (list of PaperReview/dicts) | `structured` (MetaReview), `metadata.reviewer_count` |
| 5 | `cite` | Verify citations; emit suggestions only | `candidates` (list `{title,year?,reason?}`), `out_dir`* | `structured.suggested_bibtex`, `structured.coverage` |
| 6 | `write` | Draft one paper section | `outline`/`section_plan`, `blocks`/`source`, `vision`*, `out_path`* | `content` (draft), `structured.word_count` |
| 7 | `edit` | Revise prose against reviewer feedback | `draft`/`target`, `review`/`critic_notes` | `content` (revised), `structured.word_count` |
| 8 | `describe_figures` | Fill figure descriptions for context injection | `blocks`/`figures`, `context`* | `structured.descriptions`, `structured.blocks`* |
| 9 | `plot` | Generate matplotlib plot code (text only) | `spec` (`{kind,intent,data_hint?,aspect_ratio?}`), `out_path`* | `content` (Python code), `structured.artifact` |
| 10 | `write_review` | Writer ↔ reviewer critic-refine loop | all `write` keys + `max_rounds`* (default 3) | final writer `AgentOutput` of the loop |
| 11 | `figure_refine` | Figure visualizer ↔ critic refine loop | `spec`, `out_path`*, `max_rounds`* (default 3) | final figure `AgentOutput` of the loop |

*Keys marked \* are optional.* The full per-action reference (return shape, fallback behavior,
safety notes) is in [`docs/USAGE.md`](docs/USAGE.md).

Every action degrades gracefully: missing inputs or failures produce an output whose
`metadata["error"]` (or top-level `error`) describes the problem rather than raising.

---

## Install

Requires **Python ≥ 3.12** and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync          # core install (pydantic only) — hermetic, no network or model downloads
```

The core install runs all 11 actions offline using a deterministic echo LLM client and an in-memory
retriever. Heavy paths are opt-in behind optional extras:

| Extra | Install command | What it enables |
|-------|----------------|-----------------|
| `pdf` | `uv sync --extra pdf` | Real PDF/arXiv extraction in `ingest` (Docling primary, PyMuPDF OCR fallback); pulls `docling`, `pymupdf`, `pillow`, `httpx` |
| `rag` | `uv sync --extra rag` | Real embeddings + vector store for `ask` (SentenceTransformer + LanceDB); pulls `lancedb`, `sentence-transformers`, `numpy` |
| `scholar` | `uv sync --extra scholar` | Real Semantic Scholar client + fuzzy matching for `cite`; pulls `thefuzz`, `httpx` |
| `viz` | `uv sync --extra viz` | Actual figure rendering via the gated `render_plot_code` helper; pulls `matplotlib` |

Install a subset as needed: `uv sync --extra pdf --extra scholar`.

Without a given extra, the corresponding feature still runs in its offline mode: `ingest` returns
`metadata["error"]` for the missing dependency; `ask` falls back to the deterministic hashing
embedder; `cite` requires an injected scholar client; `plot` emits code but never renders it.

**Gotcha — torch/torchvision mismatch.** With a very recent PyTorch (e.g. `2.12.0+cpu`), the CPU
wheel for `torchvision` may not be co-installed automatically, causing a
`Could not run 'torchvision::nms'` error. Fix it by reinstalling from the same CPU index:

```bash
uv pip install --reinstall torchvision --index-url https://download.pytorch.org/whl/cpu
```

**Gotcha — Docling first-run model download.** After installing the `pdf` extra, the first call to
`ingest` downloads ~500 MB of Docling ML models (layout, formula, figure classifiers). This is a
one-time download; subsequent runs use the cached models.

---

## Choosing a model

All experts default to the offline `EchoLLMClient`: the harness runs fully without a model, which
is correct for `ingest` (deterministic), `meta_review` (arithmetic), and `cite` (verification).
Actions that produce prose — `ask`, `review`, `write`, `edit`, `describe_figures`, `plot` — need a
**real provider** for useful output.

### Environment variables

| Variable | Values / default | Purpose |
|----------|-----------------|---------|
| `CLIO_LLM` | `echo` (default) \| `claude` \| `codex` \| `ollama` | Provider for the CLI |
| `CLIO_LLM_MODEL` | any model name | Override the default model name for the chosen provider |
| `CLIO_OLLAMA_URL` | `http://localhost:11434` | Base URL of a local Ollama server |
| `SEMANTIC_SCHOLAR_API_KEY` | (none) | Optional API key for the S2 endpoint; without it the public endpoint rate-limits with HTTP 429 (see [Troubleshooting](#troubleshooting)) |

### Ready-made providers

```python
from clio_parser.llm.providers import ClaudeCliLLMClient, CodexCliLLMClient, OllamaLLMClient, resolve_llm

# Session-based; no API key needed when Claude Code is authenticated
llm = ClaudeCliLLMClient()

# codex exec, non-interactive
llm = CodexCliLLMClient()

# Local Ollama server
llm = OllamaLLMClient(model="llama3.1:8b", url="http://localhost:11434")

# Equivalent to setting CLIO_LLM="claude"
llm = resolve_llm("claude")
```

Inject the provider at construction — all experts share the one client:

```python
from clio_parser import ClioParserAgent, ClioParserSubagent

agent = ClioParserAgent(llm=ClaudeCliLLMClient())
sub   = ClioParserSubagent(llm=resolve_llm("ollama"))
```

To write your own provider, implement the single synchronous method from
`clio_parser.llm.client.LLMClient`:

```python
from clio_parser.harness.types import Message

class MyLLMClient:
    def complete(self, messages: list[Message], **kwargs: object) -> str:
        ...   # call your API, return a string
```

---

## Quickstart

### Check available actions

```bash
clio-parser capabilities
```

### Ingest a paper

The `source` argument accepts an arXiv id, a full arXiv/HTTP URL, a local PDF path, a paper title,
or a topic string:

```bash
# arXiv id
clio-parser ingest 2601.23265

# Direct URL
clio-parser ingest https://arxiv.org/pdf/1706.03762.pdf

# Local file
clio-parser ingest /path/to/paper.pdf

# Paper title (resolved via the arXiv search API)
clio-parser ingest "Attention Is All You Need"

# Topic (resolves the top arXiv hit)
clio-parser ingest "transformer self-attention mechanism"
```

Output lands in `./clio-out/<slug>/`: a `paper.md` Markdown file, a `blocks.json` memory-blocks
dump, and an `img/` directory with extracted figure PNGs. Results are printed as JSON to stdout.

### Review with a real model

```bash
CLIO_LLM=claude clio-parser review --paper "$(cat clio-out/2601.23265/paper.md)"
```

### Ask a question over ingested blocks

```bash
CLIO_LLM=ollama CLIO_LLM_MODEL=llama3.1:8b \
  clio-parser ask \
    --question "What is the main contribution?" \
    --blocks-json "$(cat clio-out/2601.23265/blocks.json)"
```

### Dispatch any action by name

```bash
# meta_review, edit, plot, write_review, figure_refine — all reachable via 'run'
clio-parser run meta_review --json '{"reviews": [{"Overall": 7, "Decision": "Accept"}, {"Overall": 5, "Decision": "Reject"}]}'
clio-parser run plot --json '{"spec": {"kind": "plot", "intent": "bar chart of accuracy by model"}}'
```

### In-process Python

```python
from clio_parser import ClioParserSubagent
from clio_parser.llm.providers import ClaudeCliLLMClient

sub = ClioParserSubagent(llm=ClaudeCliLLMClient())

# Discover actions
print(sub.capabilities())   # {"name", "version", "actions": [...]}

# Ingest a paper
result = sub.run("ingest", {"source": "2601.23265", "out_dir": "/tmp/my-paper"})
blocks = result["structured"]   # MemoryBlocks dump

# Ask a question
answer = sub.run("ask", {"question": "What problem does this paper solve?", "blocks": blocks})
print(answer["content"])

# Review
review = sub.run("review", {"paper": result["content"]})
print(review["structured"]["decision"], review["structured"]["overall"])
```

All methods return plain `dict`s (`action`, `content`, `structured`, `metadata`) and never raise;
any failure is in `metadata["error"]` or the top-level `"error"` key.

For the typed `ClioParserAgent` surface (returns `AgentOutput` objects):

```python
from clio_parser import ClioParserAgent
from clio_parser.llm.providers import ClaudeCliLLMClient

agent = ClioParserAgent(llm=ClaudeCliLLMClient())
out = agent.review("# Title\n\nAbstract...")
# out.content, out.structured, out.metadata
```

---

## Where output goes

**CLI `ingest`** writes to `./clio-out/<slug>/` by default, where `<slug>` is the sanitized source
string (up to 64 characters). For `clio-parser ingest 2601.23265` that is
`./clio-out/2601.23265/`. The directory contains:

```
clio-out/2601.23265/
  paper.md         — extracted Markdown
  blocks.json      — MemoryBlocks dump (sections, figures, metadata)
  img/
    figure1.png    — extracted figure images (Docling path)
    figure2.png
    ...
```

You can override the directory with `--json '{"out_dir": "/your/path"}'`.

**Library `ingest` (no `out_dir`)** writes to a temporary directory
(`/tmp/clio-pdf-<random>/`) that persists for the duration of the process and is then cleaned up by
the OS. Pass `out_dir` explicitly to keep the results.

**Other actions** (write, edit, plot, cite) also accept an `out_path` / `out_dir` payload key to
persist their output under a `SafeFiles` root; without it, results are only in the returned dict.

---

## Testing

### Default hermetic suite

```bash
uv sync
uv run pytest        # 300+ hermetic tests — no network, no model downloads
```

The pytest configuration deselects `live` and `baseline` markers by default
(`addopts = "-m 'not live and not baseline'"`).

### Real end-to-end harness

`scripts/real_test.py` exercises every stage with real backends (PDF extraction, LLM, embeddings,
Semantic Scholar, matplotlib rendering). It is not pytest — run it directly:

```bash
uv sync --all-extras
CLIO_TEST_LLM=claude uv run python scripts/real_test.py
```

Knobs for `scripts/real_test.py`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CLIO_TEST_LLM` | `claude` | `claude` \| `codex` \| `ollama` \| `echo` (skips LLM stages) |
| `CLIO_OLLAMA_MODEL` | `llama3.1:8b` | Ollama model to use |
| `CLIO_OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `CLIO_TEST_PDF` | bundled PaperBanana PDF | Path or arXiv id/URL to ingest |
| `CLIO_FORCE_PYMUPDF` | (unset) | Set to `1` to skip Docling and use the PyMuPDF fallback |

### Gated real-backend tests

```bash
# Real embeddings, S2 lookups, matplotlib rendering:
uv sync --extra rag --extra scholar --extra viz
uv run pytest -m live

# Reference-impl comparisons + real-PDF extraction:
uv sync --extra pdf
uv run pytest -m baseline
```

Neither marker runs in CI's default hermetic pass.

---

## Development

### CI

Every pull request runs: **ruff** (lint + format check), **mypy** (type check), and **pytest**
(hermetic suite). See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

```bash
uv run ruff check clio_parser tests scripts
uv run ruff format --check clio_parser tests scripts
uv run mypy clio_parser
uv run pytest -q
```

### Dev agents

The `.claude/agents/` directory contains specialized subagents used during development
(`planner`, `designer`, `coder`, `test-engineer`, `debugger`, `code-reviewer`, `explorer`,
`progress`, `doc-updater`). See [`AGENTS.md`](AGENTS.md) for their scope and model assignments.

### Further reading

- [`docs/USAGE.md`](docs/USAGE.md) — full action reference, LLMClient contract, gated test details
- [`artifact/notes/DESIGN.md`](artifact/notes/DESIGN.md) — authoritative architecture and design decisions
- [`artifact/notes/SYNTHESIS.md`](artifact/notes/SYNTHESIS.md) — cross-artifact rationale and reuse map
- [`CLAUDE.md`](CLAUDE.md) — project rules and standards

---

## Architecture

```
clio_parser/
  agent.py                 ClioParserAgent: routes Task to expert by payload["action"]
  harness/                 BaseAgent, AgentProtocol, engine, patterns, session, types
    patterns.py            Sequential | Parallel | CriticRefine  (RoundRobin: future work)
  experts/                 ingestor · paper_qa · reviewer · meta_reviewer · citation ·
                           writer · editor · figure_agent  (+ models, loops)
  ingest/                  Docling + PyMuPDF extract · postprocess · tables · memory blocks
  retrieval/               rag (hashing default; LanceDB/SentenceTransformer extra) · scholar
  tools/files.py           SafeFiles: sandboxed read / write / diff-based edit
  llm/
    client.py              LLMClient protocol + EchoLLMClient (offline default)
    providers.py           ClaudeCliLLMClient · CodexCliLLMClient · OllamaLLMClient · resolve_llm
  eval/report.py           baseline metrics + report
  integration/
    clio_adapter.py        ClioParserSubagent: capabilities() + run() (JSON-serializable)
  cli.py                   `clio-parser` console entry point
tests/                     hermetic unit tests + gated live/baseline comparisons
scripts/real_test.py       real end-to-end validation harness
```

**Future work (deferred):** the `RoundRobin` pattern (reviewer-discussion escalation), diagram
image generation, and LLM vision captions for figures.

---

## Troubleshooting

**Semantic Scholar HTTP 429 (rate limited).** The public S2 endpoint is heavily rate-limited without
an API key. Set `SEMANTIC_SCHOLAR_API_KEY` in your environment. The `cite` action and the
`scholar_live` test gracefully handle 429s (the test marks itself as skipped rather than failing).

**Docling first-run model download hangs or is slow.** The `pdf` extra triggers a ~500 MB download
of Docling's layout, formula, and figure ML models on the first `ingest` call. This is normal and
happens once. If the download fails, ensure you have a stable network connection and retry.

**`torchvision::nms` op mismatch.** When installing the `rag` or `pdf` extra with a recent CPU
PyTorch (e.g. `2.12.0+cpu`), you may see:

```
RuntimeError: operator torchvision::nms does not exist
```

Fix by reinstalling `torchvision` from the matching CPU wheel index:

```bash
uv pip install --reinstall torchvision --index-url https://download.pytorch.org/whl/cpu
```

**`uv run --no-sync` after installing extras via `uv pip`.** If you installed an extra with
`uv pip install` directly (rather than `uv sync --extra`), run tests or scripts with
`uv run --no-sync` to prevent uv from rolling back the extra:

```bash
uv run --no-sync pytest -m live
```

---

## License

BSD-3-Clause. Adapted concepts and prompts are cited in-source by repository URL and license:
[paper-to-md](https://github.com/jmhessel/paper-to-md) (MIT),
[papervizagent / PaperBanana](https://github.com/JoshuaChou2018/papervizagent) (Apache-2.0),
[PaperOrchestra](https://github.com/google-deepmind/paper-orchestra) (Apache-2.0),
[wtf-p](https://github.com/shobrook/wut) (MIT).
AGPL-licensed concepts are re-implemented, not copied.

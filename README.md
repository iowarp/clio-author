# clio-parser

A standalone, pure-Python **multi-agent harness for processing, reviewing, and writing scientific
papers**. A main agent routes work to specialized **expert subagents**, backed by **retrieval** (RAG
+ Semantic Scholar) and **read/write/edit** file tools.

clio-parser is a *harness invoked by a host* (e.g. the CLIO agent). It is **not** an MCP server and
**not** a Markdown/blueprint agent — it is a normal Python package a host can call either in-process
or as a subprocess. It runs **standalone** and is tested on its own.

> **Status:** feature-complete through the planned roadmap (milestones **M0–M8**). 293 hermetic
> tests pass; `ruff` + `mypy` clean. See [`artifact/notes/PROGRESS.md`](artifact/notes/PROGRESS.md).

## What it does

The full capability chain is built and invokable:

**ingest → retrieve / Q&A → cite → review → write / edit → figures**

- **Ingest** — convert an arXiv id / URL / PDF into clean scientific Markdown plus structured
  *memory blocks* (sections, figures, equations).
- **Retrieve / Q&A** — index memory blocks and answer questions grounded only in retrieved blocks,
  citing the block ids used (selective context injection).
- **Cite** — verify citation candidates against Semantic Scholar (fuzzy title match + recency gate)
  and emit **suggestions only** (a `suggested.bib`); it never overwrites a user bibliography.
- **Review** — produce structured, persona-conditioned peer reviews (AgentReview-style rubric) and
  aggregate multiple reviews into an area-chair meta-review.
- **Write / edit** — draft a single paper section grounded in scoped source material, and revise
  existing prose to address reviewer feedback (diff-based file edits via a sandboxed `SafeFiles`).
  A writer ↔ reviewer **critic-refine** loop is available.
- **Figures** — describe/caption figures for context injection, and generate matplotlib **plot code**
  (text only — generated code is never executed on the default path).

Eleven actions are exposed: `ingest`, `ask`, `review`, `meta_review`, `cite`, `write`, `edit`,
`describe_figures`, `plot`, `write_review`, `figure_refine`. The full action catalog (payload keys
and return shapes) is in [`docs/USAGE.md`](docs/USAGE.md).

## Install

Requires **Python ≥ 3.12** and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync          # core install (pydantic only) — fully hermetic, no network or model downloads
```

The core install runs every action offline using a deterministic echo LLM client and an in-memory
retriever. Heavy paths are opt-in behind optional extras:

| Extra | `uv sync --extra <name>` enables | Pulls in |
|-------|----------------------------------|----------|
| `pdf` | Real PDF/arXiv extraction in `ingest` (Docling primary, PyMuPDF OCR fallback) | `docling`, `pymupdf`, `pillow`, `httpx` |
| `rag` | Real embeddings + vector store for retrieval (LanceDB + SentenceTransformer) | `lancedb`, `sentence-transformers`, `numpy` |
| `scholar` | Real Semantic Scholar client + fuzzy matching for `cite` | `thefuzz`, `httpx` |
| `viz` | Actual figure rendering via the gated `render_plot_code` helper | `matplotlib` |

Without an extra, the corresponding action still runs: `ingest` returns an error-flagged result
instead of extracting; retrieval falls back to a deterministic hashing embedder + in-memory index;
`cite` requires an injected scholar client; `plot` emits code but never renders it.

## Quickstart

### CLI (subprocess)

```bash
clio-parser capabilities                       # print the action manifest as JSON
clio-parser ingest 2601.23265                  # ingest an arXiv id / URL / PDF path
clio-parser review --paper "# Paper\n..."      # structured peer review
clio-parser ask --question "..." --blocks-json '{...}'
clio-parser run meta_review --json '{"reviews": [ ... ]}'   # any action by name
```

Each command prints an indented-JSON result and exits `1` if the result carries an error.

### In-process (Python API)

```python
from clio_parser import ClioParserSubagent

sub = ClioParserSubagent()
sub.capabilities()                              # {"name", "version", "actions": [...]}
sub.run("review", {"paper": "# Paper\n..."})    # {"action", "content", "structured", "metadata"}
```

`ClioParserSubagent` is the stable, JSON-serializable adapter surface (imports nothing from any
host, never raises). For typed convenience there is also `ClioParserAgent`:

```python
from clio_parser import ClioParserAgent

agent = ClioParserAgent()                       # defaults to an offline EchoLLMClient
out = agent.review("# Paper\n...")              # -> AgentOutput(content, structured, metadata)
```

Experts default to an offline `EchoLLMClient`; `ask` / `review` / `write` / `edit` need a real
provider to produce useful output. The CLI selects one via the **`CLIO_LLM`** environment variable —
`echo` (default, offline) · `claude` · `codex` · `ollama` (model via `CLIO_LLM_MODEL`):

```bash
CLIO_LLM=claude clio-parser review --paper "# Paper ..."     # real review from Claude
CLIO_LLM=ollama CLIO_LLM_MODEL=qwen2.5:14b clio-parser run ask --json '{"question": "...", "blocks": { ... }}'
```

Ready-made providers live in `clio_parser.llm.providers` (`ClaudeCliLLMClient`, `CodexCliLLMClient`,
`OllamaLLMClient`); for the in-process API pass one directly, e.g. `ClioParserAgent(llm=ClaudeCliLLMClient())`.
See [`docs/USAGE.md`](docs/USAGE.md) for the `LLMClient` contract and a skeleton client, and
`scripts/real_test.py` for an end-to-end real run.

## Testing

The default suite is **hermetic**: no network, no Docling/ML model loads.

```bash
uv run pytest                                  # 293 hermetic tests
```

Tests that need the outside world are **gated** behind markers and deselected by default:

```bash
uv run pytest -m live      --extra rag --extra scholar --extra viz   # network / real backends
uv run pytest -m baseline  --extra pdf                               # reference-impl / real-PDF comparisons
```

## Architecture

```
clio_parser/
  agent.py                MainAgent (ClioParserAgent): routes a Task to an expert by payload["action"]
  harness/                BaseAgent, AgentProtocol, engine, patterns, session, types
    patterns.py           Sequential | Parallel | CriticRefine  (RoundRobin: future work)
  experts/                ingestor · paper_qa · reviewer · meta_reviewer · citation ·
                          writer · editor · figure_agent  (+ review/write/figure models, loops)
  ingest/                 Docling + PyMuPDF extract · postprocess · tables · memory blocks
  retrieval/              rag (hashing default; LanceDB/SentenceTransformer extra) · scholar
  tools/files.py          SafeFiles: sandboxed read / write / diff-based edit
  llm/client.py           LLMClient protocol + EchoLLMClient (offline default)
  eval/report.py          baseline metrics + report
  integration/clio_adapter.py   ClioParserSubagent: JSON-serializable capabilities() + run()
  cli.py                  `clio-parser` console entry point
tests/                    hermetic unit tests + gated live/baseline comparisons
```

The authoritative design is in [`artifact/notes/DESIGN.md`](artifact/notes/DESIGN.md). Project rules
and standards are in [`CLAUDE.md`](CLAUDE.md).

**Future work (deferred):** the `RoundRobin` pattern (reviewer-discussion escalation), diagram
image generation, and LLM vision captions for figures.

## License

BSD-3-Clause. Adapted concepts are cited in-source by repository URL and license:
paper-to-md (MIT), PaperBanana / papervizagent (Apache-2.0), PaperOrchestra (Apache-2.0),
wtf-p (MIT). AGPL-licensed concepts are re-implemented, not copied.

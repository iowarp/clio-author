# clio-parser

A standalone, pure-Python **multi-agent harness for processing, reviewing, and writing scientific
papers**. A host agent (e.g. CLIO) invokes it as a **subagent** — in-process or as a subprocess CLI.
It is *not* an MCP server and *not* a Markdown/blueprint agent.

> **Status:** feature-complete (milestones M0–M8). 300+ hermetic tests; `ruff` + `mypy` clean.
> BSD-3-Clause. Full reference: [`docs/USAGE.md`](docs/USAGE.md).

## What it does

The chain **ingest → ask → cite → review → write/edit → figures**, as 11 actions:

| Action | What it does |
|---|---|
| `ingest` | arXiv id / URL / **paper title** / **topic** / local PDF → clean Markdown + memory blocks (+ figure PNGs) |
| `ask` | answer a question grounded in a paper's blocks (with citations) |
| `cite` | verify references against Semantic Scholar → BibTeX **suggestions** (never overwrites your refs) |
| `review` / `meta_review` | structured (or prose) peer review; aggregate several reviews |
| `write` / `edit` | draft a section / revise it from feedback |
| `plot` / `describe_figures` | generate matplotlib code / caption figures |
| `write_review` / `figure_refine` | iterative critic-refine loops |

Every action returns `{content, structured, metadata}` and **never raises** — failures surface in
`metadata["error"]`.

## Install

Python ≥ 3.12 + [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                  # core: offline & hermetic — every action runs with an echo model
uv sync --extra pdf      # real PDF/arXiv extraction (Docling + PyMuPDF)
uv sync --extra rag      # real semantic retrieval (sentence-transformers + LanceDB)
uv sync --extra scholar  # live Semantic Scholar for `cite`
uv sync --extra viz      # render plots (matplotlib)
```

## Run the CLI

`clio-parser` is a console script inside the `uv` venv, so it isn't on your global `PATH`. Invoke it
with **`uv run`** (or `source .venv/bin/activate`, then call it directly). Actions that use an extra
need it active on the run (`--extra pdf` / `--extra rag`).

```bash
uv run clio-parser capabilities                                      # list the 11 actions
uv run --extra pdf clio-parser ingest "Attention Is All You Need"    # id | url | title | topic | path
#   -> writes ./clio-out/<slug>/{paper.md, blocks.json, img/figures}
CLIO_LLM=claude uv run clio-parser review --paper "$(cat clio-out/<slug>/paper.md)"
CLIO_LLM=claude uv run clio-parser review --paper "..." --format prose   # human prose, not JSON
uv run clio-parser run <action> --json '{...}'                       # any action by name
```

## Pick a model

Experts default to an **offline echo** model (no real text). For real output, set `CLIO_LLM`:

| `CLIO_LLM` | Backend |
|---|---|
| `echo` *(default)* | offline / deterministic |
| `claude` | the `claude` CLI (session-based, no API key) |
| `codex` | `codex exec` |
| `ollama` | local Ollama (`CLIO_LLM_MODEL`, `CLIO_OLLAMA_URL`) |

Also: `SEMANTIC_SCHOLAR_API_KEY` makes `cite` reliable (the public endpoint rate-limits). And
`--format prose` (or payload `{"format":"prose"}`) returns a human-readable answer for **any** action
— the default `structured` returns JSON for host agents.

## Use it from another agent (as a subagent)

```python
from clio_parser.integration.clio_adapter import ClioParserSubagent
from clio_parser.llm.providers import resolve_llm

sub = ClioParserSubagent(llm=resolve_llm("claude"))   # "codex" | "ollama" | None (offline)
sub.capabilities()                                    # discover actions
result = sub.run("review", {"paper": markdown})       # -> {action, content, structured, metadata}
```

Or as a subprocess: `uv run clio-parser run <action> --json '{...}'` prints the result JSON on stdout
(exit `0` ok / `1` error). The adapter imports nothing from the host — coupling is one-directional.

## Test

```bash
uv run pytest                        # 300+ hermetic tests (offline, no model downloads)
uv run pytest -m live                # real backends (needs the extras + network)
uv run python scripts/real_test.py   # full real end-to-end (set CLIO_TEST_LLM=claude|codex|ollama)
```

## More

- **Full action/payload reference, providers, troubleshooting** → [`docs/USAGE.md`](docs/USAGE.md)
- **Architecture & design** → [`artifact/notes/DESIGN.md`](artifact/notes/DESIGN.md)
- **Agent/dev guide** → [`AGENTS.md`](AGENTS.md)

## License

BSD-3-Clause. Adapts MIT / Apache-2.0 sources with attribution (see module headers); no AGPL code.

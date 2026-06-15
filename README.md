# clio-parser

A standalone, pure-Python **multi-agent harness for processing, reviewing, and writing scientific
papers**. A main agent decomposes work across specialized **expert subagents**, backed by
**retrieval** (RAG + Semantic Scholar + optional knowledge graph) and **read/write/edit** file
tools.

> **Status:** early development. The architecture and project scaffolding are in place; the harness
> implementation is in progress (milestone **M0**). See [`artifact/notes/PROGRESS.md`](artifact/notes/PROGRESS.md).

## Capabilities (two tracks)

- **Processing** — convert an arXiv link or PDF into clean *scientific* Markdown with vision
  (figures, tables, equations), stored as structured *memory blocks* for selective context
  injection and question answering.
- **Writing & editing** — outline → plan → draft → review → revise, with citations grounded against
  external sources.

clio-parser is designed to run on its own and to be **invoked as a subagent** by a host agent.

## Architecture

```
clio_parser/
  agent.py            MainAgent: plan -> delegate to experts -> critic-refine -> synthesize
  harness/            BaseAgent, AgentProtocol, engine, patterns, session, types
  experts/            ingestor · figure · retriever · reviewer · writer · editor · citation
  ingest/             Docling + post-processing + tables + memory blocks
  retrieval/          rag (vector) · scholar (citation grounding) · kg (optional)
  tools/files.py      read / write / edit (diff-based)
  llm/client.py       provider abstraction (local vision models, Ollama, API)
tests/                unit tests + baseline comparisons
```

The authoritative design is in [`artifact/notes/DESIGN.md`](artifact/notes/DESIGN.md); the
comparative rationale across reference systems is in
[`artifact/notes/SYNTHESIS.md`](artifact/notes/SYNTHESIS.md).

## Getting started

Requires **Python ≥ 3.12** and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync          # install dependencies
uv run pytest    # run the test suite
```

## Development

This repository ships a Claude Code development harness under `.claude/` — specialized subagents
(planner, designer, coder, code-reviewer, debugger, test-engineer, explorer, progress, doc-updater)
and skills. Project rules and standards live in [`CLAUDE.md`](CLAUDE.md).

Reference material (source repositories and papers used for study and as evaluation baselines) is
fetched locally under `artifact/` and is **not** tracked in git; see
[`artifact/notes/MANIFEST.md`](artifact/notes/MANIFEST.md) to reproduce it.

## License

BSD-3-Clause (planned).

# CLAUDE.md — clio-parser

Project rules and context for Claude Code. Keep this file current; it is loaded every session.

## What this project is

**clio-parser** is a **standalone, pure-Python multi-agent harness** for **processing, reviewing,
and writing scientific papers**. A main agent decomposes work across specialized **expert
subagents**, backed by **retrieval** (RAG + Semantic Scholar + optional knowledge graph) and
**read/write/edit** file tools.

Two capability tracks:
- **Processing** — arXiv/PDF → clean *scientific* Markdown with vision (figures/tables/equations),
  stored as structured *memory blocks* for selective context injection and Q&A.
- **Writing & editing** — outline → plan → draft → review → revise, with grounded citations.

It is consumed by the **CLIO agent** (`iowarp/clio-agent`), which can invoke clio-parser as a
**standalone subagent**. That integration adapter is thin and deferred — **the harness stands and
is tested on its own.**

> **Hard rule — form.** clio-parser is a *proper Python agent harness* (à la the reference
> architectures `papervizagent` and `protoneo/knowledge`). It is **NOT** an MCP server and **NOT**
> a Markdown/blueprint agent. Do not build it as a CLIO Agent Blueprint or a FastMCP server.

## Architecture (target)

```
clio_parser/
  agent.py            MainAgent: plan -> delegate to experts -> critic-refine -> synthesize
  harness/            BaseAgent, AgentProtocol, engine, patterns, session, types
  experts/            ingestor · figure_agent · retriever · reviewer · writer · editor · citation
  ingest/             Docling + postprocess (fresh port) + tables + memory blocks
  retrieval/          rag (LanceDB) · scholar (Semantic Scholar) · kg (optional)
  tools/files.py      read / write / edit (diff-based)
  llm/client.py       provider abstraction (local vision models, Ollama, API)
integration/clio_adapter.py   thin shim so CLIO can invoke ClioParserAgent (deferred)
tests/baselines/      comparisons vs paper-to-md / PaperBanana / PaperOrchestra
```

The authoritative design lives in **`artifact/notes/DESIGN.md`**; cross-artifact rationale in
**`artifact/notes/SYNTHESIS.md`**; per-source deep studies in `artifact/notes/*.md`. Read those
before large changes — do not duplicate their content here.

## Tech stack & standards

- **Python ≥ 3.12**, managed with **`uv`** (`uv sync`, `uv run ...`). Never call `pip` directly.
- **Lint/format:** `ruff` (`uv run ruff check` / `ruff format`). **Types:** full type hints; check
  with `mypy` (or `pyright`). Data models use **Pydantic v2**.
- **Tests:** `pytest` under `tests/`. New behavior ships with tests. Baseline comparisons live in
  `tests/baselines/`.
- **Async** where I/O-bound (LLM calls, downloads), mirroring the reference harnesses.
- **Style:** match surrounding code; small, composable modules; docstrings on public APIs;
  no dead code or speculative abstractions.
- **License:** clio-parser targets **BSD-3-Clause** (matches CLIO). See licensing rule below.

## Licensing rule (IMPORTANT)

- May copy/adapt: **paper-to-md** (MIT), **PaperBanana/papervizagent** & **PaperOrchestra**
  (Apache-2.0), and the **phagocyte** ingest code (first-party).
- **Must NOT copy code** from **protoneo** (**AGPL-3.0**) into this permissively-licensed package —
  **re-implement its concepts** (BaseAgent shape, deliberation patterns, KG) from scratch.
- Preserve upstream license headers/attribution when adapting Apache/MIT code.

## Documentation rule (IMPORTANT)

Notes and docs under `artifact/notes/` (and any published material) must read as **standalone,
professional technical documentation**. Do **not** reference internal discussions, individuals, or
organizations. Cite sources only by **repo URL** and **license identifier**.

## Reference baselines (for evaluation)

Cloned in `artifact/repos/`: `paper-to-md`, `papervizagent` (PaperBanana), `wtf-p`,
`paper-orchestra` (PaperOrchestra), `protoneo`, `clio`, `phagocyte`. Papers in `artifact/papers/`.
clio-parser is benchmarked against these (PDF→MD fidelity, figure VLM-as-Judge, ≥90% citation
verification, review win-rate).

## Working agreement

- **Use the right subagent:** `planner`/`designer` for strategy, `coder` to implement,
  `test-engineer` for tests, `debugger` for failures, `code-reviewer` before merge, `explorer` for
  read-only search, `progress` for status / resuming, `doc-updater` for keeping docs in sync.
  (See `.claude/agents/`.)
- **Track progress:** the `progress` agent maintains `artifact/notes/PROGRESS.md` (the living ledger
  of done / in-progress / to-do, milestones, and where we left off). Check it when resuming and
  update it as milestones move.
- Confirm before destructive or outward-facing actions (force-push, deleting files you didn't
  create, publishing). Branch before committing on `main`.
- Prefer reusing existing utilities over adding new ones; check `artifact/notes/SYNTHESIS.md`
  reuse map first.
- Keep changes scoped; report test results honestly (show failures, don't paper over them).

## Subagent model policy

Models are matched to task difficulty and the cost of being wrong; escalate when a task exceeds its
tier.

| Agent | Model | Rationale |
|---|---|---|
| planner | **opus** | Architecture/sequencing — highest-leverage reasoning; a wrong plan wastes downstream work. |
| designer | **opus** | Long-lived interface/schema decisions; correctness compounds. |
| code-reviewer | **opus** | Must out-reason the implementer to catch subtle correctness/contract/license bugs. |
| debugger | **opus** | Open-ended root-cause analysis across traces and interactions. |
| coder | **opus** | Implementation quality is prioritized — strongest model writes the code. |
| test-engineer | **sonnet** | Pattern-following execution against a defined spec; fast and capable. |
| explorer | **sonnet** | Read-only search with synthesis; capable enough to trace, still cheap. |
| progress | **sonnet** | Survey + light reconciliation of ledger vs. reality; run often, so keep it cheap. |
| doc-updater | **sonnet** | Accurate doc synthesis from code; writing/sync work, run often. |

Escalation: bump a `sonnet` agent to `opus` for unusually complex one-off tasks; do not downgrade
the `opus` think/judge roles.


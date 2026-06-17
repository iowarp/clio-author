# AGENTS.md

Guidance for AI agents (and humans) working in the **clio-parser** repository. This is the
tool-agnostic companion to `CLAUDE.md`; both describe the same rules.

## What this project is

clio-parser is a **standalone, pure-Python multi-agent harness** for **processing, reviewing, and
writing scientific papers**. A main agent (`ClioParserAgent`) routes work to specialized expert
subagents, backed by retrieval and safe read/write/edit tools. It is designed to be **invoked as a
subagent by a host agent** (e.g. an external orchestration layer) via an in-process API
(`ClioParserSubagent`) or a subprocess CLI (`clio-parser`).

> **Form (do not change):** this is a *proper Python agent harness* — **not** an MCP server and
> **not** a Markdown/blueprint agent. Do not reshape it into either.

## Capabilities (the action surface)

`ingest` (arXiv/PDF → scientific Markdown + memory blocks) · `ask` (grounded Q&A) · `cite`
(Semantic Scholar verification, suggestions-only) · `review` / `meta_review` (AgentReview rubric +
panel) · `write` / `edit` (outline→draft→revise) · `describe_figures` / `plot` (figure captioning +
matplotlib code-gen) · `write_review` / `figure_refine` (iterative critic loops).

## Architecture

```
clio_parser/
  agent.py            ClioParserAgent — routes invoke() by payload["action"] to experts
  integration/        ClioParserSubagent — host-facing adapter (JSON in/out, CLIO-agnostic)
  cli.py              `clio-parser` console script
  harness/            BaseAgent, AgentProtocol, Engine, patterns (Sequential/Parallel/CriticRefine), session, types
  experts/            ingestor · paper_qa · citation · reviewer · meta_reviewer · writer · editor · figure_agent · echo
  ingest/             Docling+PyMuPDF extraction + postprocess (sections/citations/equations/figures/bibliography/tables/cleanup) + blocks
  retrieval/          rag (embeddings) · scholar (Semantic Scholar)
  tools/files.py      SafeFiles — sandboxed read/write/edit
  llm/client.py       LLMClient protocol + EchoLLMClient (offline default)
  eval/report.py      metrics + report
```

Design rationale: `artifact/notes/DESIGN.md`; cross-artifact analysis: `artifact/notes/SYNTHESIS.md`;
status + per-milestone plans: `artifact/notes/PROGRESS.md` and `artifact/notes/M*-PLAN.md`.

## Build, test, run

- **Python ≥ 3.12**, managed by **`uv`**. `uv sync` (core); `uv sync --all-extras` (heavy paths).
- **Test:** `uv run pytest` — the default suite is **hermetic** (offline, no heavy deps). Heavy/real
  paths are gated by markers: `uv run pytest -m live` / `-m baseline` (need the relevant extra +
  network). Never make the default suite require network or the optional extras.
- **Lint/types:** `uv run ruff check` / `ruff format`; `uv run mypy clio_parser`. Keep both clean.
- **Run:** `uv run clio-parser capabilities`; `uv run clio-parser run <action> --json '{...}'`.
- **Real end-to-end check:** `uv run python scripts/real_test.py` (drives real PDF/LLM/embeddings/
  Semantic Scholar/matplotlib; see `docs/USAGE.md`).

## Optional extras (lazy, gated)

`pdf` (Docling + PyMuPDF) · `rag` (LanceDB + sentence-transformers) · `scholar` (thefuzz + httpx) ·
`viz` (matplotlib). All heavy imports are **lazy inside functions**; importing any module must work
without the extras installed. The default install needs only `pydantic`.

## Conventions (follow these)

- **Experts never raise.** Catch everything and return an error-flagged `AgentOutput`
  (`metadata["error"]` / `["parse_error"]`), appended once to the session. Mirror existing experts.
- **Pydantic v2** for all data models; full type hints; small composable modules.
- **LLM boundary:** experts call `LLMClient.complete(messages) -> str`; default `EchoLLMClient` keeps
  tests hermetic. A real provider (Ollama, an API, etc.) plugs in by implementing that one method.
- **File safety:** all file writes go through `SafeFiles` (sandboxed root, `O_NOFOLLOW`, no clobber);
  never overwrite a user's source of truth. Citation/writer output is *suggestions only*.
- **Secret safety:** never commit, patch, print, or paste API keys/tokens. Use `.env.local` or
  `CLIO_ENV_FILE`; rotate any key that appears in chat, logs, issues, or commits.
- **Hermetic-first:** add the deterministic/offline path + tests first; gate the heavy path behind an
  extra + `live`.

## Licensing (important)

BSD-3-Clause. Adapt freely from MIT/Apache sources **with attribution** (paper-to-md MIT;
PaperBanana/PaperOrchestra Apache-2.0). **Never copy AGPL code** (protoneo) — re-implement concepts.
Preserve upstream license headers when adapting.

## Documentation rule

Notes/docs must read as standalone, publishable technical writing — no personal, organizational, or
internal-discussion references; cite sources by **repo URL + license** only.

## Working agreement

Branch before committing; one PR per change; run the code-review pass before merge (it has caught
real bugs). Report test results honestly (show failures). Keep `artifact/notes/PROGRESS.md` current.

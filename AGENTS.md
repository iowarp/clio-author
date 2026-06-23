# AGENTS.md

Guidance for AI agents (and humans) working in the **clio-author** repository. This is the
tool-agnostic companion to `CLAUDE.md`; both describe the same rules.

## What this project is

clio-author is a **standalone, pure-Python multi-agent harness** for **processing, reviewing, and
writing scientific papers**. A main agent (`ClioAuthorAgent`) routes work to specialized expert
subagents, backed by retrieval and safe read/write/edit tools. It is designed to be **invoked as a
subagent by a host agent** (e.g. an external orchestration layer) via an in-process API
(`ClioAuthorSubagent`) or a subprocess CLI (`clio-author`).

> **Form (do not change):** this is a *proper Python agent harness* — **not** an MCP server and
> **not** a Markdown/blueprint agent. Do not reshape it into either.

## Capabilities (the action surface)

**26 actions across the author lifecycle** (frame · gather · plan · draft · strengthen · referee ·
respond · ship · drive). Each manifest action carries `phase` + `needs_source` metadata. Highlights:

- **Read & gather:** `ingest` (arXiv/PDF → scientific Markdown + memory blocks), `gather` (many
  sources — files/folders/globs/git/PDFs — → one merged `context.json`).
- **Understand:** `ask` (grounded Q&A), `kg` (content knowledge graph; `--full` 6-stage pipeline).
- **Sources:** `discover` (scholarly search), `cite` (verify, suggestions-only), `check_refs`
  (deterministic bib lint), `research` (grounded literature brief).
- **Plan & write:** `plan`, `write`, `compose`, `revise` (`mode=feedback|style`; `edit`/`polish` are
  aliases), `coherence`, `experiment` (recreate an evaluation plan from reference papers).
- **Review & respond:** `review`, `section_review`, `meta_review`, `verify_work`, `audit`, `rebuttal`.
- **Figures / ship / drive:** `plot`, `describe_figures`, `figure_refine`, `export` (LaTeX + PDF),
  `orchestrate` (goal-driven multi-step), plus `write_review` (writer↔reviewer loop).

Full map: `clio-author lifecycle` and `docs/LIFECYCLE.md`; per-action reference in `README.md` and
`docs/RUNBOOK.md`.

## Architecture

```
clio_author/
  agent.py            ClioAuthorAgent — routes invoke() by payload["action"] to experts
  integration/        ClioAuthorSubagent — host-facing adapter (JSON in/out, CLIO-agnostic)
  cli.py              `clio-author` console script
  harness/            BaseAgent, AgentProtocol, Engine, patterns (Sequential/Parallel/CriticRefine), session, types
  experts/            ingestor · context (gather) · paper_qa (ask) · citation · discover · research ·
                      reviewer · meta_reviewer · rebuttal · section_review · verify_work · check_refs ·
                      audit · planner · writer · editor (revise/edit) · polish · coherence · compose ·
                      experiment · kg · figure_agent (plot/describe/refine) · echo
  ingest/             Docling+PyMuPDF extraction + postprocess (sections/citations/equations/figures/bibliography/tables/cleanup) + blocks + gather (multi-source)
  retrieval/          rag (embeddings) · scholar (4-backend cascade: S2/OpenAlex/Crossref/arXiv) · kg (content knowledge-graph pipeline)
  export/latex.py     paper.md -> paper.tex + references.bib (+ optional PDF compile)
  tools/files.py      SafeFiles — sandboxed read/write/edit
  llm/client.py       LLMClient protocol + EchoLLMClient (offline default)
  integration/        ClioAuthorSubagent adapter + manifest (action + lifecycle metadata) + mcp_bridge
```

Design rationale: `artifact/notes/DESIGN.md`; cross-artifact analysis: `artifact/notes/SYNTHESIS.md`;
status + per-milestone plans: `artifact/notes/PROGRESS.md` and `artifact/notes/M*-PLAN.md`.

## Build, test, run

- **Python ≥ 3.12**, managed by **`uv`**. `uv sync` (core); `uv sync --all-extras` (heavy paths).
- **Test:** `uv run pytest` — the default suite is **hermetic** (offline, no heavy deps). Heavy/real
  paths are gated by markers: `uv run pytest -m live` / `-m baseline` (need the relevant extra +
  network). Never make the default suite require network or the optional extras.
- **Lint/types:** `uv run ruff check` / `ruff format`; `uv run mypy clio_author`. Keep both clean.
- **Run:** `uv run clio-author capabilities`; `uv run clio-author run <action> --json '{...}'`.
- **Real end-to-end check:** `uv run python scripts/real_test.py` (drives real PDF/LLM/embeddings/
  Semantic Scholar/matplotlib; see `docs/USAGE.md`).

## Optional extras (lazy, gated)

`pdf` (Docling + PyMuPDF) · `rag` (LanceDB + sentence-transformers) · `scholar` (thefuzz + httpx) ·
`viz` (matplotlib) · `mcp` (fastmcp — the MCP bridge for MCP-only hosts). All heavy imports are
**lazy inside functions**; importing any module must work without the extras installed. The default
install needs only `pydantic`. (`git` on PATH is used by `gather` for git-repo sources.)

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

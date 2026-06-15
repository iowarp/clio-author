# PROGRESS — clio-parser

Living status ledger. Maintained by the `progress` subagent (see `.claude/agents/progress.md`).
Status legend: ✅ done · 🚧 in progress · ⬜ not started · ⛔ blocked.

**Last updated:** 2026-06-15
**Where we left off:** **M0 complete, reviewed, and fixed** — harness skeleton runs
(`ClioParserAgent.invoke()`; 5 tests pass, ruff + mypy clean; BSD-3 LICENSE added). Branch
`setup/project-harness` pushed; **PR #1** open against `main`. M1 is planned in `M1-PLAN.md`.
Next: **execute M1** (processing track — ingest port + `ingestor` expert).
See the **Session log** below to resume from the last working session.

## Setup phases

| # | Item | Status | Evidence |
|---|---|---|---|
| P0 | Acquire artifacts → `artifact/` | ✅ | 7 repos in `artifact/repos/`, 2 PDFs in `artifact/papers/`, `MANIFEST.md` |
| P1 | Deep study (per-artifact notes) | ✅ | 9 notes in `artifact/notes/` (clio, phagocyte, paper-to-md, wtf-p, protoneo, papervizagent, 2 papers) |
| P2 | Comparative synthesis | ✅ | `artifact/notes/SYNTHESIS.md` |
| P3 | Design (architecture + build form) | ✅ | `artifact/notes/DESIGN.md` (standalone harness) |
| P4 | Dev harness (`.claude/`) | ✅ | `CLAUDE.md`, `settings.json`, 7 agents, 2 skills |

## Build milestones (from DESIGN.md §5)

| # | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Harness skeleton (`BaseAgent`, `AgentProtocol`, engine, patterns, session, types) + trivial expert; `ClioParserAgent.invoke()` runs | ✅ | `clio_parser/harness/` + `agent.py` + `experts/echo.py` + `llm/client.py`; 4 tests pass, ruff/mypy clean |
| M1 | Processing track: `ingest/` port + `ingestor` expert → Markdown + memory blocks; baseline diff | ⬜ | |
| M2 | Memory blocks + selective injection + `rag` retrieval; `paper_qa` | ⬜ | |
| M3 | Grounding: `scholar` (Semantic Scholar) + `citation` expert | ⬜ | |
| M4 | Review: `reviewer` + critic-refine pattern + multi-reviewer | ⬜ | |
| M5 | Write/edit: `writer` + `editor` + file tools | ⬜ | |
| M6 | Figures (optional): `figure_agent` generation | ⬜ | |
| M7 | Harden gaps: table fidelity, generalized equations, baseline eval report | ⬜ | |
| M8 | CLIO integration: thin `clio_adapter` so CLIO can invoke the harness | ⬜ | deferred |

## Open decisions / pending inputs

- ✅ **Agent framework** — plain Python + Pydantic v2 + a pluggable, synchronous `LLMClient` (M0);
  DSPy / LiteLLM / async deferred to concrete `LLMClient` implementations at the seam.
- ✅ **Writing scope** — all capabilities, phased (review → HITL writing → autonomous).
- ⬜ **Default VLM / embedding models** for vision + RAG.
- ⛔ **Phagocyte license** — unspecified upstream; confirm before lifting code verbatim (plan is a fresh port regardless).

## Session log (resume here)

Newest first. Each entry: what we decided, what we did, and where we stopped — so the next session
can continue from the last conversation without re-deriving context.

### 2026-06-15 — Session 2: push, README, M0 skeleton
**Decisions made:**
- **Agent framework (M0):** plain Python + Pydantic v2 + a pluggable synchronous `LLMClient`
  (`EchoLLMClient` stub for hermetic tests). DSPy/LiteLLM/async deferred to concrete client impls.

**Done this session:**
- Pushed branch `setup/project-harness` to GitHub; wrote and pushed a real `README.md`.
- **M0 complete:** scaffolded `clio_parser/` (`harness/` types, protocol, base, session, patterns,
  engine; `llm/client.py`; `experts/echo.py`; `agent.py`) + `pyproject.toml` + tests. `Sequential`
  pattern implemented; `Parallel`/`RoundRobin`/`CriticRefine` are documented stubs.
- Verified: `uv run pytest` → 4 passed; `ruff` + `mypy` clean; `invoke("hello world")` works.

**Stopped at:** M0 done and verified; M0 commit pending push on `setup/project-harness`.

**Next step:** M1 — processing track. Use `planner` to plan the fresh port of the paper-to-md /
phagocyte post-processing into `clio_parser/ingest/`, then build the `ingestor` expert (PDF/arXiv →
scientific Markdown + memory blocks) and a baseline diff. Optionally run `code-reviewer` on M0 first.

### 2026-06-15 — Session 1: artifacts, design, dev harness
**Decisions made:**
- **Form (locked):** clio-parser is a **standalone, pure-Python multi-agent harness** — *not* an MCP
  server, *not* a Markdown/blueprint agent. The CLIO agent (`iowarp/clio-agent`, develop) will
  **invoke** it as a standalone subagent (thin adapter, deferred). Reference harnesses:
  `papervizagent` + `protoneo/knowledge`.
- **Ingest core:** fresh minimal port of the paper-to-md/phagocyte post-processing.
- **Writing scope:** all capabilities, phased (review → human-in-the-loop writing → autonomous).
- **Framework:** decide at M0 (plain Python+LiteLLM vs DSPy — prototype both).
- **License:** target BSD-3; re-implement AGPL `protoneo` concepts (no code copy); confirm
  Phagocyte license before lifting.
- **Docs rule:** notes must be publishable — no references to individuals/organizations or internal
  discussion; cite sources by repo URL + license only. (All notes scrubbed accordingly.)
- **Subagent models:** opus for planner/designer/coder/code-reviewer/debugger; sonnet for
  test-engineer/explorer/progress.

**Done this session:**
- Initialized git + pushed clio-parser to GitHub.
- Acquired 7 repos + 2 papers into `artifact/`; wrote `MANIFEST.md`.
- Deep-studied every artifact → 9 notes; wrote `SYNTHESIS.md` and `DESIGN.md`.
- Built the `.claude/` dev harness (CLAUDE.md, settings.json, 7 agents, 2 skills); verified all
  formats against official Claude Code docs.
- Added the `progress` agent (with a Session log) and the `doc-updater` agent; created this
  `PROGRESS.md` ledger.

**Stopped at:** setup complete (P0–P4). No build code yet. Everything uncommitted on `main`.

**Next step:** M0 — scaffold the harness skeleton (`clio_parser/harness/`: `BaseAgent`,
`AgentProtocol`, engine, patterns, session, types + a trivial expert so `ClioParserAgent.invoke()`
runs). Use `planner` to produce the M0 build plan first. (Optionally commit P0–P4 to a branch first.)

## Changelog

- 2026-06-15 — P0–P4 complete; `.claude/` dev harness standardized; progress ledger + session log created; `doc-updater` agent added.
- 2026-06-15 — branch pushed; README written; **M0 harness skeleton** complete (4 tests pass, ruff/mypy clean).

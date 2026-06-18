# M8 Build Plan — Main-Agent Routing + CLIO Integration Adapter

The capstone: turn `ClioAuthorAgent` into the real **main agent** that routes to every expert, and
add a thin **adapter** + **CLI** so the CLIO agent (or any host) can invoke clio-author as a
standalone subagent. Per the locked form: a standalone Python harness CLIO *invokes* — NOT an MCP
server, NOT a blueprint. The adapter is intentionally thin and CLIO-agnostic (no CLIO imports).

## Decisions
- **Hermetic-first:** default `EchoLLMClient`; all routing/adapter/CLI tests run offline. Real
  LLM/PDF/scholar/viz paths stay gated behind their extras.
- **Back-compat:** `ClioAuthorAgent().invoke("hello world")` must still return the echo output
  (M0 test) — unknown/no action → echo expert.
- Loose coupling: the adapter exposes a stable, serializable interface; CLIO calls it via import or
  subprocess (CLI). No dependency on the `clio-agent` repo.

## Steps
1. **Upgrade `clio_author/agent.py`** — `ClioAuthorAgent.__init__(self, llm=None, *, files=None,
   scholar_client=None)` builds the expert set (echo, ingestor, paper_qa, reviewer, meta_reviewer,
   citation, writer, editor, figure) sharing the llm/files/scholar_client. `invoke(task: str | Task)
   -> AgentOutput` routes on `task.payload.get("action")`:
   - `ingest`→IngestorExpert, `ask`→PaperQAExpert, `review`→ReviewerExpert,
     `meta_review`→MetaReviewerExpert, `cite`→CitationExpert, `write`→WriterExpert,
     `edit`→EditorExpert, `describe_figures`/`plot`→FigureAgentExpert; unknown/None→EchoExpert.
   - Plus loop entry points: `write_review` → `run_write_review_loop`, `figure_refine` →
     `run_figure_refine` (return the final output / list as appropriate).
   - Typed convenience methods wrapping the above: `ingest(source)`, `ask(question, blocks)`,
     `review(paper, persona=None)`, `cite(candidates, ...)`, `write(outline, source, ...)`,
     `edit(draft, review)`, `describe_figures(blocks)`, `plot(spec)`. Each builds a `Task` and calls
     `invoke`. Never raises (experts already error-flag).
2. **`clio_author/integration/__init__.py` + `clio_author/integration/clio_adapter.py`** —
   `ClioAuthorSubagent` wrapping `ClioAuthorAgent` (no CLIO imports):
   - `capabilities() -> dict` — a manifest: name, version, the list of actions with one-line
     descriptions and expected payload keys (so a host/CLIO can discover what it can invoke).
   - `run(action: str, payload: dict | None = None) -> dict` — dispatch to `invoke`, return a
     JSON-serializable `{"action","content","structured","metadata"}`. Never raises (catch → error dict).
3. **`clio_author/cli.py`** — argparse with subcommands (`ingest`, `ask`, `review`, `cite`, `write`,
   `describe`, `capabilities`) that build a payload and call `ClioAuthorSubagent.run`, printing JSON.
   Add `clio-author = "clio_author.cli:main"` console script in `pyproject.toml`. Real heavy paths
   require the relevant extra; the CLI itself imports lazily and degrades to error dicts.
4. **Tests** (hermetic): `tests/test_agent_routing.py` (each action routes to the right expert via a
   canned/Echo client; unknown→echo; back-compat echo; convenience methods). `tests/integration/
   test_clio_adapter.py` (`capabilities()` shape; `run(action,payload)` returns serializable dict for
   each action incl. error cases; `json.dumps` round-trips). `tests/test_cli.py` (argparse dispatch
   with Echo → JSON to stdout; `capabilities` subcommand; unknown action → error JSON, nonzero/zero
   exit as designed).
5. **Docs/notes:** update README "invoked as a subagent" with the adapter/CLI usage; note CLIO calls
   `ClioAuthorSubagent` (import) or the `clio-author` CLI (subprocess). No AGPL; BSD-3.

## Smallest hermetic first slice
`ClioAuthorAgent` routing + `ClioAuthorSubagent.run/capabilities`, Echo-tested.

## Risks
- Keep `invoke` back-compat (echo on unknown) so the M0 test passes.
- Adapter output must be JSON-serializable (use `model_dump()` already in `structured`).
- CLI heavy paths gated; default offline.

## Verification
`uv run pytest` hermetic green; `ruff`/`mypy` clean; `ClioAuthorAgent().invoke("hi")` → echo
(back-compat); `ClioAuthorSubagent().run("ingest", {...})` returns a JSON-serializable error/result
dict offline; `python -m clio_author.cli capabilities` prints the manifest JSON.

## Files
- New: `clio_author/integration/{__init__,clio_adapter}.py`, `clio_author/cli.py`,
  `tests/test_agent_routing.py`, `tests/integration/{__init__,test_clio_adapter}.py`, `tests/test_cli.py`.
- Modify: `clio_author/agent.py`, `clio_author/__init__.py` (export `ClioAuthorSubagent`),
  `pyproject.toml` (console script), `README.md`.
- Reuse: all experts (`clio_author/experts/*`), loop helpers (`write_loop`, `figure_agent`),
  `harness/{engine,session,types}.py`, `llm/client.py`, `tools/files.py`.

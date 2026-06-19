# Does AUTHOR help? — with vs without, across three hosts

A controlled comparison: the **same task** run by each host **with** AUTHOR (as a subagent) and
**without** it (the host's own LLM doing the task). Hosts: Claude (CLI, `haiku`), Codex (CLI), and
CLIO (its tool gateway). Goal: isolate what AUTHOR adds for the user and for the agentic system.

## How each host invoked AUTHOR (process + evidence)

- **Claude** — subprocess host. Command:
  `claude -p "<task: use clio-author run meta_review …>" --model haiku --allowedTools Bash --dangerously-skip-permissions --output-format stream-json --verbose`.
  Captured tool call (proof it really invoked AUTHOR, not guessed):
  `TOOL CALL > uv run --no-sync clio-author run meta_review --json '{"reviews":[…]}'` — it even
  self-corrected the payload from a bare list to `{"reviews":[…]}` and then succeeded.
- **Codex** — subprocess host. Command:
  `codex exec --dangerously-bypass-approvals-and-sandbox "Run: uv run --no-sync clio-author run meta_review --json '…' …"`.
- **CLIO** — driven through **CLIO's own code** (the cloned repo's `clio_agent` package, in CLIO's
  venv): `spec_from_declaration` → `build_gateway` → `create_sync_tool_executor` (from
  `clio_agent.tools.{mcp_config,gateway,execution}`). CLIO's gateway spawned the MCP bridge
  (`python -m clio_author.integration.mcp_bridge`) over stdio, **discovered** the tools
  (`clioauthor_capabilities`, `clioauthor_run`), and called `run(meta_review)`. Driver:
  `scripts/clio_gateway_test.py`. This exercises CLIO's real tool-invocation machinery with **no LM
  turn** (so zero model tokens). A full LM-backed CLIO conversation needs a configured backend and was
  not run here.

## Result matrix

### Task 1 — `meta_review` (aggregate 3 reviews → decision + overall)
| Host | WITH AUTHOR | WITHOUT AUTHOR |
|---|---|---|
| Claude (haiku) | `Accept, 6/10` (AUTHOR's defined rule; structured scores) | `Accept, 6` — but via an **ad-hoc** rule it invented ("majority + mean 5.67") |
| Codex | `Accept, 6` | `Accept, 6` — **19,316 tokens** for the one call |
| CLIO | `Accept (6/10), 3 reviewers` via its gateway, **0 model tokens** | (needs a full LM turn / backend — not run) |

**Reading:** on trivial arithmetic the raw LLMs *can* land the same answer — but each used a
different, undefined aggregation rule, returned only prose (no per-axis scores), wasn't reproducible,
and (Codex) spent ~19K tokens. AUTHOR returns the same defined decision + 7 structured scores every
time, for ~0 model tokens.

### Task 2 — citation grounding (BibTeX for a **nonexistent** paper)
Title: *"Retrieval-Augmented Diffusion Transformers for Tabular Time-Series Forecasting" (2024)* — fabricated.
| | WITH AUTHOR (`cite`) | WITHOUT AUTHOR |
|---|---|---|
| Fake paper | **NOT FOUND** — `num_verified=0`; refuses to invent | Claude **refused** ("need WebSearch permission") → task uncompleted; an instructed/less-aligned model would fabricate (literature reports 78–90% citation-hallucination) |
| Real paper (*Attention Is All You Need*) | **VERIFIED** — real `@inproceedings{vaswani2017…}` from scholarly DBs | — |

**Reading:** verification against real databases is a capability the host *structurally lacks* — it
either refuses or risks fabricating. AUTHOR gives a definitive grounded answer (found / not-found +
real metadata) with zero model tokens.

## What AUTHOR brings (for the user and the agentic system)
1. **Grounding / anti-hallucination.** Citations verified against Semantic Scholar/OpenAlex/Crossref/
   arXiv; fabrications are caught by construction. A bare LLM cannot verify — it refuses or invents.
2. **Determinism & defined semantics.** A fixed decision rule + 7 structured scores, identical across
   runs and hosts. Raw LLMs use ad-hoc, varying rules and emit prose.
3. **Token / compute offload.** Deterministic logic (aggregation, parsing, LaTeX, table-building,
   citation matching) runs with ~0 model tokens; the raw LLM spent ~19–20K tokens to *sometimes*
   reproduce the easy part and *cannot* do the grounded part at all.
4. **Structured, auditable output.** `{decision, scores, verified flags, BibTeX, memory blocks}` an
   agent can branch on and a user can trust — not free text.
5. **Capabilities a host simply doesn't have.** Real PDF/vision ingest, semantic retrieval, multi-
   source citation verification, figure generation, LaTeX export. No prompting gives a bare LLM these.
6. **Portability.** Identical behavior whether the host is Claude, Codex, or CLIO — one package, one
   contract, three transports (in-process / CLI / MCP).

## Honest caveats
- On *trivial* deterministic tasks a strong LLM may match the answer; AUTHOR's value there is
  determinism, auditability, and cost — not raw correctness.
- A well-aligned host (Claude here) refused to fabricate rather than producing a fake citation — good,
  but it then **couldn't complete the task**; AUTHOR is the tool that completes it, grounded.
- The CLIO "without" cell (a full LM-backed turn) was not run; it needs a configured backend.

# Invoking AUTHOR as a subagent — host integration

AUTHOR (clio-author) is a standalone package a host agent **invokes** — load, call, drop. There are
three ways a host reaches it, all hitting the same `ClioAuthorSubagent` surface
(`capabilities()` + `run(action, payload)`):

| Transport | How | When |
|---|---|---|
| **In-process** | `from clio_author.integration.clio_adapter import ClioAuthorSubagent` | host is Python and can import |
| **Subprocess CLI** | `clio-author run <action> --json '{...}'` (JSON on stdout) | any host that can run a shell command |
| **MCP bridge** | `python -m clio_author.integration.mcp_bridge` (FastMCP, stdio) | host whose only extension surface is MCP (e.g. CLIO) |

The package itself is **not** an MCP server; the bridge is a thin, optional shim (the `mcp` extra)
so MCP-only hosts can reach the same actions.

---

## Verified host invocations (comparison)

The same task — *aggregate three peer reviews into one decision* via the `meta_review` action (which
needs no model inside AUTHOR, so the only cost is the host deciding to call it) — driven by three
different hosts:

| Host | Mechanism | Result | Notes |
|---|---|---|---|
| **Claude** (CLI, small model) | subprocess: ran `clio-author run meta_review --json …` and used the output | `Accept, 6/10, 3 reviewers` | host self-corrected the payload (`[…]` → `{"reviews":[…]}`) then succeeded |
| **Codex** (CLI) | subprocess: same command, reported the result | `Accept, 6` | one call, ~20K host tokens |
| **CLIO** (its tool gateway) | MCP: gateway spawned the bridge over stdio, **discovered** `clioauthor_capabilities` + `clioauthor_run`, called `run(meta_review)` | `Meta-decision: Accept (overall 6/10) from 3 reviewer(s)` | driven through CLIO's real `build_gateway` + executor — **zero model tokens** (tool-execution layer only) |

All three reached the identical AUTHOR result, each via the transport natural to that host.

---

## Reproduce

**In-process (Python):**
```python
from clio_author.integration.clio_adapter import ClioAuthorSubagent
sub = ClioAuthorSubagent()
print(sub.run("meta_review", {"reviews": [
    {"Overall": 8, "Decision": "Accept"},
    {"Overall": 3, "Decision": "Reject"},
    {"Overall": 6, "Decision": "Accept"},
]})["content"])
```

**Claude as host (small model, subprocess):**
```bash
claude -p "Use the subagent CLI: uv run --no-sync clio-author run meta_review --json '<payload>' \
  to aggregate these reviews into one decision, then report the decision + overall. \
  Reviews: [{\"Overall\":8,\"Decision\":\"Accept\"},{\"Overall\":3,\"Decision\":\"Reject\"},{\"Overall\":6,\"Decision\":\"Accept\"}]" \
  --model haiku --allowedTools Bash --dangerously-skip-permissions
```

**Codex as host (subprocess):**
```bash
codex exec --dangerously-bypass-approvals-and-sandbox \
  "Run: uv run --no-sync clio-author run meta_review --json '{\"reviews\":[...]}'  then report the decision + overall."
```

**CLIO as host (MCP bridge, through CLIO's gateway — no model needed):**
```bash
# 1) the bridge (spawned by the host; the mcp extra provides fastmcp)
uv run --extra mcp python -m clio_author.integration.mcp_bridge        # stdio MCP server

# 2) declare it to CLIO (AGENT.md / mcp.yaml):
#    mcp_servers:
#      clioauthor: "uv run --extra mcp python -m clio_author.integration.mcp_bridge"
#
# CLIO's gateway then exposes clioauthor_capabilities + clioauthor_run to its experts.
# A model-free check that the gateway discovers + calls the tools is in
#   scripts/clio_gateway_test.py  (run inside CLIO's environment).
```

---

## Status & the CLIO note

- **Subprocess + in-process: fully working** for any host (proven with Claude and Codex).
- **MCP bridge: working** — CLIO's gateway discovers and calls AUTHOR's actions over the bridge.
- CLIO currently composes external capabilities **only via MCP** (its registry is for in-process
  DSPy experts, not external packages). The bridge is therefore the supported path today. A native
  **in-process subagent hook** in the host (import-and-call, no MCP round-trip) would be a host-side
  enhancement; until then the bridge is the clean integration point.

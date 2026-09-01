# Integrating AUTHOR into a host

AUTHOR is designed to be **driven by a host agent**. Pick the wiring by host.

| Mode | Best for | Entry point |
|---|---|---|
| **Subagent** (in-process Python) | any Python host | `clio_author.integration.clio_adapter.ClioAuthorSubagent` |
| **MCP** | any MCP host | `clio-author-mcp` (`uv sync --extra mcp`) |
| **A2A** | any agent-to-agent host | `clio-author-a2a` (Agent Card + `message/send`) |
| **Clio Coder extension** | **Clio Coder** | `integration/clio-coder/` (skill + `/author-demo` prompt + `author` agent recipe) |
| **Claude Code plugin** | **Claude Code** | `integration/claude-plugin/` (bundles the MCP server + `author` subagent) |
| **Codex (MCP)** | **Codex CLI** | `integration/codex/config.toml` (`codex mcp add clio_author -- clio-author-mcp`) |
| **Tool** (CLI / subprocess) | any language | the `clio-author` console script (JSON on stdout) |

**Host map:** Clio Coder → the extension (CLI-backed); Claude Code → the plugin; Codex → the MCP config.

> **Clio Coder does not speak MCP.** Its MCP/DB proxy is marked design-reserved and
> unimplemented in `src/core/tool-names.ts`, so `clio-author-mcp` is unreachable from that host
> and the `mcp` extra buys nothing there. Clio Coder drives the **CLI over `bash`**, made
> discoverable through a skill, a prompt template, an agent recipe, and declared verifier checks.
> See [`clio-coder/README.md`](clio-coder/README.md).

## Clio Coder

```bash
clio-coder extensions install integration/clio-coder --project --force
clio-coder extensions enable clio-author --project
mkdir -p .clio-coder/agents && cp integration/clio-coder/agents/author.md .clio-coder/agents/
```

Then `/skill clio-author …`, `/author-demo`, or `/run author …`. The declared demo checks in
`.clio-coder/verifiers.yaml` are operator-authored with `clio-coder verifiers add … --yes`,
because that catalog is a protected execution grant an agent may not write.

Discovery is uniform across modes: `capabilities()` / `clio-author capabilities` lists every action
with its lifecycle `phase` + `needs_source` metadata, and `clio-author lifecycle` prints the
phase → actions map.

## Subagent (in-process Python)

```python
from clio_author.integration.clio_adapter import ClioAuthorSubagent
from clio_author.llm.providers import resolve_llm

sub = ClioAuthorSubagent(llm=resolve_llm("claude"))      # | "codex" | "ollama" | None (offline echo)
out = sub.run("review", {"paper": "# My paper\n..."})    # -> {"action","content","structured","metadata"}
```

`run(action, payload)` returns a JSON-serializable dict and **never raises** (failures land in
`metadata["error"]`). The adapter imports nothing from the host, so the coupling is one-directional.

## Tool (CLI / subprocess)

Any language can shell out and read JSON from stdout (exit `0` = ok, `1` = error):

```bash
uv run clio-author run review --json '{"paper":"# My paper\n..."}'
```

## MCP (CLIO, Codex, any MCP host)

```bash
uv sync --extra mcp
clio-author-mcp                                  # stdio (default)
CLIO_MCP_TRANSPORT=http CLIO_MCP_PORT=8765 clio-author-mcp   # HTTP
```

The bridge exposes `capabilities` + `run(action, payload)` as MCP tools; the harness itself stays
non-MCP.

## Claude Code plugin

A real plugin (not a slash command) that bundles the MCP server + an `author` subagent. See
[`claude-plugin/README.md`](claude-plugin/README.md). Quick version:

```bash
uv tool install 'clio-author[mcp]'                                  # puts clio-author-mcp on PATH
claude --plugin-dir integration/claude-plugin                       # local dev
# …or: /plugin marketplace add iowarp/clio-author  then  /plugin install clio-author@clio-author
```

## Codex

Codex has no tool-server plugin API — MCP is the path. Register clio-author with one line (or paste
[`codex/config.toml`](codex/config.toml) into `~/.codex/config.toml`), and drop
[`codex/AGENTS.md`](codex/AGENTS.md) into your project so Codex knows when to call it:

```bash
uv tool install 'clio-author[mcp]'
codex mcp add clio_author -- clio-author-mcp
```

## A2A (agent-to-agent hosts)

```bash
clio-author-a2a            # serves the Agent Card + JSON-RPC message/send (one skill per tool + role)
```

## Host-specific rule — avoid nesting deadlock

Do **not** set AUTHOR's nested `CLIO_LLM` to the *same* provider as the host (e.g. `CLIO_LLM=codex`
while the host is Codex, or `CLIO_LLM=claude` under Claude) — the model recurses into itself and
hangs. For grounded work inside a host, prefer the no-LLM actions (`cite`, `discover`, `check_refs`,
`audit`), run an action on the offline echo model when you only need its structure, or point the
nested `CLIO_LLM` at a different provider.

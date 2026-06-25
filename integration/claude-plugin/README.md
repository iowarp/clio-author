# clio-author — Claude Code plugin

Exposes the clio-author harness to **Claude Code** as MCP tools (`capabilities` +
`run`) and an **`author` subagent**. It bundles only the MCP server — no slash
commands — so Claude calls clio-author's 24 tools + 7 roles as native tools.

## Prerequisite

clio-author must be installed so the `clio-author-mcp` command is on your `PATH`,
with the MCP extra:

```bash
uv tool install 'clio-author[mcp]'      # or: pipx install 'clio-author[mcp]'
# (from a clone) uv sync --extra mcp  &&  uv tool install --editable '.[mcp]'
```

Verify: `clio-author-mcp --help` (or that `clio-author-mcp` starts and waits on stdio).

## Install the plugin

**Local (development):**
```bash
claude --plugin-dir /path/to/clio-author/integration/claude-plugin
```

**Via marketplace:**
```
/plugin marketplace add iowarp/clio-author
/plugin install clio-author@clio-author
```

Then use it: ask Claude to "use the author subagent to review paper.md", or call
the `capabilities` / `run` MCP tools directly. The plugin starts the
`clio-author` MCP server automatically when enabled.

## What it provides

- **MCP server `clio-author`** — `capabilities()` (the action/role menu) and
  `run(action, payload)` (dispatch any of the 24 tools or 7 roles).
- **`author` subagent** (`agents/author.md`) — a paper-lifecycle agent that drives
  those tools, prefers roles for multi-step work, and never invents citations.

See the repo's `docs/RUNBOOK.md` for every action and `docs/USAGE.md` for payloads.

# Integrating AUTHOR into a host

AUTHOR is designed to be **driven by a host agent**. There are four ways to wire it in; pick by host.

| Mode | Best for | Entry point |
|---|---|---|
| **Subagent** (in-process Python) | CLIO, any Python host | `clio_author.integration.clio_adapter.ClioAuthorSubagent` |
| **Tool** (CLI / subprocess) | any language, any host | the `clio-author` console script (JSON on stdout) |
| **Slash command** | Codex, Claude Code | `integration/codex/author.md`, `integration/claude/author.md` |
| **MCP** | MCP-only hosts | `clio_author.integration.mcp_bridge` (`uv sync --extra mcp`) |

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

## Slash command (Codex / Claude Code)

Both files are ready-to-use command prompts that drive the CLI and report the JSON result.

- **Codex** — install `integration/codex/author.md` as a Codex prompt/command, then `/author <task>`.
- **Claude Code** — copy `integration/claude/author.md` to `.claude/commands/author.md` (project) or
  `~/.claude/commands/author.md` (user), then `/author <task>`.

## MCP (MCP-only hosts)

```bash
uv sync --extra mcp
uv run python -m clio_author.integration.mcp_bridge            # stdio (default)
CLIO_MCP_TRANSPORT=http CLIO_MCP_PORT=8765 uv run python -m clio_author.integration.mcp_bridge   # HTTP
```

The bridge exposes the same actions as MCP tools; the harness itself stays non-MCP.

## Host-specific rule — avoid nesting deadlock

Do **not** set AUTHOR's nested `CLIO_LLM` to the *same* provider as the host (e.g. `CLIO_LLM=codex`
while the host is Codex, or `CLIO_LLM=claude` under Claude) — the model recurses into itself and
hangs. For grounded work inside a host, prefer the no-LLM actions (`cite`, `discover`, `check_refs`,
`audit`), run an action on the offline echo model when you only need its structure, or point the
nested `CLIO_LLM` at a different provider.

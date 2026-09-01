# clio-author in Clio Coder

Clio Coder drives clio-author as a **CLI over `bash`**, not over MCP.

Clio Coder has no MCP client — its MCP/DB proxy is marked design-reserved and
unimplemented in `src/core/tool-names.ts`. The `.mcp.json` in
[`../claude-plugin/`](../claude-plugin/) and the `[mcp_servers]` block in
[`../codex/config.toml`](../codex/config.toml) do not apply to this host. The
`mcp` extra buys you nothing here; `uv sync` alone is enough.

A Claude Code plugin bundles an MCP server, subagents, and slash commands in one
manifest. Clio Coder splits that into three delivery mechanisms, because a Clio
Coder **extension** carries prompts and skills only
(`ExtensionResourceKind = "skills" | "prompts" | "themes"`).

| Piece | Delivered by | Lands at |
|---|---|---|
| Skill + slash command | extension (`clio-coder-extension.yaml`) | enabled extension resource roots |
| `author` agent recipe | manual copy or share archive | `.clio-coder/agents/author.md` |
| Declared demo checks | `clio-coder verifiers add` (operator only) | `.clio-coder/verifiers.yaml` |

## Install

```bash
# 1. the extension: skill + /author-demo prompt
clio-coder extensions install integration/clio-coder --project --force
clio-coder extensions enable clio-author --project

# 2. the agent recipe (extensions cannot carry agents)
mkdir -p .clio-coder/agents && cp integration/clio-coder/agents/author.md .clio-coder/agents/
```

### 3. The declared checks — operator only

`.clio-coder/verifiers.yaml` is a **protected path**. A Clio agent cannot write it, and
confirmation cannot override the block: the catalog is an execution grant, so authoring it
is reserved to the operator. Copying it from this directory by hand is refused with
`write denied by readOnlyPaths entry .clio-coder/verifiers.yaml`.

Use the authoring command instead. Each `add` prints an authority preview and writes only
when repeated with `--yes`:

```bash
clio-coder verifiers add --id author-capabilities \
  --description "clio-author exposes its 24 actions and 7 roles" \
  --command '["uv","run","clio-author","capabilities"]' --tags demo,author --yes

clio-coder verifiers add --id author-lifecycle \
  --description "Print the author-lifecycle phase to action map" \
  --command '["uv","run","clio-author","lifecycle"]' --tags demo,author --yes

clio-coder verifiers add --id test-author \
  --description "Run the clio-author test suite" \
  --command '["uv","run","pytest","-q"]' --tags test,python --yes

clio-coder verifiers add --id author-grounding-benchmark \
  --description "End-to-end grounding benchmark against cite-only and claim-only baselines" \
  --command '["uv","run","python","scripts/benchmark_grounding.py"]' --tags demo,benchmark --yes
```

`clio-coder verifiers author` discovers the pytest runner from `pyproject.toml` and proposes
most of this for you. The `verifiers.yaml` in this directory is the reference copy of the
intended result, not something to install.

Confirm:

```bash
clio-coder extensions list  # -> clio-author  project  active  0.4.0
clio-coder skills list      # -> clio-author  package  extension  trusted
clio-coder agents           # -> author  custom/science/workspace-edit/balanced
clio-coder verifiers validate
```

## Agent recipe schema

`agents/author.md` follows the strict recipe parser in `src/domains/agents/recipe-schema.ts`,
not the abbreviated example in `docs/built-in-agents.md`. Every one of `version`, `name`,
`description`, `tools`, `skills`, `audience`, `category`, `capabilityClass`, `latencyClass`,
`projectContextTier`, `budget`, `resultContract`, and `tags` is **required**, and unknown keys
are rejected outright — `thinkingLevel` from the docs example quarantines the recipe.

Two further constraints before editing it:

- A project recipe must declare `audience: custom`. Audience follows where the recipe was
  discovered and cannot be claimed as `base`.
- `tools` is an object, not a flat list, and a `workspace-edit` agent must require `read` and
  `write|edit`: `required: [bash, read, {anyOf: [write, edit]}]`.

A malformed recipe is quarantined with its reason printed by `clio-coder agents`, not silently
dropped.

## Install the skill on its own

The skill is the smallest useful unit: it teaches any Clio Coder session how to drive
clio-author, with no extension, agent recipe, or checkout required. This is the right
choice for **someone who wants to use clio-author from their own paper workspace**.

### From GitHub

`clio-coder extensions install` takes a **local path only**, but `clio-coder skills install`
also accepts a GitHub URL. It must be a `blob`/`tree` URL naming the directory that contains
`SKILL.md`; a bare repository URL is rejected.

```bash
# install for your whole machine — every repo you open gets it
clio-coder skills install \
  https://github.com/iowarp/clio-author/tree/main/integration/clio-coder/skills/clio-author \
  --user

# or scope it to one repository
clio-coder skills install \
  https://github.com/iowarp/clio-author/tree/main/integration/clio-coder/skills/clio-author \
  --project

# rejected — no path component
clio-coder skills install https://github.com/iowarp/clio-author --project
```

`raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` works too.

> **The URL must point at a branch that actually carries the path.** The installer clones the
> repo and reports
> `has no integration/clio-coder/skills/clio-author; the source-url may name a path that branch
> does not carry`
> when it does not — which is what you get if you point it at a branch predating this
> integration, or at a fork that has not picked it up.

### From a clone

```bash
clio-coder skills install integration/clio-coder/skills/clio-author --user
```

### Scope

| Flag | Lands at | Use when |
|---|---|---|
| `--user` | `<configDir>/skills/clio-author/` | you write papers in many repos — **the usual choice** |
| `--project` | `.clio-coder/skills/clio-author/` | one repo should carry it for the whole team |

`--project` inside a checkout that also has the extension installed will shadow it and print
`clio-author from clio/project overrides extension/package`. Pick one delivery, not both.

### After installing

The installer stamps provenance into the copy it writes and leaves the audit unset:

```yaml
clio:
  source-url: "https://github.com/iowarp/clio-author/tree/main/…"
  installed-at: "…"
  installed-hash: "…"
  audit: unknown
```

It prints `audit is set to unknown; review the skill and set audit: pass yourself`. That is
the intended workflow — read the skill you just installed, then set `audit: pass`. Keep the
rest of the `clio:` block so `clio-coder skills update clio-author` can tell your edits from
an upstream change.

Verify and use:

```bash
clio-coder skills list      # -> clio-author  user  clio  trusted  model
clio-coder skills inspect clio-author
```

```text
/skill clio-author verify the citation "Attention Is All You Need"
```

The skill alone gives you `/skill clio-author …` and model-visible routing. It does **not**
give you the `author` agent or the `/author-demo` prompt — those need the extension and the
recipe copy above.

### Prerequisite

The skill drives a binary; it does not vendor one. `clio-author` must be on `PATH`, or the
session must sit in a clone where `uv run clio-author` resolves:

```bash
uv tool install 'clio-author[pdf,scholar,viz]'
```

## Use

```text
/skill clio-author verify the citation "Attention Is All You Need"
/author-demo deterministic
/run author ingest arXiv 1706.03762 and peer-review it
```

or `verify(check="author-capabilities")` for a gate rather than a narration.

## Model selection

Text actions need `CLIO_LLM`; the default is an offline echo placeholder. Never point it
at the provider driving the Clio Coder session — that recurses and hangs. Use `codex` or
`ollama`:

```bash
export CLIO_LLM=codex
```

Declared checks in `verifiers.yaml` run under a restricted environment allowlist, so
`CLIO_LLM` does not reach them. They cover the deterministic acts only; run model-backed
actions through `bash`, where the exported environment applies.

# clio-author in Clio Coder

Clio Coder drives clio-author as a **CLI over `bash`**, not over MCP. The `.mcp.json` in
`../claude-plugin/` and the `[mcp_servers]` block in `../codex/config.toml` do not apply here;
the `mcp` extra buys you nothing.

A Claude Code plugin ships one manifest. Clio Coder needs three pieces, because an extension
carries `skills | prompts | themes` only:

| Piece | Installed by | Lands at |
|---|---|---|
| Skill + `/author-demo` prompt | `clio-coder extensions install` | extension resource roots |
| `author` agent recipe | manual copy | `.clio-coder/agents/author.md` |
| Declared checks | `clio-coder verifiers add` — **operator only** | `.clio-coder/verifiers.yaml` |

---

## Prerequisite

The skill drives a binary; it does not vendor one. **clio-author is not published to PyPI**, so
it installs from a checkout or straight from git — never by bare package name.

From a clone (editable, so the tool tracks your working tree):

```bash
git clone https://github.com/iowarp/clio-author && cd clio-author
uv tool install --editable '.[pdf,scholar,viz]'
```

Or without a checkout:

```bash
uv tool install 'clio-author[pdf,scholar,viz] @ git+https://github.com/iowarp/clio-author'
```

> **Do not run `uv tool install 'clio-author[pdf,scholar,viz]'`.** With no source, uv resolves
> the name against PyPI, finds nothing, and fails with *"there are no versions of
> clio-author[pdf]"*. It removes the existing tool environment before it resolves, so running
> it **uninstalls a working clio-author and leaves nothing behind**. Recover with the editable
> command above.

Confirm:

```bash
uv tool list | grep clio-author     # clio-author v0.4.0
clio-author capabilities            # 24 actions, 7 roles
```

`clio-author` must be on `PATH`, or the session must sit in a clone where `uv run clio-author`
resolves. **Prefer the bare `clio-author`** — `uv run clio-author` uses the project venv, which
after a plain `uv sync` has no extras.

---

## Option A — skill only (any repo)

For writing papers in your own workspace. One command, no checkout.

```bash
clio-coder skills install \
  https://github.com/iowarp/clio-author/tree/main/integration/clio-coder/skills/clio-author \
  --user

clio-coder skills inspect clio-author   # then set `audit: pass` in the installed copy
```

The URL must be a `tree`/`blob` URL naming the directory that contains `SKILL.md`; a bare repo
URL is rejected. The installer stamps `audit: unknown` deliberately — read the skill, then set
`audit: pass`, keeping the rest of the `clio:` block so `skills update` can tell your edits
from an upstream change.

Gives you `/skill clio-author <task>`. Does **not** give you the `author` agent or
`/author-demo`.

| Scope | Lands at | Use when |
|---|---|---|
| `--user` | `~/.config/clio-coder/skills/clio-author/` | many repos — the usual choice |
| `--project` | `.clio-coder/skills/clio-author/` | one repo carries it for the team |

**Pick one delivery.** A user- or project-scope skill shadows an extension's copy and prints
`clio-author from clio/user overrides extension/package`.

---

## Option B — full agent setup (from a clone)

```bash
git clone https://github.com/iowarp/clio-author && cd clio-author
uv sync

# 1. extension: skill + /author-demo prompt
clio-coder extensions install integration/clio-coder --project --force
clio-coder extensions enable clio-author --project

# 2. agent recipe (extensions cannot carry agents)
mkdir -p .clio-coder/agents
cp integration/clio-coder/agents/author.md .clio-coder/agents/

# 3. declared checks — you must run these yourself
clio-coder verifiers add --id author-capabilities \
  --description "clio-author exposes its 24 actions and 7 roles" \
  --command '["uv","run","clio-author","capabilities"]' --tags demo,author --yes

clio-coder verifiers add --id test-author \
  --description "Run the clio-author test suite" \
  --command '["uv","run","pytest","-q"]' --tags test,python --yes

clio-coder verifiers add --id author-grounding-benchmark \
  --description "End-to-end grounding benchmark" \
  --command '["uv","run","python","scripts/benchmark_grounding.py"]' --tags demo,benchmark --yes
```

`.clio-coder/verifiers.yaml` is a **protected path**: a Clio agent cannot write it and
confirmation cannot override the block, because a check catalog is an execution grant.
Copying the reference `verifiers.yaml` from this directory is refused. Use `verifiers add`.
`clio-coder verifiers author` will propose most of it from `pyproject.toml`.

---

## Verify

```bash
clio-coder extensions list   # clio-author  project  active  0.4.0
clio-coder skills list       # clio-author  trusted   (no "overrides" warning)
clio-coder agents            # author  custom/science/workspace-edit/balanced
clio-coder verifiers validate
```

---

## Use

```text
/skill clio-author verify the citation "Attention Is All You Need"
/run author ingest arXiv 1706.03762 and peer-review it
/author-demo deterministic
verify(check="author-capabilities")
```

`/skill` teaches the session; `/run author` dispatches the agent and seals a receipt;
`verify(...)` runs a gate instead of narrating.

**Model:** text actions need `CLIO_LLM`; the default is an offline echo placeholder, and a
result starting with `[echo] ` means none is set.

```bash
export CLIO_LLM=claude    # safe here; codex and ollama also work
```

Clio Coder runs clio-author as a *separate subprocess*, so there is no recursion — the nesting
deadlock is specific to Claude Code hosting an MCP server in-process. Declared checks run under
a restricted environment allowlist, so `CLIO_LLM` never reaches them; they cover the
deterministic actions only.

These need no model at all: `capabilities` `lifecycle` `discover` `cite` `check-refs` `audit`
`plan_check` `export` `gather` `meta_review` `ingest`.

---

## Uninstall / fresh start

`clio-coder skills` has **no remove command** — a skill is uninstalled by deleting its
directory.

```bash
# skill
rm -r ~/.config/clio-coder/skills/clio-author      # --user
rm -r .clio-coder/skills/clio-author               # --project

# extension
clio-coder extensions remove clio-author --project

# agent recipe
rm .clio-coder/agents/author.md

# declared checks
clio-coder verifiers remove author-capabilities --yes
clio-coder verifiers remove test-author --yes
clio-coder verifiers remove author-grounding-benchmark --yes

# the binary
uv tool uninstall clio-author
```

Full reset of this repo's Clio state — codewiki, handoffs, proposals, and with `--all` the
generated `CLIO-CODER.md` too:

```bash
clio-coder context reset --all
```

Confirm you are clean:

```bash
clio-coder extensions list && clio-coder skills list && clio-coder agents
```

---

## Gotchas

| | |
|---|---|
| `uv run clio-author ingest` fails | project venv has no extras; use the bare `clio-author` |
| `[echo] ...` in a result | `CLIO_LLM` is unset |
| `overrides extension/package` warning | skill installed at two scopes; keep one |
| `skills install` rejects the URL | needs a `tree`/`blob` path, not a bare repo URL |
| `has no integration/...` on install | that branch does not carry the path |
| Recipe quarantined | every schema field is required, unknown keys are rejected, a project recipe must be `audience: custom`, and `tools` is an object: `required: [bash, read, {anyOf: [write, edit]}]` |
| First `ingest` is slow | downloads ~500 MB of Docling models; warm it before a demo |

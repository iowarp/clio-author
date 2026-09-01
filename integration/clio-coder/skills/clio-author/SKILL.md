---
name: clio-author
description: Drive the clio-author harness (24 tools + 7 roles) for scientific-paper work — ingest PDF/arXiv to Markdown, grounded Q&A, citation verification and faithfulness, peer review, grounding-integrity audit, planning, drafting, knowledge graphs, LaTeX export. Use whenever a paper, citation, bibliography, review, or rebuttal is involved.
version: 0.4.0
license: BSD-3-Clause
allowed-tools:
  - bash
  - read
  - write
  - ls
  - verify
---

# clio-author

A standalone Python harness for the scientific-paper lifecycle:
**ingest → ground → verify citations → review → plan → write → export**, all on one
shared memory-block substrate, so a claim traces end-to-end to a real source.

Clio Coder drives it as a **CLI over bash**. It is not an MCP server to this host.

## Invocation

From the repository root every command is prefixed with `uv run`:

```bash
uv run clio-author capabilities   # 24 actions, each with phase + needs_source
uv run clio-author lifecycle      # phase -> actions map
```

After `uv tool install '.[pdf,scholar,viz,mcp]'` the `uv run` prefix drops.

Every command prints JSON on stdout. Exit `0` = ok, `1` = error.

## Discover before guessing

Do not guess action names. Run `capabilities` and route by **lifecycle phase**
(frame · gather · plan · draft · strengthen · referee · respond · ship · drive),
not by remembering names.

## Canonical action names vs. subcommand names

The 24 canonical actions use underscores. Three subcommands spell them differently,
and two actions have **no direct subcommand at all**:

| Canonical action | CLI subcommand |
|---|---|
| `verify_work` | `verify-work` |
| `check_refs` | `check-refs` |
| `describe_figures` | `describe` |
| `meta_review` | *(none — use `run`)* |
| `plot` | *(none — use `run`)* |

When in doubt use the generic dispatcher, which accepts every canonical name:

```bash
uv run clio-author run <action> --json '{...}'
```

The 24 actions: `ingest gather experiment ask review meta_review rebuttal cite write
revise coherence kg plan research discover verify_work check_refs audit plan_check
cite_support describe_figures plot export orchestrate`

## Prefer roles for multi-step work, tools for one job

A role is a fixed policy that sequences several tools for you.

```bash
uv run clio-author role writer   --json '{"idea":"..."}' --out-dir demo/paper
uv run clio-author role verifier --markdown-file demo/paper.md --bibtex-file demo/refs.bib
uv run clio-author role reviewer --json '{"paper":"..."}'
```

Roles: `reader` (ingest/gather → kg or ask) · `scholar` (discover/research/cite/experiment) ·
`writer` (plan → plan_check → draft) · `verifier` (check_refs/cite_support/verify_work/audit/
coherence → one grounding score) · `reviewer` (review + meta_review) · `refiner` (revise →
coherence) · `viz` (plot + describe_figures).

## Rules

- **Never invent citations.** `cite` emits suggestions only and never overwrites a
  bibliography. Follow it with `cite_support` to confirm the source actually backs
  the claim it is attached to.
- **Follow the trail.** Every result carries `metadata.suggested_next` — the role or
  tool to run next.
- **Report the command you ran** alongside the fields you read out of the JSON.

## Model selection

Text actions need a real model. The default is an **offline echo placeholder**; if a
result starts with `"[echo] ..."` the model is unset.

```bash
export CLIO_LLM=codex      # or ollama, lmstudio, openrouter, litellm
```

**Nesting rule:** never point `CLIO_LLM` at the same provider driving this Clio Coder
session — the model recurses into itself and hangs.

These actions need **no model** and are instant and deterministic. Prefer them for
demos and for grounded checks:

`capabilities` `lifecycle` `discover` `cite` `check_refs` `audit` `plan_check`
`export` `gather` `meta_review` `ingest`

## Optional extras

Each capability is opt-in and lives in the project venv:

| Extra | Unlocks | Install |
|---|---|---|
| `pdf` | real PDF/arXiv extraction — **required for `ingest`** | `uv sync --extra pdf` |
| `rag` | semantic retrieval for `ask` | `uv sync --extra rag` |
| `scholar` | Semantic Scholar backend for `cite`/`discover` | `uv sync --extra scholar` |
| `viz` | render plot PNGs | `uv sync --extra viz` |

The first `ingest` downloads ~500 MB of Docling models. Do that **before** a demo.
Without the `pdf` extra `ingest` fails cleanly with
`"PyMuPDF is not installed. Install with: uv sync --extra pdf"`.

## Gotchas

- `orchestrate --inputs-json` takes file **content**, not paths.
- Keys live in `.env.local` (git-ignored, auto-loaded). Never pass a key on the
  command line. `SEMANTIC_SCHOLAR_API_KEY` and `GEMINI_API_KEY` are both optional.
- A global `uv tool install` has its **own venv**; `uv sync --extra ...` in the repo
  does not reach it.

## Declared checks

The deterministic acts are registered in `.clio-coder/verifiers.yaml`, so they can be
run as gates rather than narrated:

```
verify(check="author-capabilities")
verify(check="author-lifecycle")
verify(check="test-author")
verify(check="author-grounding-benchmark")
```

Project checks run under a restricted environment allowlist, so `CLIO_LLM` does **not**
reach them. Run model-backed actions through `bash`, where the exported environment applies.

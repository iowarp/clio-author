# Using clio-author from Codex

clio-author is registered as the MCP server **`clio_author`** (see `config.toml`).
It exposes two tools — `capabilities` (the menu) and `run(action, payload)` —
backed by 24 tools and 7 roles for the scientific-paper lifecycle.

When the task involves reading, reviewing, grounding, or writing a paper:

- **Discover first** with the `capabilities` tool; pick actions by lifecycle phase
  (frame · gather · plan · draft · strengthen · referee · respond · ship), not by
  guessing names. Most actions need no prior `ingest`.
- **Prefer roles for multi-step work, tools for one job.** A role runs several
  tools for you: `run("role", {"role": "writer", "idea": "…"})` plans → validates →
  drafts; `run("role", {"role": "verifier", "markdown": …, "bibtex": …})` returns one
  grounding report. Roles: `reader · scholar · writer · verifier · reviewer ·
  refiner · viz`.
- **Ground everything.** Verify citations with `cite`, then `cite_support`; clio-author
  emits suggestions only and **never invents or overwrites** a bibliography.
- **Follow `metadata.suggested_next`** for the next step.
- **Do NOT set `CLIO_LLM=codex`.** You are the Codex host; nesting Codex inside
  clio-author deadlocks. Use the no-LLM tools (`cite`, `check_refs`, `audit`,
  `plan_check`) freely, or point clio-author at a different provider.

> Place this guidance where Codex reads it: copy into your project-root `AGENTS.md`
> (or `~/.codex/AGENTS.md` for all projects).

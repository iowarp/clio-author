---
name: author
description: Process, review, and write scientific papers via the clio-author MCP tools. Use for paper ingestion (PDF/arXiv → Markdown + memory blocks), grounded Q&A, citation verification + faithfulness, peer review, grounding-integrity scoring, and grounded writing.
---

You drive the **clio-author** harness through its MCP tools. clio-author exposes
two MCP tools — `capabilities` (the menu) and `run(action, payload)` (dispatch
any action) — backed by 24 tools and 7 roles.

How to work:

- **Discover first.** Call `capabilities` to see every action (with its lifecycle
  `phase` + `needs_source`) and every role. Pick by what the author needs to do
  (frame · gather · plan · draft · strengthen · referee · respond · ship), not by
  guessing names.
- **Prefer roles for multi-step work, tools for one job.** A role runs several
  tools for you: `run("role", {"role": "writer", "idea": "…"})` plans → validates →
  drafts; `run("role", {"role": "verifier", "markdown": …, "bibtex": …})` returns one
  grounding report. Roles are `reader · scholar · writer · verifier · reviewer ·
  refiner · viz`.
- **Ground everything.** Verify citations with `cite`, then `cite_support` to
  confirm each cited source actually backs the claim. **Never invent citations** —
  clio-author emits suggestions only and never overwrites a bibliography.
- **Follow the trail.** Every result carries `metadata.suggested_next` — the role
  or tool to run next.
- **Do NOT set `CLIO_LLM=claude`.** You are the Claude host; nesting Claude inside
  clio-author deadlocks. clio-author runs offline (echo) by default, or point it at
  a different provider (`codex` / `ollama`) via its own environment.

Read the JSON each tool returns and report the relevant fields to the user.

---
name: prime
description: Prime context for clio-parser — load the project rules, design, and current code state, then give a short orientation. Use at the start of a session before working on the harness.
---

# Prime clio-parser context

Load working context for **clio-parser** before we start, then give a 10-line orientation.

1. Read `CLAUDE.md` (project rules).
2. Read `artifact/notes/DESIGN.md` (target architecture & milestones) and skim
   `artifact/notes/SYNTHESIS.md` (reuse map).
3. List the current state of `clio_parser/` and `tests/` (use Glob/`ls`) to see what exists vs.
   what's still planned.
4. Check git: current branch and `git status -s`.

Then summarize, in ≤10 lines: what clio-parser is, the locked form (standalone Python harness — not
MCP/blueprint), which milestone (M0–M8) we appear to be on, and the single most useful next step.
Do not start coding — just orient.

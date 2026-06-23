---
description: Use the AUTHOR (clio-author) subagent to ingest / ask / cite / review / write / compose papers.
allowed-tools: Bash
---

You have a standalone subagent in this repo called **AUTHOR** (the `clio-author` package). Use it to
do the requested paper task: **$ARGUMENTS**

How to call it (run from the repo root):

- Discover actions: `uv run --no-sync clio-author capabilities`
- Any action: `uv run --no-sync clio-author run <action> --json '<payload>'`
- Common subcommands:
  - `uv run --no-sync --extra pdf clio-author ingest <arxiv-id|url|title|pdf> --json '{"out_dir":"clio-out/<slug>"}'`
  - `uv run --no-sync clio-author ask --question "..." --blocks-file <blocks.json> --format prose`
  - `CLIO_SCHOLAR=auto uv run --no-sync --extra scholar clio-author cite --candidates-json '[{"title":"...","year":2020}]'`
  - `CLIO_LLM=claude uv run --no-sync clio-author review --paper-file <paper.md> --ground --format prose`
  - `CLIO_LLM=claude uv run --no-sync clio-author compose --idea "..." --out-dir clio-out/paper --latex`

Rules:
- Prefer **grounded** actions: verify any citations with `clio-author cite` before stating them; do
  not invent references.
- For prose actions set `CLIO_LLM=claude` (you are the model). **Never** set `CLIO_LLM` to the host
  you are running under if that would nest the same CLI (it can deadlock) — for grounding use the
  no-LLM `cite` action.
- Each command prints a JSON result on stdout (add `2>/dev/null` for clean JSON); read it and report
  the relevant fields. Full reference: `docs/RUNBOOK.md`.

Run the needed `clio-author` command(s), then summarize the result for me.

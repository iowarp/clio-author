Use the AUTHOR (clio-author) subagent in this repo to do the requested paper task: $ARGUMENTS

Run from the repo root (read the JSON printed on stdout and report the relevant fields):
- Discover actions: `uv run --no-sync clio-author capabilities` · phases: `uv run --no-sync clio-author lifecycle`
- Any action: `uv run --no-sync clio-author run <action> --json '<payload>'`
- Ingest a paper: `uv run --no-sync --extra pdf clio-author ingest <id|url|path> --json '{"out_dir":"clio-out/x"}'`
- Gather many sources: `uv run --no-sync --extra pdf clio-author gather --sources <a> <b> --out-dir clio-out/ctx`
- Review: `uv run --no-sync clio-author review --paper-file <paper.md> --ground --format prose`
- Cite (verify, no model): `CLIO_SCHOLAR=auto uv run --no-sync --extra scholar clio-author cite --candidates-json '[{"title":"...","year":2020}]'`

Rules:
- Pick the action by lifecycle phase — `uv run --no-sync clio-author lifecycle` (frame · gather · plan ·
  draft · strengthen · referee · respond · ship). Most actions need no prior `ingest`.
- Verify citations with `clio-author cite` and never invent them; writer/citation output is suggestions only.
- **Do NOT set `CLIO_LLM=claude`** — you are the Claude host, so nesting Claude inside AUTHOR
  deadlocks. For grounded work prefer the no-LLM actions (`cite`, `discover`, `check_refs`, `audit`),
  or run an action on the offline echo model when you only need its structure, or point the nested
  `CLIO_LLM` at a *different* provider.
- Full flag reference: `docs/RUNBOOK.md`.

Install as the `/author` slash command: copy this file to `.claude/commands/author.md` in your repo
(project scope) or `~/.claude/commands/author.md` (user scope), then run `/author <task>`.

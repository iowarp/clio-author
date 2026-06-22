Use the AUTHOR (clio-author) subagent in this repo to do the requested paper task: $ARGUMENTS

Run from the repo root:
- Discover: `uv run --no-sync clio-author capabilities`
- Any action: `uv run --no-sync clio-author run <action> --json '<payload>'`
- e.g. ingest: `uv run --no-sync --extra pdf clio-author ingest <id> --json '{"out_dir":"clio-out/x"}'`
- cite (verify, no model): `CLIO_SCHOLAR=auto uv run --no-sync --extra scholar clio-author cite --candidates-json '[{"title":"...","year":2020}]'`
- review: `uv run --no-sync clio-author review --paper-file <paper.md> --ground --format prose`

Rules: verify citations with `clio-author cite` (don't invent); read the JSON on stdout and report
the result. Do NOT set CLIO_LLM=codex (nesting deadlock); use the no-LLM `cite` for grounding.

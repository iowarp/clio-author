# Exact task prompts

## Shared task
Produce a GROUNDED peer review of `paper.md`. Output: Decision (Accept/Reject), 3 strengths,
3 weaknesses; ground ≥1 weakness in real related work. Concise (~220–250 words).

## WITHOUT AUTHOR (run in an isolated dir with only the paper; full tools)
> "Produce a GROUNDED peer review of the paper in ./paper.md … you may search the web to find/verify real prior papers …"

## WITH AUTHOR (run in the repo; full tools + the clio-author subagent)
> "Peer-review ./demo-out/eval/paper.md. Use the subagent CLI to VERIFY citations:
> `uv run --no-sync clio-author cite --candidates-json '[{"title":"…","year":YYYY}]'` (checks real
> scholarly DBs, returns num_verified). Only cite related work clio-author verifies. …"

Hosts invoked with full access: Claude `--dangerously-skip-permissions --model sonnet`;
Codex `codex exec --dangerously-bypass-approvals-and-sandbox`.

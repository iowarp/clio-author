# Agentic test — host agents with vs without AUTHOR (full tool access)

A controlled, instrumented test: two host agents (**Claude**, sonnet; **Codex**) are each given
**full tool access** (`--dangerously-skip-permissions` / `--dangerously-bypass-approvals-and-sandbox`
→ Bash, WebSearch, Read, …) and one task — **produce a grounded peer review** of `paper.md`
(Decision + 3 strengths + 3 weaknesses; ground ≥1 weakness in *real/verified* related work). Each is
run **without** AUTHOR (host does it alone) and **with** AUTHOR (may call the `clio-author` subagent).
We measure tokens, wall-time, tool-call count, errors, and **whether the grounding is verified**.

## Results

| Host | Arm | Total tokens | Wall | Tool calls | Errors | Grounding quality |
|---|---|---|---|---|---|---|
| Claude (sonnet) | without | 231,045 | 68 s | 8 | 0 | web-search snippets (**unverified**) |
| Claude (sonnet) | **with AUTHOR** | 224,217 | 64 s | 6 | 0 | `clio-author cite` → **verified vs scholarly DBs** |
| Codex | without | 47,059 | 40 s | 7 | 0 | citation **from memory** (unverified; risk of wrong id) |
| Codex | **with AUTHOR** | 35,907 | 78 s | 6 | 0 | `clio-author cite` → **verified** ("The AI Scientist", Lu et al. 2024) |
| Codex | with (1st try) | — | timeout 460 s | — | **1** | `CLIO_LLM=codex` → `review` spawned **codex-in-codex** → deadlock |

Proof each host used AUTHOR as a subagent (captured from the transcripts):
- Claude ran: `uv run --no-sync clio-author cite --candidates-json '[{"title":"AutomaTikZ…","year":2024}, …]'`
- Codex ran `clio-author cite` 6× to verify candidates before citing them.

## Findings
1. **Grounding quality is the decisive difference.** Without AUTHOR, hosts grounded in unverified web
   snippets (Claude) or a from-memory citation (Codex) — the exact hallucination risk. With AUTHOR,
   both grounded only in citations **verified against real scholarly databases**.
2. **Fewer tokens with AUTHOR** — Claude 224K vs 231K; Codex **36K vs 47K (~24% fewer)** — and
   comparable/fewer tool calls. The deterministic verification is offloaded to a no-LLM action.
3. **Integration lesson (the error row):** never configure the nested AUTHOR model to be the *same*
   host (`CLIO_LLM=codex` under Codex) — it recurses and deadlocks. Use a no-LLM action (`cite`) for
   grounding, or a different model for any nested generation.
4. **Both hosts completed the task with AUTHOR using the same `cite` contract** — portability across
   hosts (one package, one interface).

## Caveats (honest)
- This is **n=1 per cell** on one truncated paper — directional, not statistically significant. The
  benchmark plan (`docs/BENCHMARK-PLAN.md`) scales this with real datasets.
- Claude token totals are dominated by cache reads (prompt-cache), so absolute numbers are
  host-specific; compare within-host (with vs without).
- "Verified" means present in a scholarly DB via the cascade (Semantic Scholar → OpenAlex → Crossref
  → arXiv); it does not assert the citation is *apt*, only that it is real.

## Reproduce
See `prompts.md` for the exact task strings. `run.sh` runs all four arms and writes
`reviews/*.md` + `metrics.json`. Requires the `claude` and `codex` CLIs on PATH and (for the WITH
arms) `SEMANTIC_SCHOLAR_API_KEY` in `.env.local`. Full-access flags are intentional — the test is
"give the agent everything and see if AUTHOR still helps."

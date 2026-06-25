# The author lifecycle — what AUTHOR does, and when

AUTHOR is **not** a linear "ingest → … → export" pipeline. It is a toolkit a
*person* — an author — reaches into at different moments. This document tells the
story of that author and maps every capability to the phase of work it serves, so
you (or a host agent like CLIO) can pick the right action by **what you need to do
right now**, not by remembering action names.

Two things shape the whole design:

1. **An author wears two hats** — the **Writer** (producing their own paper) and
   the **Referee** (judging others'). The same toolkit serves both.
2. **You can enter at any phase.** Most jobs do **not** start with `ingest`: you
   can review pasted text, write from an idea, polish a draft, or answer reviewers
   without ever processing a PDF. Only four actions operate on a *processed*
   paper (`ask`, `kg`, `experiment`, `describe_figures`) — everything else works
   from text, an idea, or JSON you supply directly.

> This map is machine-readable. Run `clio-author lifecycle` to print it, and every
> action in `clio-author capabilities` carries a `phase` list and a `needs_source`
> flag so a host can route by phase.

---

## The story of an author

> You have a folder of experimental results and a hunch they're worth a paper.
>
> **① Frame it.** What's the story, and what's already out there? Run `research`
> for a grounded literature brief, `discover` to pull *real* candidate papers, and
> — for a competitive evaluation — `experiment` to extract how the top related
> papers designed *their* experiments. `ask` questions against them and build a
> `kg` of the concept landscape.
>
> **② Gather.** Pull in everything you'll build on — results notes, the related
> PDFs, even a code repo — with `gather` (one merged context), or a single paper
> with `ingest`.
>
> **③ Plan.** `plan` turns the idea into per-section blueprints (claims, evidence,
> word budgets); `plan_check` validates that blueprint *before* you write a word
> (every claim has a source, budgets add up); `experiment` recreates a grounded
> **evaluation plan** (datasets / baselines / metrics / ablations) for the new method.
>
> **④ Draft.** `write` section by section, or the **`writer` role** drafts the whole
> paper at once (plan → plan_check → draft) — grounded in the context from ②. Figures
> via `plot`, captions via `describe_figures`; the **`viz` role** tightens a diagram with a critic.
>
> **⑤ Strengthen it — before anyone sees it.** `revise` for clarity, `coherence`
> for cross-section consistency, `verify_work` to confirm every planned claim is
> made and supported, `check_refs` + `cite` for the bibliography, `cite_support`
> to confirm each cited source actually backs the sentence it's attached to, and an
> `audit` for completeness — or run all of that in one shot with the **`verifier`
> role** (which also rolls up one grounding-integrity score). `review` the draft as a
> hostile referee, then apply fixes with the **`refiner` role**.
>
> **⑥ Separately, referee.** A venue asks you to review submissions. Paste each
> into `review` (optionally vision-grounded on its figures), or use the **`reviewer`
> role** for a per-section pass, and as an area chair aggregate with `meta_review`.
>
> **⑦ Reviews come back.** Draft a point-by-point `rebuttal`, then `revise` the
> manuscript to incorporate it and re-run `audit`.
>
> **⑧ Ship.** `export` → `paper.tex` + `references.bib`; `--pdf` for the camera-ready.
>
> Whenever a job spans phases, `orchestrate` drives the sequence from one line.

---

## The phases (and the actions that serve them)

| Phase | The author's question | Actions |
|---|---|---|
| **① Frame** | *What's my story; what exists?* | `research`, `discover`, `ask`, `kg`, `experiment` |
| **② Gather** | *Pull in what I'll build on* | `ingest`, `gather`, `ask`, `kg`, `cite` |
| **③ Plan** | *Blueprint the paper + evaluation* | `plan`, `plan_check`, `experiment`, `research` |
| **④ Draft** | *Write & illustrate* | `write`, `plot`, `describe_figures` · roles `writer`, `viz` |
| **⑤ Strengthen** | *Make my own paper bulletproof* | `review`, `revise`, `coherence`, `verify_work`, `check_refs`, `cite`, `cite_support`, `audit` · roles `verifier`, `refiner` |
| **⑥ Referee** | *Judge others' papers* | `review`, `meta_review` · role `reviewer` |
| **⑦ Respond** | *Answer my reviewers* | `rebuttal`, `revise`, `audit` |
| **⑧ Ship** | *Camera-ready* | `export` · role `writer` |
| **⟳ Drive** | *Run a multi-step job for me* | `orchestrate` |

A few actions deliberately serve more than one phase — that is the toolkit's
strength, not a flaw:

- `review` — self-check your own draft (**⑤**) *and* referee others (**⑥**).
- `revise` — polish your draft (**⑤**) *and* incorporate rebuttal feedback (**⑦**).
- `experiment` — study others' evaluations (**①**) *and* plan your own (**③**).
- `ask` / `kg` — interrogate the field (**①**) *and* your gathered material (**②**).
- `cite` — build the bibliography (**②**) *and* verify it later (**⑤**).
- role `writer` — draft the whole paper (**④**); then `export` ships it (**⑧**).

---

## Per-phase recipes (copy-paste)

Set a model first for the LLM-backed steps: `export CLIO_LLM=claude` (or `codex` /
`ollama`). Deterministic steps (`discover`, `cite`, `check_refs`, `audit`, `gather`,
`ingest`) work with no model.

**① Frame**
```bash
clio-author discover --query "learned cache eviction" --limit 8 --out-dir clio-out/lit
clio-author research --topic "learned cache eviction" --format prose
clio-author experiment --sources 2106.09685 ./related/fastcache.pdf \
  --out-dir clio-out/eval   # study how related work evaluated (no idea yet)
```

**② Gather**
```bash
clio-author gather --sources ./notes/ ./results.md https://github.com/me/proj 2106.09685 \
  --out-dir clio-out/context        # -> context.json (a drop-in --blocks-file)
clio-author ask --question "what baselines did the related work use?" \
  --blocks-file clio-out/context/context.json --format prose
```

**③ Plan**
```bash
clio-author plan --idea "An RL cache-eviction policy for scientific data workloads" \
  --blocks-file clio-out/context/context.json --out-dir clio-out/plan
clio-author experiment --sources ./related/*.pdf \
  --idea "An RL cache-eviction policy ..." --out-dir clio-out/eval --format prose
```

**④ Draft**
```bash
clio-author role writer --json '{"idea":"An RL cache-eviction policy ..."}' \
  --out-dir clio-out/paper          # plan → plan_check → draft the whole paper
clio-author plot --json '{"spec":{"kind":"line","title":"Hit-rate vs cache size"}}'
```

**⑤ Strengthen** (your own paper, before anyone sees it)
```bash
clio-author revise --mode style --text-file clio-out/paper/sections/01-introduction.md --voice concise
clio-author coherence --markdown-file clio-out/paper/paper.md
clio-author verify-work --text-file clio-out/paper/sections/03-method.md \
  --section-plan-file clio-out/plan/plan.json
clio-author check-refs --bibtex-file clio-out/paper/references.bib --markdown-file clio-out/paper/paper.md
clio-author cite_support --markdown-file clio-out/paper/paper.md --citations-file clio-out/cite.json  # do the sources back the claims?
# …or run the whole verification pass in one shot with the verifier role:
clio-author role verifier --markdown-file clio-out/paper/paper.md \
  --bibtex-file clio-out/paper/references.bib --citations-file clio-out/cite.json --out-dir clio-out/paper
clio-author review --paper-file clio-out/paper/paper.md --format prose   # self peer-review
```

**⑥ Referee** (someone else's paper)
```bash
clio-author review --paper-file submission.md --format prose
clio-author section-review --text-file their-method-section.md --format prose
clio-author run meta_review --json '{"reviews":[{...},{...},{...}]}'
```

**⑦ Respond** (after decisions on your paper)
```bash
clio-author rebuttal --paper-file clio-out/paper/paper.md \
  --review-json '{"weaknesses":["no baseline X","unclear ablation"]}' --format prose
clio-author revise --text-file clio-out/paper/sections/04-evaluation.md \
  --critic-notes "add the baseline X comparison the reviewer asked for"
```

**⑧ Ship**
```bash
clio-author export --markdown-file clio-out/paper/paper.md \
  --bibtex-file clio-out/paper/references.bib --out-dir clio-out/camera-ready --pdf
```

**⟳ Drive** (let AUTHOR sequence a phase for you)
```bash
clio-author orchestrate --goal "ingest 2106.09685, then review it and verify its claims" \
  --out-dir clio-out/run
```

---

See [`README.md`](../README.md) §2 for the full per-action argument reference, and
[`docs/RUNBOOK.md`](RUNBOOK.md) for every flag of every subcommand.

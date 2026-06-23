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

> **Maya** has a folder of experimental results and a hunch they're worth a paper.
>
> **① She frames it.** What's the story, and what's already out there? She runs
> `research` for a grounded literature brief, `discover` to pull *real* candidate
> papers, and — because she wants a competitive evaluation — `experiment` to
> extract how the top related papers designed *their* experiments. She `ask`s
> questions against them and builds a `kg` of the concept landscape.
>
> **② She gathers.** She pulls in everything she'll build on — results notes, the
> related PDFs, even her code repo — with `gather` (one merged context), or a
> single paper with `ingest`.
>
> **③ She plans.** `plan` turns her idea into per-section blueprints (claims,
> evidence, word budgets); `experiment` recreates a grounded **evaluation plan**
> (datasets / baselines / metrics / ablations) for her new method.
>
> **④ She drafts.** `write` section by section, or `compose` the whole paper at
> once — grounded in the context from ②. Figures via `plot`, captions via
> `describe_figures`, a key diagram tightened with `figure_refine`.
>
> **⑤ She strengthens it — before anyone sees it.** `revise` for clarity,
> `coherence` for cross-section consistency, `verify_work` to confirm every
> planned claim is made and supported, `check_refs` + `cite` for the bibliography,
> an `audit` for completeness, and she even `review`s her own draft as a hostile
> referee (or loops it with `write_review` / `section_review`).
>
> **⑥ Separately, she referees.** A venue asks her to review submissions. She
> pastes each into `review` (optionally vision-grounded on its figures), does a
> focused `section_review`, and as an area chair aggregates with `meta_review`.
>
> **⑦ Her reviews come back.** She drafts a point-by-point `rebuttal`, then
> `revise`s the manuscript to incorporate it and re-runs `audit`.
>
> **⑧ She ships.** `export` → `paper.tex` + `references.bib`; `--pdf` for the
> camera-ready (or `compose --pdf` end to end).
>
> Whenever a job spans phases, `orchestrate` drives the sequence from one line.

---

## The phases (and the actions that serve them)

| Phase | The author's question | Actions |
|---|---|---|
| **① Frame** | *What's my story; what exists?* | `research`, `discover`, `ask`, `kg`, `experiment` |
| **② Gather** | *Pull in what I'll build on* | `ingest`, `gather`, `ask`, `kg`, `cite` |
| **③ Plan** | *Blueprint the paper + evaluation* | `plan`, `experiment`, `research` |
| **④ Draft** | *Write & illustrate* | `write`, `compose`, `plot`, `describe_figures`, `figure_refine` |
| **⑤ Strengthen** | *Make my own paper bulletproof* | `review`, `revise`, `coherence`, `verify_work`, `check_refs`, `cite`, `audit`, `section_review`, `write_review`, `figure_refine` |
| **⑥ Referee** | *Judge others' papers* | `review`, `section_review`, `meta_review` |
| **⑦ Respond** | *Answer my reviewers* | `rebuttal`, `revise`, `audit` |
| **⑧ Ship** | *Camera-ready* | `compose`, `export` |
| **⟳ Drive** | *Run a multi-step job for me* | `orchestrate` |

A few actions deliberately serve more than one phase — that is the toolkit's
strength, not a flaw:

- `review` — self-check your own draft (**⑤**) *and* referee others (**⑥**).
- `revise` — polish your draft (**⑤**) *and* incorporate rebuttal feedback (**⑦**).
- `experiment` — study others' evaluations (**①**) *and* plan your own (**③**).
- `ask` / `kg` — interrogate the field (**①**) *and* your gathered material (**②**).
- `cite` — build the bibliography (**②**) *and* verify it later (**⑤**).
- `compose` — draft the whole paper (**④**) *and*, with `--pdf`, ship it (**⑧**).

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
clio-author compose --idea "An RL cache-eviction policy ..." \
  --blocks-file clio-out/context/context.json --plan --out-dir clio-out/paper
clio-author plot --json '{"spec":{"kind":"line","title":"Hit-rate vs cache size"}}'
```

**⑤ Strengthen** (your own paper, before anyone sees it)
```bash
clio-author revise --mode style --text-file clio-out/paper/sections/01-introduction.md --voice concise
clio-author coherence --markdown-file clio-out/paper/paper.md
clio-author verify-work --text-file clio-out/paper/sections/03-method.md \
  --section-plan-file clio-out/plan/plan.json
clio-author check-refs --bibtex-file clio-out/paper/references.bib --markdown-file clio-out/paper/paper.md
clio-author audit --markdown-file clio-out/paper/paper.md --bibtex-file clio-out/paper/references.bib
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

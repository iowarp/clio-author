---
marp: true
title: "AUTHOR — Agentic Understanding for Thesis, Hypothesis, and Objective Research"
paginate: true
---

<!--
Render options (it also reads fine as plain Markdown):
  - Marp:   marp docs/PRESENTATION.md -o author.pdf   (or the VS Code "Marp" preview)
  - Pandoc: pandoc -t beamer docs/PRESENTATION.md -o author.pdf
Each "---" starts a new slide. 11 slides (title + 10).
-->

# AUTHOR
### Agentic Understanding for Thesis, Hypothesis, and Objective Research

A standalone, **host-invocable** multi-agent package that spans the **whole scientific-paper
lifecycle** — read → understand → verify citations → review → plan → write → illustrate → export.

*Invoked by the CLIO agent as a subagent · 18 actions · grounded, not hallucinated*

---

## 1 · What this is (and the paper)

- **AUTHOR** = one Python package that turns a paper (**arXiv link / PDF / title**) into clean
  Markdown + memory blocks, then lets specialized **expert agents** answer, verify, review, plan,
  write, illustrate, and export — all behind **one interface a host agent can call**.
- **Paper title:** *AUTHOR: Agentic Understanding for Thesis, Hypothesis, and Objective Research.*
- **Core claim:** the contribution is **unifying the lifecycle in one grounded, composable package** —
  not any single capability in isolation.
- **Status:** built end-to-end — 18 actions, ~460 hermetic tests, CI green; validated live (Claude /
  Codex / Ollama / Gemini vision / live citation backends).

---

## 2 · Motivation — why this is needed

- **Fragmentation tax.** A researcher today stitches together separate, non-interoperating tools: a
  PDF parser, a literature-QA tool, a citation auditor, a writing agent, a figure agent, a LaTeX
  exporter — none sharing a data model or interface.
- **Hallucination is the central failure.** LLM scientific writing fabricates citations at high rates
  (78–90% reported for GPT-4o; survey generators "uniformly weak" on reference quality). Trust
  requires **grounding**, not generation.
- **Hosts need a composable capability, not a closed pipeline.** A larger agent (CLIO) should be able
  to *invoke* paper-processing/writing on demand — load, use, drop.
- **One substrate, reused.** Ingest → the *same* memory blocks feed Q&A, review, and writing.

---

## 3 · The gap — nobody unifies the lifecycle

The 2024–2026 landscape splits into **three non-overlapping camps**:

| Camp | Examples | Does | Omits |
|---|---|---|---|
| **Ingest-only parsers** | Docling, MinerU | PDF→MD + vision | write / review / verify |
| **End-to-end *generators*** | AI Scientist, Agent Laboratory, CycleResearcher | ideate→experiment→write (closed) | external ingest, citation-verify, host API |
| **Single-slice specialists** | AutoSurvey, PaperBanana, CiteCheck, PaperQA2 | one capability well | everything else |

> **The quadrant {vision ingest + grounded QA + citation-verify + review + write + figures + export}
> as one host-invocable package is held by no one.** That is AUTHOR's position.

---

## 4 · Capability coverage (AUTHOR vs the field)

In=ingest · QA=grounded QA · CV=cite-verify · Rv=review · Wr=write · Fg=figures · Ex=export ·
1pkg=one package · Host=host-invocable

| System | In | QA | CV | Rv | Wr | Fg | Ex | 1pkg | Host |
|---|---|---|---|---|---|---|---|---|---|
| **AUTHOR** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** |
| AI Scientist v2 | N | N | P | Y | Y | Y | Y | P | N |
| PaperOrchestra | N | P | P | P | Y | Y | Y | P | N |
| AutoSurvey | N | Y | P | N | Y | N | N | P | N |
| PaperBanana | N | P | N | P | N | Y | P | N | P |
| Docling / MinerU | Y | N | N | N | N | N | P | Y | Y |
| PaperQA2 | N | Y | P | N | N | N | N | N | Y |

**No row but AUTHOR is all-Y.** (Full matrix + a source per cell: `docs/MOTIVATION.md`.)

---

## 5 · What we built — the 18 actions

- **Read / understand:** `ingest` (PDF→MD+blocks+figures), `ask` (grounded Q&A), `kg` (content
  knowledge graph)
- **Verify:** `cite` (S2→OpenAlex→Crossref→arXiv cascade; suggestions only, never edits)
- **Review:** `review` (decision + scores + `--ground`), `meta_review` (panel), `write_review` (loop)
- **Write:** `plan` (tasks/claims/sources), `write`, `edit`, `polish`, `coherence`, `compose`
  (whole paper), `export` (→ LaTeX)
- **Illustrate:** `plot`, `describe_figures` (Gemini vision), `figure_refine` (loop)
- **Drive:** `orchestrate` (goal → plan a sequence of the above → execute)

One adapter (`ClioAuthorSubagent.capabilities()` + `.run(action, payload)`) + a CLI — stateless,
JSON in/out, never raises.

---

## 6 · References & artifacts we built on

**Combined (the mandate):**
- *Processing* — **paper-to-md** (+ phagocyte) and **PaperBanana** (arXiv 2601.23265)
- *Writing/editing* — **wtf-p** and **PaperOrchestra** (arXiv 2604.05018)

**Harness references (concepts re-implemented, not copied):**
- **papervizagent** — orchestrator + expert agents + critic loop → our `CriticRefine` + `figure_agent`
- **protoneo/knowledge** (AGPL) — BaseAgent / deliberation patterns / knowledge graph → our
  `harness/` (Sequential·Parallel·CriticRefine·RoundRobin) + `kg`

All cloned in `artifact/repos/`; both papers in `artifact/papers/`; deep-study notes in
`artifact/notes/`. License-clean (BSD-3-Clause; no AGPL code copied).

---

## 7 · Design — how it's put together

```
host (CLIO) ──► ClioAuthorSubagent  (capabilities + run, JSON, never-raises)
                      │
                 Main agent (router)  +  orchestrate (goal → plan → execute)
                      │
   ┌─────────── expert agents ───────────┐
   ingestor · paper_qa · citation · reviewer/meta · planner ·
   writer/editor · polish · coherence · figure_agent · kg · compose · export
                      │
   backends:  retrieval (RAG + scholarly cascade) · vision (Gemini) ·
              SafeFiles (read/write/edit, sandboxed) · pluggable LLM (claude/codex/ollama/echo)
```

**Principles:** expert agents + retrieval + read/write/edit tools · grounded (verify, source-bound) ·
standalone harness, thin host bridge · hermetic-first (offline echo model + heavy paths gated).

---

## 8 · How we'll prove it — evaluation plan (why each matters)

| Track | Why we need it | Baselines |
|---|---|---|
| **PDF→MD fidelity** | ingest errors propagate to every action | paper-to-md, Docling, MinerU |
| **Figures** | high-bar, easily-judged; backs "writes a paper" | PaperBanana, DeTikZify |
| **Citation verify** | the grounding claim; hallucination is the field's top failure | CiteCheck, PaperOrchestra |
| **Review** | must track ground-truth decisions; does `--ground` help? | AgentReview, DeepReview |
| **Writing** | most visible output; parity = credible, not marketing | PaperOrchestra, AutoSurvey |
| **Orchestration + cost** | composability is part of the novelty; adopters need budgets | — |

Phasing: **Phase 0** automated metrics (now) → **Phase 1** LLM/VLM-as-Judge → **Phase 2** human
win-rates. *(Full plan: `docs/BENCHMARK-PLAN.md`.)*

---

## 9 · Justification — why this is worth doing

- **It's a real, unoccupied gap** — surveyed 20+ systems; none unify the lifecycle as one grounded,
  host-invocable package (Slides 3–4).
- **It directly fixes the trust problem** — verification + source-grounded writing vs hallucination-
  prone generators.
- **It's a reusable substrate, not a one-off** — a host (CLIO) gains paper read/review/write as
  composable, on-demand capabilities; the experts compose in any order.
- **It's already real** — built, tested, demonstrable today; the benchmark plan turns the claim into
  numbers a reviewer will accept.
- **Anticipated objection — "isn't this just tool orchestration?"** Frameworks (MCP, LangGraph) are
  domain-agnostic plumbing that ship *zero* paper-lifecycle capability. AUTHOR is the missing domain
  package; MCP is just how a host reaches it.

---

## 10 · Status & next steps

**Done:** 18 actions · ~460 hermetic tests + CI · live-validated (Claude/Codex/Ollama/Gemini, real
citation backends) · motivation + benchmark plan written · dynamic `orchestrate`.

**Next:**
1. **Demo** — prove a host agent (Claude/Codex) invokes AUTHOR as a subagent end-to-end.
2. **CLIO integration** — thin MCP bridge (CLIO invokes external capabilities via MCP); file a CLIO
   feature request for an in-process subagent hook.
3. **Benchmarks** — run Phase 0 metrics; scope datasets / judge models / human eval.

**Open decisions for discussion:** the bar (beat specialists vs parity + unification) · dataset access
(PaperBananaBench / PaperWritingBench) · human-eval resourcing.

*Repo: github.com/SIslamMun/clio-author · `docs/MOTIVATION.md`, `docs/BENCHMARK-PLAN.md`, `docs/RUNBOOK.md`*

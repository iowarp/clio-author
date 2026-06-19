# Motivation & Novelty — why AUTHOR

## The one-sentence claim
AUTHOR unifies the **entire scientific-paper lifecycle** — vision-based ingest → grounded
Q&A/retrieval → external **citation verification** → peer review → planning/writing/editing →
figure generation → LaTeX export — behind **one grounded, host-invocable package**. A survey of the
2024–2026 landscape finds **no existing system occupies this position**: the capabilities exist, but
each lives in a *separate* tool, and they do not interoperate.

## The gap (what the field looks like today)
Work splits cleanly into three non-overlapping camps:

1. **Ingestion-only parsers** — Docling ([arXiv:2408.09869](https://arxiv.org/abs/2408.09869)),
   MinerU ([2409.18839](https://arxiv.org/abs/2409.18839)): excellent PDF→Markdown with vision for
   figures/tables/equations, but they write, review, and verify *nothing*.
2. **End-to-end research *generators*** — The AI Scientist v1/v2
   ([2408.06292](https://arxiv.org/abs/2408.06292), [2504.08066](https://arxiv.org/abs/2504.08066)),
   Agent Laboratory ([2501.04227](https://arxiv.org/abs/2501.04227)), CycleResearcher
   ([2411.00816](https://arxiv.org/abs/2411.00816)), AI co-scientist, Robin, DeepScientist, Zochi,
   Carl: they ideate→experiment→write→(sometimes)review as **closed pipelines**, treat external-paper
   ingestion and citation-grounding as thin or absent, and expose **no composable tool surface**.
3. **Single-slice specialists** — survey writers (AutoSurvey
   [2406.10252](https://arxiv.org/abs/2406.10252), SurveyForge
   [2503.04629](https://arxiv.org/abs/2503.04629)), figure agents (PaperBanana
   [2601.23265](https://arxiv.org/abs/2601.23265)), citation auditors (CiteCheck
   [2605.27700](https://arxiv.org/abs/2605.27700)), literature-QA tools (PaperQA2
   [2409.13740](https://arxiv.org/abs/2409.13740), OpenScholar
   [2411.14199](https://arxiv.org/abs/2411.14199)).

**The quadrant {robust vision ingest + grounded QA + external citation-verify + review + write +
figures + export} delivered as one installable, host-invocable package is held by no one.**

## Capability coverage (condensed)
In=ingest(PDF→MD+vision) · QA=grounded QA · CV=citation-verify vs scholarly DB · Rv=review · Wr=write
· Fg=figures · Ex=export · 1pkg=one package · Host=host-invocable. (Y/P/N)

| System | In | QA | CV | Rv | Wr | Fg | Ex | 1pkg | Host |
|---|---|---|---|---|---|---|---|---|---|
| **AUTHOR** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** |
| AI Scientist v2 | N | N | P | Y | Y | Y | Y | P | N |
| Agent Laboratory | P | N | N | P | Y | P | Y | Y | N |
| PaperOrchestra | N | P | P | P | Y | Y | Y | P | N |
| AutoSurvey / SurveyForge | N | Y | P | N | Y | N | N | P | N |
| PaperBanana | N | P | N | P | N | Y | P | N | P |
| Docling / MinerU | Y | N | N | N | N | N | P | Y | Y |
| PaperQA2 / OpenScholar | N | Y | P | N | N | N | N | N | Y |
| CiteCheck (auditors) | N | N | Y | N | N | N | N | N | N |

No row other than AUTHOR is all-Y. The closest writing system (PaperOrchestra) is N on ingest/host;
the closest ingest systems do nothing downstream; citation-verify is held only by tools that do
nothing else. (Full matrix with a source per cell: see the research notes in `artifact/notes/`.)

## Why this matters — motivation points
1. **Fragmentation tax.** A researcher today chains a parser + a literature-QA tool + a citation
   auditor + a writing agent + a figure agent + a LaTeX exporter — none sharing a data model or
   interface. AUTHOR collapses these into one package over a shared memory-block substrate.
2. **No grounded, composable, host-invocable lifecycle package.** Every end-to-end generator is a
   *closed pipeline* with no tool surface; AUTHOR is explicitly invokable by a host agent as a
   composable subagent (the experts are individually callable in any order, plus a goal-driven
   `orchestrate`).
3. **Grounding vs hallucination.** Citation hallucination is empirically severe (OpenScholar reports
   GPT-4o hallucinating 78–90% of citations; survey-generation benchmarks find reference quality
   uniformly weak). Generators use scholarly DBs only to *gather* references; AUTHOR makes
   **verification against scholarly databases a first-class lifecycle stage**, and grounds writing in
   provided/ingested source material.
4. **Ingestion as the front door, not an afterthought.** The generators start from a goal/code, not
   from external papers; robust vision ingest lives only in the parsing camp, which then does nothing
   with it. AUTHOR feeds vision ingest into the *same* substrate that answers, reviews, and writes.
5. **A reusable substrate, not a one-shot generator.** Closed generators emit one artifact and stop;
   AUTHOR exposes the *capabilities themselves* (ingest, QA, verify, review, plan, write, figures,
   export) as composable experts — the "expert-agents + retrieval + read/write/edit tools"
   decomposition a host can build on.
6. **Breadth × grounding × composability, simultaneously.** Individual systems achieve one or two of
   these; the combination across the whole lifecycle is the distinguishing contribution.

## Counter-arguments (and rebuttals)
- **"Isn't this just orchestration of existing tools?"** Orchestration frameworks (MCP, LangGraph,
  AutoGen, CrewAI) are domain-agnostic *plumbing* — they ship **zero** paper-lifecycle capabilities.
  AUTHOR is the missing domain *package*; MCP is merely how a host *reaches* it (complementary).
- **"The AI Scientist already writes and reviews papers."** It *generates new* research end-to-end
  and reviews its *own* output, but does not ingest external PDFs, does no grounded QA over a given
  paper, does not verify citations against scholarly DBs, and is a closed CLI with no host-tool
  surface. It is a *generator*, not a *grounded lifecycle tool a host composes* — a different category.
- **"PaperQA2 / OpenScholar already do grounded literature QA + citations."** Excellently — but they
  verify *their own answers* against a corpus, not an external manuscript's bibliography, and do no
  vision ingest, review, writing, figures, or export. AUTHOR subsumes that slice and can use such a
  tool as a backend.
- **"Survey generators already write cited scholarly text."** From curated/abstract corpora only; they
  cannot ingest arbitrary PDFs with vision, do not verify citations against external DBs, and do no
  review/figures/export.

## Honest caveats
- Some "generators" (Zochi, Carl) are closed products; their capability cells are conservative/unknown,
  not asserted.
- PaperOrchestra has no official code release (third-party reimplementation only); the 2026 figure /
  citation-audit systems are recent preprints.
- None of this changes the verdict: **unify-the-lifecycle-as-one-grounded-host-invocable-package is
  unoccupied** — and that is the contribution AUTHOR claims.

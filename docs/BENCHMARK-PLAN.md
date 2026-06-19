# Benchmark Plan — AUTHOR (clio-author) vs. the reference systems

**Status:** proposal for discussion.

## Why benchmark at all (the argument)
AUTHOR's contribution is two-fold — **(i)** it covers the *whole* paper lifecycle as one grounded,
host-invocable package (no prior system does; see [`MOTIVATION.md`](MOTIVATION.md)), and **(ii)** each
individual capability must be *good enough to trust*. A motivation argument alone is not evidence; a
reviewer (or a user deciding to adopt it) will ask **"is each piece actually competitive, and is the
output grounded rather than hallucinated?"** This plan answers that with numbers. Concretely, benchmarking is needed to:

- **Substantiate the novelty claim** — "unifies the lifecycle" only matters if each slice is credible; we must show parity (or better) with the specialist that owns each slice.
- **Quantify grounding** — citation hallucination is the field's central failure mode; we must *measure* our verified-citation rate and source-grounding, not assert it.
- **De-risk adoption** — a host (e.g. CLIO) and its users need evidence that invoking AUTHOR yields reliable outputs.
- **Produce the evidence a paper needs** — the contribution is only publishable with a results table against named baselines.

Each track below restates **why that specific evaluation is needed** so each can be argued on its own.

---

## 1. What exists today (the honest starting point)
- `tests/baselines/test_pdf_to_md.py` — port-equivalence (our ingest matches the reference post-processing on shared cases) + a full-pipeline metrics run on 2 real PDFs (gated `baseline`/`live`).
- `clio_author/eval/report.py` — `compute_md_metrics` (sections / linked-citations / figures counts) + `build_report` (multi-system comparison table).
- The reference repos are cloned in `artifact/repos/`; both source papers in `artifact/papers/`.
- **Missing:** any executed benchmark *numbers* — no VLM-as-Judge, no figure/writing benchmarks run, no measured citation-accuracy, no review/writing win-rates. This plan closes that.

---

## 2. Five evaluation tracks (one per capability)
Each track: **why we need it · task · dataset · baselines · metrics · protocol.**

### Track 1 — PDF → Markdown fidelity (processing)
- **Why we need it:** ingestion is the front door — every downstream action consumes its memory blocks, so extraction errors propagate everywhere. We must show our blocks are as faithful as a dedicated parser; otherwise the whole lifecycle inherits garbage-in.
- **Task:** arXiv/PDF → clean scientific Markdown + structure.
- **Baselines:** paper-to-md, Docling, MinerU2.5, Nougat/olmOCR.
- **Dataset:** our 2 PDFs → ~30–50 arXiv papers across domains, with human-curated ground-truth MD for a subset.
- **Metrics:** heading/section recall, table-cell F1, equation retention, figure-extraction count, reading-order, citation-link accuracy (extends `compute_md_metrics`).
- **Protocol:** run each system on the same PDFs; score vs ground truth; report per-metric deltas. Automated.

### Track 2 — Figure generation
- **Why we need it:** figures are a high-bar, easily-judged output; a weak figure capability undermines the "writes a whole paper" claim. We need to show our generated figures are competitive with the specialist figure agent.
- **Task:** method description/spec → publication-ready figure (diagram or statistical plot).
- **Baselines:** PaperBanana, DeTikZify.
- **Dataset:** PaperBananaBench (292 methodology-diagram cases) — *access TBD*; plus our own plot specs.
- **Metrics:** VLM-as-Judge on 4 axes (faithfulness, conciseness, readability, aesthetics) → blind pairwise win-rate; for statistical plots: render-success + spec-adherence.
- **Protocol:** generate with AUTHOR (`plot`/`diagram`/`figure_refine`) vs the baseline on identical specs; a VLM judge scores blind pairs.

### Track 3 — Citation verification
- **Why we need it:** this is the grounding claim, and citation hallucination is the field's most-cited failure (78–95% hallucination rates reported). It is the single most defensible differentiator — but only if we *measure* accuracy and the coverage gain from our multi-source cascade.
- **Task:** flag citations as correct / metadata-drift / fabricated; suggest BibTeX.
- **Baselines:** PaperOrchestra (S2-only), CiteCheck, CiteGuard.
- **Dataset:** ~200 labeled citations (correct / minor-drift / fabricated); reuse a public set if available.
- **Metrics:** verification accuracy / macro-F1, the ≥90% verified-rate target, false-positive rate; **cascade coverage** (S2→OpenAlex→Crossref→arXiv) vs a single backend.
- **Protocol:** run `cite` over the labeled set; report precision/recall + coverage gain. Automated.

### Track 4 — Review quality
- **Why we need it:** review is a capability several recent systems compete on; to claim it as part of the lifecycle we must show our decisions/scores track ground truth, and that our `--ground` (retrieval-grounded) mode actually helps.
- **Task:** produce a peer review (decision + scores + critique).
- **Baselines:** AgentReview, DeepReview, human reviews.
- **Dataset:** papers with known decisions/scores (e.g. an OpenReview subset).
- **Metrics:** decision-prediction accuracy + score MAE vs ground truth; review helpfulness (LLM-judge or human); **A/B `--ground` on vs off**.
- **Protocol:** `review` N papers; compare to ground truth; report grounded-vs-ungrounded delta.

### Track 5 — Writing quality
- **Why we need it:** writing is the most visible output and the hardest to fake; the strongest writing baseline (PaperOrchestra) reports human win-rates, so parity here is what makes "AUTHOR writes papers" credible rather than marketing.
- **Task:** idea + experimental log → drafted manuscript (`compose`, optionally `--plan`/`--review`/`--latex`).
- **Baselines:** PaperOrchestra, AutoSurvey, human-written.
- **Dataset:** PaperWritingBench (200 reverse-engineered papers) — *access TBD*; else a small reverse-engineered subset.
- **Metrics:** human side-by-side win-rate (lit-review quality + overall), generated-citation accuracy, coherence (our `coherence` action as an auto-metric), word-budget adherence, planning adherence (does the draft follow the `plan`).
- **Protocol:** `compose` from bench inputs; blind human pairwise vs baselines → win-rate margins; automated proxies alongside.

### Cross-cutting — Orchestration & cost
- **Why we need it:** the unification claim includes *composability* — a host hands AUTHOR a goal and it plans the right steps. We must show `orchestrate` picks correct sequences, and report cost/latency so adopters can budget.
- **Metrics:** `orchestrate` task-completion rate on a small goal set; cost/latency per action and per full `compose` run, per model.

---

## 3. What's needed (decisions to make)
| Need | Question |
|---|---|
| **Datasets** | Are PaperBananaBench (292) and PaperWritingBench (200) public, or do we build subsets? Is there an OpenReview subset for review? |
| **Judge models** | A VLM/LLM judge (Gemini/Claude) for figures + review/writing — API budget? |
| **Human eval** | The win-rates the baselines report are *human* side-by-side. Do we have annotators / a protocol, or rely on LLM-judge proxies for now? |
| **Running baselines** | Stand up paper-to-md / Docling / MinerU / PaperBanana / PaperOrchestra (code in `artifact/repos/`) — compute + model deps. |
| **The bar** | Beat the specialists, or parity + the unification story? (Sets how hard each track must be.) |

---

## 4. Phasing (cheap → expensive)
- **Phase 0 — automated, no humans:** MD-fidelity on a small PDF set (T1); citation accuracy on a small labeled set (T3); plot render-success (T2 partial); coherence + word-budget auto-metrics (T5 partial). Scriptable now.
- **Phase 1 — LLM/VLM-as-Judge:** figures (T2) and review/writing (T4/T5) scored by a judge model (automated proxy for human eval).
- **Phase 2 — human eval:** the side-by-side win-rates (T4–T5) — the gold-standard numbers for the paper.

**Deliverable:** a `bench/` harness + a results table (AUTHOR vs each baseline, per metric) — the concrete "tested against baselines" evidence.

---

## 5. Recommendation
Start **Phase 0** now (no new datasets, no humans), and resolve the dataset / human-eval / bar
decisions in §3 to scope Phases 1–2. The unification demo (one package doing all tracks, invoked by a
host agent) is independent and already demonstrable.

# Benchmark Plan — AUTHOR (clio-author) vs. the reference systems

**Status:** proposal for discussion. **Audience:** Anthony + team.
**Why:** the mandate's second half — *"test it against these baselines"* — is currently **scaffolded but not executed** (see §1). This plan turns that into a concrete, runnable evaluation.

---

## 0. The framing (what we are actually claiming)

AUTHOR is **one cohesive package** that spans the *whole* scientific-paper lifecycle — read → understand → verify citations → review → plan → write → illustrate → export. **No single reference system does all of it**: each owns one slice. So the evaluation has two jobs:

1. **Per-capability parity/quality** — on each slice, is AUTHOR competitive with the system that specializes in it?
2. **The unification claim** — AUTHOR does all slices behind one interface (CLIO can invoke it), which none of the baselines do. This is the headline contribution and is demonstrated, not benchmarked.

> Honest stance to agree on with Anthony: is the bar **beating** each specialist, or **parity + unification** (one package, grounded, host-invocable)? That choice sets how hard each track below has to be.

---

## 1. What exists today (the honest starting point)

- `tests/baselines/test_pdf_to_md.py` — port-equivalence (our ingest matches phagocyte/paper-to-md on shared cases) + a full-pipeline metrics run on 2 real PDFs (gated `baseline`/`live`).
- `clio_author/eval/report.py` — `compute_md_metrics` (sections / linked-citations / figures counts) + `build_report` (multi-system comparison table).
- The reference repos are cloned in `artifact/repos/` (paper-to-md, papervizagent, paper-orchestra, protoneo, wtf-p, phagocyte) and both papers in `artifact/papers/`.
- **Missing:** any executed benchmark *numbers* — no VLM-as-Judge, no PaperBananaBench/PaperWritingBench run, no measured citation-accuracy, no review/writing win-rates.

---

## 2. Five evaluation tracks (one per capability)

Each track: **task · dataset · baselines · metrics · protocol**.

### Track 1 — PDF → Markdown fidelity  (processing)
- **Task:** arXiv/PDF → clean scientific Markdown + structure.
- **Baselines:** paper-to-md, Docling, **MinerU2.5**, Nougat/olmOCR.
- **Dataset:** start with our 2 PDFs → scale to ~30–50 arXiv papers across domains (cs/physics/bio) with a human-curated ground-truth MD for a subset.
- **Metrics:** heading/section recall, **table-cell F1**, equation retention, figure-extraction count, reading-order correctness, citation-link accuracy. (Extends `compute_md_metrics`.)
- **Protocol:** run each system on the same PDFs; score vs ground truth; report per-metric deltas. Fully automated.

### Track 2 — Figure generation  (PaperBanana track)
- **Task:** method description/spec → publication-ready figure (diagram or statistical plot).
- **Baselines:** **PaperBanana**, DeTikZify (code-figure cousin).
- **Dataset:** **PaperBananaBench** (292 methodology-diagram cases) — *access TBD*; plus our own plot specs.
- **Metrics:** **VLM-as-Judge** on PaperBanana's 4 axes (faithfulness, conciseness, readability, aesthetics) → blind pairwise **win-rate**; for statistical plots: render-success rate + spec-adherence.
- **Protocol:** generate with AUTHOR (`plot`/`diagram`/`figure_refine`) vs PaperBanana on identical specs; a VLM judge (Gemini/Claude) scores blind pairs.

### Track 3 — Citation verification  (PaperOrchestra track)
- **Task:** given citations, flag correct / metadata-drift / fabricated; suggest BibTeX.
- **Baselines:** PaperOrchestra (S2-only), **CiteCheck**, CiteGuard.
- **Dataset:** ~200 labeled citations (correct / minor-drift / fabricated), à la CiteCheck; reuse a public set if available.
- **Metrics:** verification accuracy / **macro-F1**, the **≥90% verified-rate** target, false-positive rate; **coverage of our cascade** (S2→OpenAlex→Crossref→arXiv) vs a single backend.
- **Protocol:** run `cite` over the labeled set; report precision/recall and coverage gains from the cascade. Automated.

### Track 4 — Review quality  (AgentReview / PaperOrchestra track)
- **Task:** produce a peer review (decision + scores + critique).
- **Baselines:** AgentReview, **DeepReview**, human reviews.
- **Dataset:** papers with known decisions/scores (e.g. an ICLR OpenReview subset).
- **Metrics:** **decision-prediction accuracy** and score **MAE** vs ground truth (CycleReviewer-style); review helpfulness (LLM-judge or human); **A/B `--ground` on vs off** (does retrieval-grounding help, à la DeepReview).
- **Protocol:** `review` N papers; compare predicted decision/score to ground truth; report grounded-vs-ungrounded delta.

### Track 5 — Writing quality  (wtf-p / PaperOrchestra track)
- **Task:** idea + experimental log → drafted manuscript (`compose`, optionally `--plan`/`--review`/`--latex`).
- **Baselines:** **PaperOrchestra**, AutoSurvey, human-written.
- **Dataset:** **PaperWritingBench** (200 reverse-engineered papers: idea+log → paper) — *access TBD*; else a small reverse-engineered subset.
- **Metrics:** human **side-by-side win-rate** (PaperOrchestra's protocol: lit-review quality + overall quality), generated-citation accuracy, **coherence** (our `coherence` action as an auto-metric), word-budget adherence, planning quality (`plan` → does the draft follow it).
- **Protocol:** `compose` from bench inputs; blind human pairwise vs baselines → win-rate margins; automated proxies (coherence/citation) alongside.

### Cross-cutting — Orchestration & cost
- **Orchestration:** does `orchestrate` pick the right action sequence for a goal (task-completion rate on a small goal set)?
- **Cost/latency:** per action and per full `compose` run, per model (claude/codex/ollama).

---

## 3. What's needed (the discussion points for Anthony)

| Need | Question |
|---|---|
| **Datasets** | Are **PaperBananaBench** (292) and **PaperWritingBench** (200) publicly available, or do we build subsets? Is there an OpenReview subset we can use for review? |
| **Judge models** | A VLM/LLM judge (Gemini/Claude) for figures + review/writing — API budget? |
| **Human eval** | The win-rates the papers report are **human** side-by-side. Do we have annotators / a protocol, or do we rely on LLM-judge proxies for now? |
| **Running baselines** | Stand up paper-to-md / Docling / MinerU / PaperBanana / PaperOrchestra (their code is in `artifact/repos/`) — local compute + their model deps. |
| **Bar** | Beat the specialists, or parity + the unification story? |

---

## 4. Phasing (cheap → expensive)

- **Phase 0 — automated, no humans, this week:** MD-fidelity metrics on a small PDF set (Track 1); citation accuracy on a small labeled set (Track 3); plot render-success (Track 2 partial); coherence + word-budget auto-metrics for `compose` (Track 5 partial). All scriptable with what we have.
- **Phase 1 — LLM/VLM-as-Judge:** figures (Track 2 full) and review/writing scored by a judge model (automated proxy for human eval).
- **Phase 2 — human eval:** the side-by-side win-rates (Tracks 4–5) — the gold-standard numbers for the paper.

**Deliverable:** a `bench/` harness + a results table (AUTHOR vs each baseline, per metric) — the concrete "tested against baselines" evidence.

---

## 5. Recommendation

Start **Phase 0** immediately (it needs no datasets we don't have and no humans), and bring the **dataset/human-eval/bar** questions in §3 to Anthony to scope Phases 1–2. The unification demo (one package doing all five tracks, invoked by a host agent) is independent and already demonstrable.

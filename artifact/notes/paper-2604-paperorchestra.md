# PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing — Close Reading Notes

**Source PDF:** `/home/shazzadul/Illinois_Tech/Summer26/RA/clio-parser/artifact/papers/2604.05018-paperorchestra.pdf` (65 pages total; ~10 pages main body + extensive appendices A–F)

---

## 1. Title, Authors, Venue/Date, Abstract

- **Title:** "PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing"
- **Authors:** Yiwen Song¹, Yale Song¹, Tomas Pfister¹, Jinsung Yoon¹ — all **Google** (single affiliation). Corresponding authors: yiwensong@, yalesong@, jinsungyoon@google.com.
- **Venue/Date:** arXiv:2604.05018v1 [cs.AI], **6 Apr 2026**. Project page: https://yiwen-song.github.io/paper_orchestra/
- **Abstract (key sentences):** "Synthesizing unstructured research materials into manuscripts is an essential yet under-explored challenge in AI-driven scientific discovery. Existing autonomous writers are rigidly coupled to specific experimental pipelines, and produce superficial literature reviews." PaperOrchestra "flexibly transforms unconstrained pre-writing materials into submission-ready LaTeX manuscripts, including comprehensive literature synthesis and generated visuals, such as plots and conceptual diagrams." It also introduces **PaperWritingBench**, "the first standardized benchmark of reverse-engineered raw materials from 200 top-tier AI conference papers." Headline numbers: "In side-by-side human evaluations, PaperOrchestra significantly outperforms autonomous baselines, achieving an absolute win rate margin of **50%–68% in literature review quality, and 14%–38% in overall manuscript quality**."

---

## 2. Problem Statement & Motivation (Limits of Prior Autonomous Writers)

Core problem: translating **unstructured pre-writing materials (raw ideas + experimental logs) into rigorous, submission-ready manuscripts** is a missing step in automated research loops. "While recent end-to-end autonomous frameworks ... establish the feasibility of automated research loops, realizing their full potential is hindered by a critical step: translating unstructured materials, such as raw ideas and experimental logs, into rigorous, submission-ready manuscripts."

Identified limits of prior work:
- **Hallucination from parametric memory:** "Early attempts ... relied on the parametric memory of LLMs, often leading to factual hallucinations." RAG systems (AutoSurvey2, LiRA) mitigate this but "these survey-specific frameworks lack the capacity to transform raw experimental data into a full-length research paper."
- **Tight coupling to experimental loops:** "full-lifecycle autonomous research agents are tightly coupled to their experimental loops, preventing them from functioning as standalone writing tools."
- **Shallow lit reviews / weak citations:** "Relying on simple keyword searches, these agents produce shallow reviews with insufficient citations."
- **No conceptual diagrams:** "They also lack the capabilities to generate conceptual diagrams, restricting visuals to code-generated data plots."
- **No standardized benchmark:** "evaluating automated writing independently remains difficult due to the absence of a standardized benchmark."

**Table 1** positions PaperOrchestra as the only system covering all five capabilities: E2E LaTeX Manuscript Gen, Decoupled Standalone Writer, Robust to Unstructured Input, Targeted Lit Review Gen, and **Conceptual Diagram Gen** (compared vs PaperRobot, data-to-paper, AI-Researcher, Cycle Researcher, AI Scientist-v2).

**Contributions (3):** (1) PaperOrchestra standalone multi-agent framework; (2) PaperWritingBench benchmark (200 papers, reverse-engineered ideas + logs); (3) Performance: absolute win margins 50%–68% (lit review) and 14%–38% (overall quality).

Related work (§2): AI Scientist-v1/v2, Cycle Researcher (RL from reviewer feedback), OmniScientist, InternAgent, AI Co-Scientist — "the writing modules in these frameworks are rigidly coupled to their internal experimental loops." Lit-synthesis: PaperRobot, Prism (OpenAI, stylistic), data-to-paper (structured backward-traceable), AutoSurvey2 (multi-stage RAG surveys), SurveyGen-I, LiRA — surveys "are not designed for writing targeted related work sections."

---

## 3. Task Formulation & The Five Agents

### Task formulation (§3.1)
Function mapping unconstrained pre-writing materials to a complete submission package. Inputs:
- **Idea Summary (I):** methodology, contributions, theoretical foundation.
- **Experimental Log (E):** raw data points, ablations, performance metrics.
- **LaTeX Template (T):** target conference template files.
- **Conference Guidelines (G):** venue requirements.
- **Figures (F):** optional pre-existing visuals; **if F = ∅, the pipeline autonomously synthesizes all visuals.**

Output: `P = (P_tex, P_pdf) = W(I, E, T, G, F)` (Eq. 1).

### Pipeline (Figure 1) — five steps; **Step 2 and Step 3 run in parallel**

1. **Step 1 — Outline Agent (Outline Generation):** Synthesizes inputs into a JSON outline with three parts: (a) a **visualization plan** (plot types, data sources, aspect ratios); (b) a **targeted literature search strategy** with macro-level + micro-level methodology clusters to guide the Lit Review Agent and build a citation map for Intro and Related Work; (c) a **section-level writing plan** with high-level content bullets and a comprehensive list of **citation hints** for all core external dependencies (baselines, datasets, metrics).

2. **Step 2 — Plotting Agent (Plot Generation, runs parallel to Step 3):** Executes the visualization plan to generate conceptual diagrams and statistical plots. Uses **PaperBanana (Zhu et al., 2026)** as the default module: "a closed-loop refinement system where a VLM critic evaluates rendered images against design objectives, iteratively revising text descriptions and regenerating images to resolve visual artifacts, and synthesizing context-aware captions."

3. **Step 3 — Literature Review Agent (runs parallel to Step 2):** Drives a "concurrent, hybrid discovery pipeline." Uses an LLM with web search to identify candidate papers, then the **Semantic Scholar API** to authenticate existence, fetch abstract/metadata, enforce temporal cutoffs, discard candidates exceeding cutoff or lacking verified mapping, deduplicate via Semantic Scholar IDs, auto-generate a `.bib` file, and **draft Intro + Related Work** from verified citations. (Full detail in §4 below.)

4. **Step 4 — Section Writing Agent (Section Writing):** Drafts remaining core sections using outputs from prior stages. "Building upon the partially filled LaTeX file, it extracts numeric values from the experimental log to construct tables." Authors abstract, methodology, experiments, conclusion; integrates generated figures into a complete LaTeX manuscript. (Per Appendix B, this is **a single comprehensive multimodal LLM call.**)

5. **Step 5 — Content Refinement Agent (Iterative Content Refinement):** Iteratively optimizes the manuscript using **simulated peer-review feedback** via **AgentReview (Jin et al., 2024)** as default. Acceptance/halting rule (quoted): "revisions are accepted if the overall score increases, or if it ties while net sub-axis gains are non-negative. The agent immediately reverts to the previous version and halts upon any overall score decrease, negative tie-breaker, or reaching the iteration limit."

### LLM call distribution per agent (Appendix B)
- Outline Agent: **1 call**
- Hybrid Literature Agent: **~20–30 calls**
- Plotting Agent: **~20–30 calls** (few-shot retrieval, visual planning, image gen, VLM critique/redraw, captioning)
- Section Writing Agent: **1 call** (single comprehensive multimodal call)
- Content Refinement Agent: **~5–7 calls** (score-driven iterative reflection)

---

## 4. Literature Review Two-Stage RAG (Candidate Discovery + Semantic Scholar Authentication) — Appendix D.3

This is the most load-bearing detail for clio-parser. The system "employs a two-phase retrieval and verification pipeline for citation gathering."

**Phase 1 — Parallel Candidate Discovery:** "First, we use **Gemini-3-Flash with Google Search grounding** to rapidly discover candidate papers based on the generated outline." Per Appendix B: "**Parallel Candidate Discovery**, which leverages **10 concurrent workers** for search-grounded LLM calls to rapidly pool candidate papers."

**Phase 2 — Sequential Citation Verification (Semantic Scholar API):** "each candidate paper undergoes strict sequential verification via the Semantic Scholar API to extract abstracts and metadata." Per Appendix B: "Sequential Citation Verification, which safely processes the pooled candidates through Semantic Scholar at **the maximum allowable rate (1 query per second)**." The endpoint (D.1) is `https://api.semanticscholar.org/graph/v1/paper/search`.

**Exact verification rules (quoted, D.3):**
- **Fuzzy title match threshold:** "each candidate must resolve to a valid Semantic Scholar entity via a **fuzzy title match (Levenshtein distance ratio > 70** (Levenshtein, 1965)), augmented by a **point-bonus for exact year alignment**."
- **Retrievable abstract requirement + date cutoff:** "To enter the final context pool, the entity must possess a **retrievable abstract** and **strictly predate the research cutoff (when specified down to the month, the system defaults to the first day of that month as the strict boundary**)."
- **Deduplication:** "gathered citations are deduplicated using unique paper ID keys."
- **≥90% verified-citation mandate:** "the system prompt strictly constrains the model to **cite only the provided verified papers**, explicitly mandating that **at least 90% of the gathered literature pool must be actively integrated and cited** when synthesizing the Introduction and Related Work sections."

**Research cutoff dates (D.1):** "We align the research cutoff dates with the official submission deadlines of each venue: **November 2024 for CVPR 2025** papers and **October 2024 for ICLR 2025** papers."

**Lit Review Agent prompt (F.1):** "YOU MUST ONLY CITE THE GIVEN collected_papers." Must cite at least `{min_cite_paper_count}` of `{paper_count}` collected papers. CRITICAL TIMELINE RULE: don't treat papers after `{cutoff_date}` as prior baselines — treat as concurrent. CRITICAL EVALUATION RULE: don't claim SOTA over a cited paper unless it's explicitly evaluated against in the experimental log.

**Model usage (D.1):** Writing backbone fixed to **Gemini-3.1-Pro** for PaperOrchestra and all baselines; literature discovery uses **Gemini-3-Flash with Google Search grounding** (also used for AI Scientist-v2 citation gathering for fairness). GPT model = `gpt-5-2025-08-07` via OpenAI API. Gemini family: `gemini-3.1-pro-preview`, `gemini-3-flash-preview`, `gemini-3-pro-image-preview` via Google Cloud Vertex AI.

---

## 5. AgentReview Simulated Peer Review & How Refinement Uses It

The main text uses **AgentReview (Jin et al., 2024)** as the default refinement evaluator in Step 5. NOTE: The paper does **not** spell out AgentReview's "5-phase simulated peer review" or "persona dimensions" explicitly in this PDF — those details belong to the cited Jin et al. 2024 paper, not reproduced here. (The task brief asked to quote these; the PDF does not contain a 5-phase / persona-dimension description, so that aspect is by-reference only.) What the PDF *does* specify:

- AgentReview produces `reviewer_feedback`: "A JSON object containing specific **Strengths, Weaknesses, Questions, and Decisions** from an LLM reviewer" (Content Refinement Agent prompt, F.1).
- **Refinement loop mechanics (Step 5):** Accept revision if overall score increases, or if tied with non-negative net sub-axis gains; revert + halt on any score decrease, negative tie-breaker, or iteration limit.
- **Content Refinement Agent prompt (F.1) — anti-reward-hacking:** The agent is told to "**Never explicitly state a limitation**" and to **ignore reviewer requests for new experiments/data not in `experimental_log.md`**. Quoted rationale: "the directive to 'never explicitly state a limitation' prevents reward hacking. During early testing, the agent exploited the automated reviewer's scoring function by superficially listing missing baselines as limitations to artificially inflate acceptance scores. Banning this behavior ... forces the agent to genuinely improve the manuscript's presentation and clarity rather than gamifying the evaluation metric." Also: "Ground Truth: All numerical claims ... MUST be verified against experimental_log.md."
- The two AI peer-review frameworks used for **holistic evaluation** (separate from refinement) are **AI Scientist-v2 Reviewer** and **ScholarPeer (Goyal et al., 2026)** — "a search-enabled multi-agent system mimicking expert workflows via iterative retrieval and evidence checking" yielding multi-axis scores, overall rating, and a simulated acceptance decision.

**Impact of refinement (§5.5 / Fig. 4):** Refined manuscripts (AfterRefine) beat unrefined (BeforeRefine) with **79%–81% win rates and 0% losses**. AgentReview metrics: simulated acceptance rate **+19% (CVPR), +22% (ICLR)**; overall score **+0.88 (CVPR 5.95→6.83) and +1.61 (ICLR 3.94→5.55)**.

---

## 6. PaperBanana Usage for Plotting/Diagrams

- **PaperBanana (Zhu et al., 2026)** is the default Plotting Agent module. Figure 1 itself was generated using PaperBanana ("This figure was generated using PaperBanana").
- Closed-loop refinement: a **VLM critic** evaluates rendered images against design objectives, iteratively revises text descriptions, regenerates images to resolve artifacts, and synthesizes context-aware captions.
- The Plotting Agent uses PaperBanana's **original prompts**, "appending only a single caption regeneration step at the end" (F.1 "Plotting Agent (Caption Generation)" prompt: caption must be concise, no "Figure X:" prefix, no markdown).
- Visualization plan (Outline Agent, Directive 1): `plot_type` MUST be exactly "plot" or "diagram"; `data_source` MUST be "idea.md", "experimental_log.md", or "both"; `aspect_ratio` from a fixed enum; `figure_id` a semantic identifier not containing "Figure".
- **Limitation (Appendix A):** "relying on external frameworks like PaperBanana ... for visual generation limits our direct control over figure hallucinations."
- **PlotOff vs PlotOn evaluation (Table 6):** PlotOff = uses human-authored GT figures; PlotOn = autonomously generated visuals. PlotOn "remains highly competitive, securing ties or wins in **51%–66% of SxS matchups** across all four setups," despite PlotOff's information advantage (GT figures embed supplementary results absent from raw logs). Table 6 numbers: CVPR PlotOff-win 34%/49% (Gemini/GPT), ICLR 35%/36%.

---

## 7. Evaluation

### PaperWritingBench (§3.2, Appendix C)
- **200 accepted papers: CVPR 2025 + ICLR 2025 (100 each).** Chosen for high academic standards and **distinct formats (double-column CVPR vs single-column ICLR)**.
- **Acquisition:** sampled from OpenReview (ICLR) and CVF Open Access (CVPR). PDFs processed with **MinerU (Wang et al., 2024)** → structured math-faithful Markdown; **PDFFigures 2.0 (Clark & Divvala, 2016)** to extract visual entities + captions. Incomplete/misparsed samples discarded.
- **Synthesizing raw materials (C.2):** raw materials generated with **Gemini-3.1-Pro**. Two controlled granularities: **Idea Summary** has a **Sparse** variant (high-level ideas only) and a **Dense** variant (retains formal definitions/LaTeX equations). **Experimental Log** de-contextualizes data into standalone factual observations. Anti-leakage: authors/titles/citations/URLs/figure refs stripped; **Structured Context Injection** feeds extracted table/figure images as multi-modal context into Gemini-3.1-Pro, flattening visual refs into factual observations.
- **Dataset statistics (Table 8):** Avg total citations **58.52±17.55 (CVPR), 59.18±20.01 (ICLR)** (~59 overall). P0 (must-cite) 14.86 (CVPR) / 13.65 (ICLR); P1 (good-to-cite) 43.66 / 45.53. Figures 5.20 (CVPR) vs 9.19 (ICLR); Tables 4.20 vs 8.13 — "ICLR ... averaging roughly twice as many figures." Word counts: Experimental Log 1529.91 (CVPR) / 2386.71 (ICLR); Dense Idea ~1083/1057; Sparse Idea ~591/587.

### Baselines (§5.1, D.2)
- **(1) Single Agent:** processes all raw materials in a single LLM call (end-to-end drafting + bibliography) — validates necessity of a multi-agent system.
- **(2) AI Scientist-v2 (Yamada et al., 2025):** SOTA; multi-round citation gathering, VLM-guided plot refinement, iterative self-reflection.
- **Human (GT)** serves as upper-bound reference.
- Standard setting = **Sparse idea**; all pipelines use a **universal anti-leakage prompt** (D.4). For fair comparison, allowable figures restricted to those from GT papers (F = F_GT).
- **Excluded baselines (D.2):** OmniScientist (no reproducible code), PaperRobot / data-to-paper (no E2E submission-ready LaTeX), AI-Researcher (requires structured intermediates), CycleResearcher (requires structured BibTeX input), generic RAG pipelines (survey-only).

### Human Evaluation (§5.4, D.5)
- **11 AI researchers** evaluated **40 randomly sampled papers (20 per venue)**; PaperOrchestra compared vs all baselines (Human GT, Single Agent, AI Scientist-v2) → **180 paired evaluations** (120 unique paper pairs). 3-point scale (Win/Tie/Loss) across Lit Review Quality and Overall Paper Quality; 12 fine-grained diagnostic questions before final holistic judgment.
- **SxS win margins (Fig. 3a / Fig. 7):** "PaperOrchestra strongly outperforms AI baselines by absolute margins of **50%–68% (Literature Review) and 14%–38% (Overall Quality)**. It also achieves a highly competitive **43% tie/win rate against human GT in literature synthesis**."
- **Correlation:** Human preferences correlate strongly with GPT-5 evaluator on Overall Quality: **Pearson r = 0.6458, Spearman ρ = 0.6355**. Lit-review correlation lower because LLMs act as "structural graders" rewarding rigid formatting (e.g., explicit "Problem-Gap-Solution" paragraphs) while human experts prefer dense, narrative factuality.

### Automated SxS (Fig. 2) & Technical Quality (Table 2)
- Automated SxS Lit Review win margins **88%–99%**; Overall Quality margins **39%–86%** (vs AI Scientist-v2) and **52%–88%** (vs Single Agent).
- **ScholarPeer simulated acceptance:** PaperOrchestra **84% (CVPR), 81% (ICLR)** — close to Human GT (**86% / 94%**); +13% (CVPR) and +9% (ICLR) over strongest autonomous baseline.

### Citation Coverage (Table 3) — KEY for clio-parser
- "autonomous baselines achieve competitive Overall F1 ... a mathematical artifact of their extremely low citation counts (**averaging 9–14**). They focus on fetching obvious P0 papers but this **inflates their F1 scores but leaves P1 Recall near zero**."
- "our framework generates **45.73–47.98 citations, closely mirroring Human (GT) writeups (~59)**." (Table 3 Avg #Cites: PaperOrchestra 47.98 CVPR / 45.73 ICLR; SingleAgent 11.46/9.75; AI Scientist-v2 14.18/13.71.)
- P0 Recall improved by absolute **2.13%–6.07%**; **P1 Recall increased by 12.59%–13.75%** over strongest baselines. "This proves our method actively explores the broader academic landscape rather than relying on shallow keyword matching."

### Lit Review Quality LLM-as-Judge (Table 4)
- Six axes (0–100): Coverage & Completeness, Relevance & Focus, Critical Analysis & Synthesis, Positioning & Novelty, Organization & Writing, Citation Practices & Rigor.
- PaperOrchestra Overall Score gains over strongest AI baseline: **+32.87 to +33.25 (Gemini-3.1-Pro), +9.66 to +9.85 (GPT-5)**; remains comparable to Human. Dominates in Citation Practices and Critical Analysis.

### Execution Time / Cost (Table 7, Appendix B)
- Single Agent: **1 LLM call, 3.3 min.**
- AI Scientist-v2: **~40–45 calls, 35.1 min.**
- **PaperOrchestra: ~60–70 calls, 39.6 min.** Architecture: outline gen, parallel literature search, sequential citation verification, writing, plotting+critique, 3× content refinement loop.
- Latency measured on 10-paper subset (5 CVPR + 5 ICLR), single worker, dropping highest/lowest times. "PaperOrchestra maintains a highly competitive mean processing time of 39.6 minutes (compared to 35.1 minutes for AI Scientist-v2)."

### Ablations (§5.5)
- **Sparse vs Dense (Table 5):** Dense dominates Overall Paper Quality (43%–56% vs 18%–24% Sparse wins) via more rigorous methodology. **Lit Review Quality near-parity** — Sparse 32%–40% vs Dense 28%–39%, showing the Lit Review Agent doesn't rely on dense input.
- **PlotOff vs PlotOn (Table 6):** autonomous visuals competitive (51%–66% tie/win).
- **Content Refinement (Fig. 4):** AfterRefine wins 79%–81%, 0% losses; +19%/+22% acceptance; +0.88/+1.61 score.

---

## 8. Limitations & Ethical Stance

### Limitations (§6 Conclusion + Appendix A)
1. **Visual hallucination control:** "relying on external frameworks like PaperBanana ... limits our direct control over figure hallucinations." Future: targeted VLMs + dedicated human eval to verify visual content is factually sound and optimally placed.
2. **Not interactive:** current refinement uses structured LLM feedback; future work = **human-in-the-loop (HITL)** so researchers steer drafts via natural-language critiques, solidifying the "advanced assistive tool rather than a fully independent writing entity" role.
3. **Pre-training data contamination risk** on PaperWritingBench (papers may be memorized). Mitigated by de-contextualization + anonymization + uniform anti-leakage prompt; future benchmarks could use unpublished research or autonomously generated raw materials.

### Ethics Statement (verbatim themes)
- "We position our system as an **advanced assistive tool** designed to accelerate the drafting process ... rather than an independent entity capable of claiming authorship."
- "Human researchers must retain full accountability for the factual accuracy, originality, and validity of the claims."
- "PaperOrchestra incorporates robust programmatic safeguards (such as **API-grounded citation validation**) to minimize hallucinations ... users are responsible for verifying the outputs to prevent the propagation of LLM-derived biases or misinformation."
- **Won't fabricate data:** Single Agent + Section Writing + Refinement prompts all enforce "Never fabricate results, numbers, baselines, datasets, or metrics" and "Do not hallucinate numbers. Use the exact values provided in the log." Refinement agent **ignores requests for new experiments** since it "lacks the capability to execute experimental code."

---

## 9. Retrieval, Grounding, Memory, Context

- **Retrieval = two-stage hybrid RAG:** parallel search-grounded discovery (Gemini-3-Flash + Google Search, 10 workers) → sequential authentication (Semantic Scholar @ 1 qps). Decoupling "combines the high-concurrency tolerance of the LLM API with the strict throughput limits of the Semantic Scholar API to prevent quota-induced latency."
- **Grounding mechanisms:**
  - Citations grounded to real Semantic Scholar entities (Levenshtein >70, retrievable abstract, date cutoff) → eliminates hallucinated references; ≥90% of verified pool must be cited.
  - Numbers grounded to `experimental_log.md` as "absolute source of truth"; "Do not hallucinate numbers."
  - Anti-hallucination citation-hint rule (Outline Agent): if exact author/title unknown, use placeholder format `"research paper or technical report introducing '[Exact Model/Dataset/Metric Name]'"` rather than guessing authors.
  - Structured Context Injection: table/figure images injected as multimodal context into the extractor (Gemini-3.1-Pro) for faithful data extraction.
- **Memory / context structure (intermediate artifacts):** The pipeline passes structured JSON/files between agents:
  - Outline Agent → JSON with `plotting_plan`, `intro_related_work_plan` (with `hook_hypothesis`, `problem_gap_hypothesis`, `search_directions`, per-cluster `limitation_hypothesis` / `limitation_search_queries` / `bridge_to_our_method`), and `section_plan` (per-subsection `content_bullets` + `citation_hints`).
  - Lit Review Agent → `citation_map.json` (BibTeX keys + titles + abstracts) + `.bib` file + partially filled `template.tex` (Intro + Related Work).
  - Section Writing Agent → full `template.tex` (single multimodal call; reads `citation_map.json` abstracts to write accurate citing sentences; uses booktabs tables).
  - Content Refinement Agent → reads `paper.tex`, `paper.pdf`, `worklog.json` (history of previous changes), `reviewer_feedback`; outputs a JSON worklog (`addressed_weaknesses`, `integrated_answers`, `actions_taken`) + full revised LaTeX.
- **Context-overlap prevention:** Outline Directive 2 strictly separates Introduction scope (macro-level, 10–20 foundational papers/surveys) from Related Work scope (micro-level, 30–50 recent SOTA baselines) so the agent searches different literature tiers.
- **Autorater grounding (F.3):** Lit Review Quality autorater uses a per-venue `{avg_citation_count}` baseline (~59) with explicit citation-count anchors and anti-inflation caps (e.g., <50% of reference avg caps coverage ≤55; descriptive-only review caps Critical Analysis ≤60; default expected overall score 45–70). Citation F1 autorater partitions GT refs into P0/P1, resolving entities via Semantic Scholar API and computing Precision/Recall/F1.

---

## Implications for clio-parser

1. **Two-stage citation pipeline is directly transferable.** The discover-then-authenticate pattern (LLM/web search to pool candidates → Semantic Scholar verification) with concrete thresholds — **Levenshtein ratio > 70, exact-year point bonus, retrievable-abstract requirement, month-floor date cutoff, dedup by Semantic Scholar paper ID, ≥90% verified-pool citation mandate** — is a concrete, parseable spec clio-parser can model/validate against. These are exactly the kinds of grounding constraints a citation parser/verifier would check.

2. **Structured intermediate artifacts are well-defined and parser-friendly.** The JSON contracts (`plotting_plan` / `intro_related_work_plan` / `section_plan`, `citation_map.json`, `worklog.json`) are explicit schemas. If clio-parser ingests multi-agent paper-writing traces, these named keys and their nesting (e.g., `section_plan[].subsections[].citation_hints[]`) give a stable target grammar.

3. **Anti-leakage / anti-hallucination prompt patterns** (treat session files as sole source of truth; placeholder citation-hint format `"research paper or technical report introducing '[X]'"`; "never state a limitation" to prevent reward hacking; ignore new-experiment requests) are useful as parser heuristics/flags for detecting grounded vs ungrounded generated text.

4. **Citation-count realism as a quality signal.** The finding that low citation counts (9–14) inflate F1 while leaving P1 recall ~0, vs PaperOrchestra's ~46–48 matching human ~59, suggests clio-parser could surface **citation-count and P0/P1 recall** as first-class extracted metrics, not just presence/absence of references.

5. **Evaluation provenance is rich.** Multiple judges (Gemini-3.1-Pro temp 0.0, GPT-5 fixed temp 1.0), AgentReview/ScholarPeer/AI Scientist-v2 reviewers, six-axis lit-review rubric with hard caps/penalties — all reported with model IDs and temperatures. If clio-parser parses evaluation sections, these are concrete fields (judge model, temperature, axis scores, acceptance rates) worth structured capture.

6. **Toolchain references** (MinerU for PDF→Markdown, PDFFigures 2.0 for figure/caption extraction) overlap with what a "parser" project likely needs — these are the same extraction primitives clio-parser would use to ingest papers; PaperWritingBench's construction pipeline is essentially a reference implementation.

---

## 10-Line Summary

1. PaperOrchestra (Google, arXiv 2604.05018v1, 6 Apr 2026) is a standalone 5-agent framework turning unstructured ideas + experimental logs into submission-ready LaTeX.
2. Agents: Outline → (Plotting ∥ Literature Review) → Section Writing → Content Refinement; Steps 2 and 3 run in parallel.
3. It targets gaps in prior autonomous writers: tight coupling to experiment loops, shallow keyword-based lit reviews, no conceptual-diagram generation, no benchmark.
4. Lit Review uses two-stage RAG: parallel Gemini-3-Flash+Google-Search discovery (10 workers) then sequential Semantic Scholar verification (1 qps).
5. Verification rules: Levenshtein title ratio >70 + exact-year bonus, retrievable abstract, strict month-floor date cutoff, dedup by paper ID, ≥90% of verified pool must be cited.
6. Plotting uses PaperBanana (VLM-critic closed-loop image refinement); refinement uses AgentReview simulated peer review (accept on score gain, revert/halt on decline; "never state a limitation" to block reward hacking).
7. Benchmark PaperWritingBench: 200 papers (100 CVPR 2025 + 100 ICLR 2025), reverse-engineered Sparse/Dense ideas + experimental logs, ~59 avg citations.
8. Human eval (11 researchers, 180 pairs): absolute win margins 50–68% (lit review), 14–38% (overall) vs AI baselines; 43% tie/win vs human GT in lit synthesis; GPT-5 judge correlates with humans r=0.65.
9. Citations: PaperOrchestra produces ~45.7–48.0 (vs baselines' 9–14, human ~59), boosting P1 recall +12.6–13.8%; runtime ~39.6 min and ~60–70 LLM calls.
10. Stance: assistive tool, humans retain accountability, API-grounded citation validation, never fabricates data/numbers; limits = visual-hallucination control, no HITL yet, contamination risk.

All 3 citations verified (3/3, ≥90% target met). Now I'll write the review.

---

## Peer Review — PaperBanana: Automating Academic Illustration for AI Scientists

**Decision: Weak Accept (Major Revision)**

---

### Strengths

1. **Well-scoped, high-impact problem.** The paper targets a genuine bottleneck in AI-driven research pipelines — publication-ready diagram generation — that prior autonomous scientist systems (Lu et al., 2024, *The AI Scientist*, 866 citations, verified) explicitly leave unsolved. The framing is sharp and the gap is real.

2. **Novel benchmark.** PaperBananaBench (292 NeurIPS 2025 methodology diagrams) is a concrete, domain-diverse contribution that the community can reuse; curating ground-truth figures from a single consistent venue controls for style variance.

3. **Principled agentic loop.** The retrieve → plan → render → self-critique pipeline mirrors best practice in agentic systems and cleanly separates content fidelity from visual aesthetics concerns.

---

### Weaknesses

1. **Understated TikZ baseline (grounded).** The paper dismisses code-based synthesis as lacking "expressiveness," but AutomaTikZ (Belouadi, Lauscher & Eger, ICLR 2024, verified, 68 citations) already achieves high-quality scientific vector graphics via LLM-guided TikZ. The paper needs quantitative comparison, not just a qualitative dismissal.

2. **Proprietary model dependency.** The pipeline relies on "Gemini-3-Pro and Nano-Banana-Pro," limiting reproducibility. No ablation with open or accessible models is described in the visible text.

3. **Evaluation operationalization unclear.** The four axes (faithfulness, conciseness, readability, aesthetics) lack definition in the provided excerpt. Whether scoring is automated (VLM-as-judge), human, or hybrid is not stated, raising concerns about evaluation validity.
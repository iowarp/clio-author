# paper-orchestra (PaperOrchestra) — Deep Study Notes

Repo: `/home/shazzadul/Illinois_Tech/Summer26/RA/clio-parser/artifact/repos/paper-orchestra`
Paper: "PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing", Song, Song, Pfister, Yoon — Google Cloud AI Research, arXiv:2604.05018 (2026).
Read-only study. Nothing in the repo was modified.

> Note on the task brief vs. reality: the brief used some labels ("PaperBanana", "AgentReview", "Levenshtein 0.7", ">=90% verified", "5-phase peer review", "PaperWritingBench") that map onto this repo loosely. I flag the exact correspondences below. The repo's AgentReview implementation is a **3-step ensemble + meta-review**, not a literal 5-phase discussion protocol; the S2 match threshold is a `thefuzz` ratio > 70 (not a Levenshtein 0.7); the "90%" is the citation-coverage requirement in the writer prompt. These are called out where they appear.

---

## 1. Purpose, tech stack, language, dependencies, license

- **Purpose**: Transform unstructured "pre-writing materials" (`idea.md` + `experimental_log.md` + optional figures) into a submission-ready LaTeX manuscript (compiled PDF) for a target conference (CVPR/ICLR templates provided). It does outline → literature review (web-grounded RAG) → figure generation → section writing → review-driven refinement.
- **Language**: Python 3.11 (Conda env `paper_orchestra`). LaTeX toolchain (`pdflatex`/`bibtex`) is invoked as a subprocess for compilation.
- **LLM backends**: Google Gemini (default `gemini-3.1-pro-preview`; image model `gemini-3-pro-image-preview`; flash `gemini-3-flash-preview` for cheap discovery/title-extraction) via `google-genai`, OR OpenAI (`openai`). Backend dispatch in `utils/llm_backend_utils.py`; Gemini client init (Vertex AI or API key) in `utils/gemini_utils.py`.
- **Key external APIs**: Semantic Scholar Graph API (`utils/scholar_utils.py`, `autoraters/citation_f1.py`); Google Search grounding tool (`types.Tool(google_search=...)`) inside the literature agent.
- **Dependencies** (`requirements.txt`): `google-genai`, `json_repair`, `matplotlib`, `openai`, `opencv-python`, `pydantic`, `PyMuPDF`, `pymupdf4llm`, `pyOpenSSL`, `pypdf`, `python-dotenv`, `rich`, `streamlit`, `thefuzz`, `tqdm`. (Note: `joblib` is imported in `citation_f1.py` but not listed.)
- **License**: Apache License 2.0 (`LICENSE`); every source file carries the "Copyright 2026 Google LLC" Apache header. README disclaimer: "not an officially supported Google product."
- **Env vars** (`.env`): `SEMANTIC_SCHOLAR_API_KEY`, `OPENAI_API_KEY`, `VERTEX_AI_PROJECT`/`VERTEX_AI_LOCATION` or `GEMINI_API_KEY`, optional `SMTP_EMAIL`/`SMTP_PASSWORD` (frontend email-on-completion).
- **Dataset**: NOT included; expected under `datasets/` (e.g. `datasets/cvpr2025/papers/...`, `datasets/iclr2025/papers/...`), referenced by `autoraters/citation_f1.py`.

## 2. Full repo structure

```
README.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, LICENSE, requirements.txt, .gitignore
paper_writing_cli.py        # main CLI entry point
paper_writing_cli.sh        # bash wrapper
assets/overview.png

methods/
  paper_writer.py                 # orchestrator WITHOUT plotting (4 sequential steps) + batch runner
  paper_writer_with_plotting.py   # orchestrator WITH plotting (lit + plotting in parallel) + batch runner
  agents/
    outline_agent.py              # OutlineAgent
    literature_review_agent.py    # HybridLiteratureAgent  (+ Pydantic models)
    section_writing_agent.py      # SectionWritingAgent
    content_refinement_agent.py   # ContentRefinementAgent (calls AgentReview)
    plotting_agent.py             # PlottingAgent (uses paper_banana_utils = "PaperBanana")
  prompts/
    outline_agent.py              # outline_agent_system_prompt (JSON schema lives here)
    literature_review_agent.py    # literature_review_agent_writter_prompt
    section_writing_agent.py      # section_writing_agent_prompt
    content_refinement_agent.py   # content_refinement_agent_system_prompt
    format_agent.py

autoraters/
  agent_review.py                 # AgentReview: reviewer persona + ensemble + meta-review
  lit_review_quality.py           # single-paper literature-review quality autorater (6 axes)
  citation_f1.py                  # citation precision/recall/F1 vs. ground-truth paper (S2 IDs, P0/P1)
  sxs_paper_quality.py            # side-by-side overall paper quality (two-order, win/tie/loss)
  sxs_lit_review_quality.py       # side-by-side lit-review quality
  prompts/
    lit_review_quality_prompts.py
    sxs_quality_prompts.py

templates/
  cvpr2025/  (template.tex, preamble.tex, cvpr.sty, ieeenat_fullname.bst, references.bib, guidelines.md)
  iclr2025/  (template.tex, iclr2025_conference.{sty,bst}, fancyhdr.sty, natbib.sty, math_commands.tex, guidelines.md, references.bib)

utils/
  gemini_utils.py            # Gemini client + call wrappers + response parsers
  openai_utils.py            # OpenAI call wrappers
  llm_backend_utils.py       # backend dispatch (call_llm_with_*), get_llm_parser
  scholar_utils.py           # s2_title_search  <-- Semantic Scholar integration (KEY)
  paper_banana_utils.py      # "PaperBanana" figure pipeline (retrieve/plan/style/generate/critique/caption)
  pdf_utils.py               # compile_latex, load_paper, pdf_to_grid_images, references extraction
  content_parsing_utils.py   # extract_paper_title_from_citation
  common_utils.py            # load_md_file, create_log_folder
  prompt_utils.py            # UNIVERSAL_NO_LEAKAGE_PROMPT (anti-leakage / anonymity)

frontend/
  app.py (1082 lines, Streamlit), frontend_utils.py, README.md
  examples/cvpr_example.json, cvpr_example_figure.png
```

## 3. The 5 agents and orchestration

Implementation files (class names):
1. **Outline** — `methods/agents/outline_agent.py` → `OutlineAgent`.
2. **Plotting** (uses "PaperBanana") — `methods/agents/plotting_agent.py` → `PlottingAgent` + module-level `process_single_figure`. The PaperBanana machinery is `utils/paper_banana_utils.py` (expects an external `PaperBanana/` dir at repo-root-parent, `PB_DIR = ../../PaperBanana`, holding `data/PaperBananaBench/{plot,diagram}/ref.json` few-shot pools, `style_guides/neurips2025_{plot,diagram}_style_guide.md`).
3. **Literature Review** — `methods/agents/literature_review_agent.py` → `HybridLiteratureAgent`.
4. **Section Writing** — `methods/agents/section_writing_agent.py` → `SectionWritingAgent`.
5. **Content Refinement** (uses AgentReview) — `methods/agents/content_refinement_agent.py` → `ContentRefinementAgent`, which calls `autoraters/agent_review.py::perform_review_agentreview`.

**Orchestration** — `write_single_paper(...)` in `methods/paper_writer.py` (no plotting) and `methods/paper_writer_with_plotting.py` (with plotting). Wrapped in a `while (not succeed) and cur_try < max_n_tries(=3)` retry loop.

Pipeline order:
- **Step 1 (sequential)**: `OutlineAgent.run(...)` → writes `outline.json` (3 top-level keys: `plotting_plan`, `intro_related_work_plan`, `section_plan`).
- **Step 2**:
  - *No-plotting variant*: `HybridLiteratureAgent.run(...)` runs alone; figures are taken from `raw_materials/figures/` (copied in).
  - *Plotting variant*: literature agent and plotting agent run **in parallel** via `ThreadPoolExecutor(max_workers=2)` — `run_literature_agent()` and `run_plotting_agent()` futures, both joined. Plot outputs (base64 → `.jpg`) are written and a `figures/info.json` (name+caption) is produced for the section writer.
  - Literature agent copies back `outline_v1.json` (citation-injected outline), `updated_template.tex` (intro+related-work now written), `references.bib`.
- **Step 3 (sequential)**: `SectionWritingAgent.run(...)` → fills remaining sections, tables, figures, citations → `raw_draft_paper.tex`.
- **Step 4 (sequential)**: `ContentRefinementAgent.run(...)` → review-driven content refinement loop, then a formatting loop, compile to final PDF → copied to `base_dir/final_paper.pdf`.

Internal parallelism: lit agent uses `ThreadPoolExecutor(max_workers=10)` for Google candidate discovery; plotting agent uses `ThreadPoolExecutor(max_workers=5)` across figures; batch runners (`run_batch_writeup`) use `ProcessPoolExecutor(max_workers=4)` across papers.

## 4. Outline agent structured JSON output

Schema is defined entirely in the system prompt `methods/prompts/outline_agent.py::outline_agent_system_prompt` (formatted with `{cutoff_date}`), appended with `UNIVERSAL_NO_LEAKAGE_PROMPT`. `OutlineAgent.run` calls `call_gemini_with_contents` and dumps `parsed_response` to `outline.json`. Three top-level keys: `plotting_plan`, `intro_related_work_plan`, `section_plan`.

Schema (quoted from the prompt's example output):

```json
{
  "plotting_plan": [
    {
      "figure_id": "fig_teaser_fig_cross_modal_alignment_performance",
      "title": "Teaser: Cross-Modal Alignment Performance",
      "plot_type": "plot",                       // MUST be exactly "plot" or "diagram"
      "data_source": "experimental_log.md",      // MUST be "idea.md", "experimental_log.md", or "both"
      "objective": "Visual summary (Radar Chart) ...",
      "aspect_ratio": "16:9"                      // one of a fixed enumerated set
    }
  ],
  "intro_related_work_plan": {
    "introduction_strategy": {
      "hook_hypothesis": "...",
      "problem_gap_hypothesis": "...",
      "search_directions": ["q1", "q2", "q3"]    // 3-5 macro queries (impact, surveys, foundational)
    },
    "related_work_strategy": {
      "overview": "...",
      "subsections": [
        {
          "subsection_title": "2.1 Autoregressive Video Generation",
          "methodology_cluster": "Discrete Tokenization & Transformers",
          "sota_investigation_mission": "...",
          "limitation_hypothesis": "...",
          "limitation_search_queries": ["...", "..."],
          "bridge_to_our_method": "..."
        }
      ]
    }
  },
  "section_plan": [
    {
      "section_title": "3. Methodology",
      "subsections": [
        {
          "subsection_title": "3.1 Temporal-Aware Attention Mechanism",
          "content_bullets": ["Define the query-key matching logic", "Explain the masking strategy"],
          "citation_hints": [
            "Vaswani et al. (Attention Is All You Need)",
            "research paper or technical report introducing 'FlashAttention-2'"
          ]
        }
      ]
    }
  ]
}
```

Key directives: (1) plotting plan picks essential figures; `figure_id` is a semantic slug, must NOT contain "Figure". (2) Intro vs Related-Work scopes are kept disjoint (macro 10-20 papers vs micro 30-50 SOTA/baselines); related work split into 2-4 methodology clusters each with a limitation hypothesis + "bridge"; a hard timeline rule forbids searching for papers after `{cutoff_date}`. (3) `citation_hints` must EXHAUSTIVELY cover every dataset, optimizer, metric, baseline, and foundational arch/model; anti-hallucination rule: use exact "Author (Title)" only if known, else `"research paper or technical report introducing '[Name]'"`.

## 5. Literature Review agent — two-stage web-grounded RAG (KEY for clio-parser)

File: `methods/agents/literature_review_agent.py` (`HybridLiteratureAgent`). Pydantic models: `CandidatePaper{title,year,reason}`, `DiscoveryResult{section_name,candidates}`, `PaperData{citation_key,title,authors,venue,year,abstract,citation_count,found_in_section,reason,journal,volume,pages,publication_date}`, `WriterOutput`.

`run(outline_path, cutoff_date)` phases:
- **Phase 1 — Discovery & Retrieval** (the two-stage RAG):
  - `_collect_search_tasks(outline)` turns the outline into search tasks of two `search_type`s:
    - `"exploration"` from `intro_related_work_plan` (intro `search_directions` and related-work `limitation_search_queries`).
    - `"targeted"` from each `section_plan` subsection's `citation_hints` (the "must-haves").
  - **Stage 1a — candidate discovery (parallel Google web searches)**: `_execute_tasks_in_parallel` → `ThreadPoolExecutor(max_workers=10)` runs `_process_search_task_google` per task (3 retries). Each calls `_discover_candidates`, which calls **`gemini-3-flash-preview`** with the **Google Search grounding tool** (`self.google_search_tool = types.Tool(google_search=types.GoogleSearch())`). `targeted` → temp 0.1, return exactly 1 best-matching paper; `exploration` → temp 0.4, return 10-15 relevant papers. Output is JSON conforming to `DiscoveryResult.model_json_schema()`. Cutoff date is injected as "Published BEFORE {cutoff_date}".
  - **Stage 1b — Semantic Scholar authentication/enrichment (rate-limited, sequential)**: for each candidate, `time.sleep(1.0)` then `_enrich_and_register_paper`, which calls `s2_title_search(cand_title, cand_year, cutoff_date)`. If S2 returns a match it must additionally pass `_is_paper_allowed` (date-cutoff re-check by year/month/day) AND have a non-empty abstract; abstracts truncated to 1500 chars. A `PaperData` is built, a citation key generated (`_generate_key`: FirstAuthorLastName + Year + first 2 meaningful title words), and de-duplicated by normalized title under a `registry_lock`.

  **Semantic Scholar integration** lives in `utils/scholar_utils.py::s2_title_search`. It hits `https://api.semanticscholar.org/graph/v1/paper/search` (`limit=3`, fields `title,authors,venue,year,abstract,citationCount,journal,publicationDate`, `X-API-KEY` header, 5s timeout) and does **fuzzy title matching** with `thefuzz.fuzz.ratio`:

  ```python
  ratio = fuzz.ratio(title_query.lower(), r["title"].lower())
  if year_hint and r.get("year") == year_hint:
      ratio += 10          # +10 bonus when the year matches
  if ratio > highest_ratio:
      highest_ratio = ratio; best_match = r
  ...
  if highest_ratio > 70:   # accept only if best fuzzy ratio > 70 (out of 100)
      return best_match
  return None
  ```
  Plus an inner `is_date_valid(publicationDate, year, cutoff_str)` that rejects anything dated on/after the `YYYY-MM` cutoff.

  > Brief's "Levenshtein 0.7": `thefuzz.fuzz.ratio` is a Levenshtein-based ratio scaled 0-100; the accept gate is `> 70`, i.e. effectively a 0.70 similarity threshold. So "Levenshtein 0.7" is accurate in spirit, threshold = 70/100.
  > Brief's ">=90% verified": this is the writer-prompt citation requirement, see below — not a discovery filter.

- **Phase 2 — Asset generation**: `_generate_bibtex` (dedups keys with a/b/c suffixes; `@article` if journal else `@inproceedings`), `_generate_citation_map` (key→{title,authors,venue,year,abstract}), and `_inject_citations_into_outline` (writes `citation_candidates` lists per section, deletes `citation_hints`).
- **Phase 3 — Writing**: `_synthesize_content` calls the writer model (`self.model_name`, default pro) with `literature_review_agent_writter_prompt` (`methods/prompts/literature_review_agent.py`) to fill ONLY Introduction + Related Work in `template.tex`. The prompt enforces:
  ```python
  min_cite_paper_count = int(len(papers) * 0.9)   # MUST cite >= 90% of collected papers
  ```
  i.e. the **">=90% verified"** coverage requirement. It also forbids citing anything outside `collected_papers`, forbids claiming SOTA over a paper not in `experimental_log.md`, and treats post-cutoff papers strictly as concurrent work.
- **Phase 4 — Saving**: writes `outline_v1.json`, `updated_template.tex`, `references.bib`, `citation_map.json` to `literature_agent_output/`.

Reusability highlight: the pattern "LLM+web-search proposes candidate titles → Semantic Scholar verifies/enriches with fuzzy title match + date cutoff + abstract presence → bibtex/citation-map" is exactly the retrieval/verification core relevant to clio-parser.

## 6. AgentReview — simulated peer review

File: `autoraters/agent_review.py`. Used by `ContentRefinementAgent` as the reward signal.

What the code actually implements (this is the operative reality):
- **Reviewer persona** via `get_agentreview_system_prompt(is_knowledgeable, is_responsible, is_benign)` — three binary persona dimensions (adapted from AgentReview's `role_descriptions.py`). Default reviewer = "Best Case" (Knowledgeable + Responsible + Benign). The opposite poles are "not knowledgeable", "lazy", "mean". A rubric (`AGENT_REVIEW_RUBRICS`, scores 1/3/5/6/8/10) is appended.
- **AC / meta-reviewer persona**: `meta_reviewer_system_prompt` — "very knowledgeable and experienced area chair... inclusive area chair" aggregating multiple reviews.
- **Review JSON fields** (`AGENTREVIEW_INSTRUCTIONS`): `Summary, Strengths, Weaknesses, Originality(1-4), Quality(1-4), Clarity(1-4), Significance(1-4), Questions, Limitations, Ethical Concerns(bool), Soundness(1-4), Presentation(1-4), Contribution(1-4), Overall(1-10), Confidence(1-5), Decision(Accept|Reject)`. THOUGHT note-taking precedes the JSON.
- **Flow** (`perform_review_agentreview`, default `num_review_ensemble=3`, temp 0.75): generate N independent reviews with the reviewer persona → `get_meta_review` aggregates them with the AC persona → numeric axis scores are recomputed as the rounded mean of valid per-reviewer scores.

> Brief's "5-phase (reviewer assessment, author-reviewer discussion, reviewer-AC, meta-review, decision)": the conceptual AgentReview protocol has those phases, but THIS repo collapses them into: (1) ensemble reviewer assessment, (2) AC meta-review aggregation, (3) Decision field, and the "author-reviewer discussion" phase is realized externally as the **ContentRefinementAgent rebuttal-via-revision loop** rather than inside `agent_review.py`. The persona dimensions present in code are the 3 reviewer axes (knowledgeable/responsible/benign) + the inclusive-AC meta-reviewer.

**ContentRefinementAgent loop** (`methods/agents/content_refinement_agent.py`, `max_reflections=3`): compile initial draft → baseline AgentReview score → for each iteration, feed the reviewer feedback + worklog + experimental log + citation map + current `.tex` + the compiled PDF bytes to the refinement model (`content_refinement_agent_system_prompt`, "Rebuttal via Revision"), recompile, re-review. Accept/revert policy by Overall delta and sub-axis gain/drop:
- Overall up → ACCEPT & continue;
- Overall down → REVERT & stop;
- Overall same → continue only if sub-axis gain ≥ drop, else revert.
Then a separate single-pass **formatting loop** (`max_formatting_loops=1`) uses a VLM (`pdf_to_grid_images` + Gemini vision) to detect figure/table overflow & layout issues and emit a formatting-only LaTeX fix. Final PDF returned.

## 7. Section Writing agent — figures, tables, citations

File: `methods/agents/section_writing_agent.py` (`SectionWritingAgent`), prompt `methods/prompts/section_writing_agent.py`. Calls `call_llm_with_images` (multimodal — actual raster figure files are passed so the model describes them faithfully; PDFs excluded from vision input), temp 0.7, parser `parse_gemini_latex_results`.
- **Tables**: build LaTeX tables from `experimental_log.md` using the **`booktabs`** format (`\toprule, \midrule, \bottomrule`); no hallucinated numbers; tables before Conclusion unless in Appendix.
- **Figures**: must use ALL files in `figures_info.json`; exact filenames incl. extension in `\includegraphics`; figures stored in `figures/`; no merging; single-column `figure` preferred in 2-col layouts; captions must not include "Figure x".
- **Citations**: use exact keys from `citation_map.json` (`\cite{Key}`), enriching sentences from the provided abstracts; uses `citation_candidates` from `outline.json`.
- Preserves already-written sections (intro/related work) and preamble; returns full compilable `template.tex`.

## 8. Evaluation — autoraters

> Brief's "PaperWritingBench": no file/string by that name exists in the repo; the benchmark/dataset is external (`datasets/`, released later). The `autoraters/` suite is the in-repo evaluation harness:

- `autoraters/agent_review.py` — simulated peer-review scores (used both as refinement signal and as an evaluator).
- `autoraters/lit_review_quality.py` — single-paper literature-review quality. Pydantic `PaperReview`; prompt `lit_review_quality_prompts.py` scores 6 axes 0-100 (Coverage, Relevance, Critical Analysis, Positioning/Novelty, Organization, Citation Rigor) with anti-inflation rules and a venue `avg_citation_count` baseline (default 58); weighted overall; batch over folders/JSON.
- `autoraters/citation_f1.py` — **citation precision/recall/F1** against the original ground-truth paper. Extracts references from both PDFs, resolves each to a Semantic Scholar `paperId` (via the same S2 search endpoint), LLM-classifies GT refs into **P0 (must-have)** / **P1 (good-to-have)**, then computes overall P/R/F1 plus P0-recall and P1-recall. Caches GT.
- `autoraters/sxs_paper_quality.py` — side-by-side overall quality of two systems; runs both orderings to de-bias position, maps to 5-point (win/leaning-win/tie/leaning-loss/loss) and 3-point categories; Gemini (PDF bytes) or OpenAI (text + page images) backends.
- `autoraters/sxs_lit_review_quality.py` — side-by-side literature-review quality (text-based).

## 9. Entry points / how it runs

- **CLI**: `paper_writing_cli.py` (`main()` argparse). Required: `--raw_materials_dir`, `--latex_template_dir`. Optional: `--output_dir`, `--idea_filename` (default `idea_sparse.md`), `--experimental_log_filename` (default `experimental_log.md`), `--writer_model_name`, `--reflection_model_name`, `--research_cutoff` (default = current `YYYY-MM`), `--use_plotting` (bool), `--plotting_model_name`, `--image_model_name`, `--plotting_max_critic_rounds` (3). It copies raw materials into `output_dir/raw_materials`, warns if no figures and not plotting, then dispatches to `paper_writer_with_plotting.write_single_paper` (if `--use_plotting`) or `paper_writer.write_single_paper`.
- **Bash**: `paper_writing_cli.sh` wraps the CLI.
- **Batch**: `run_batch_writeup(...)` in both `paper_writer*.py` — process a root folder or a `paper_info.json` list, `ProcessPoolExecutor`, resumable via `paper_writing_log.json`.
- **Frontend**: `frontend/app.py` (Streamlit, 1082 lines) — interactive demo, calls `methods.paper_writer.write_single_paper`, shows a stage timeline, optional SMTP completion email (`frontend/frontend_utils.py`).
- **Inputs expected**: `raw_materials/{idea_*.md, experimental_log.md, figures/...}`; a template dir with `template.tex`, `guidelines.md`, `.sty/.bst`, `references.bib`.
- **Outputs**: `outline.json`, `literature_agent_output/{outline_v1.json,updated_template.tex,references.bib,citation_map.json}`, `latex_writeup/`, `content_refinement_workdir/` (worklogs, peer_reviews, screenshots), `final_paper.pdf`, `time_breakdown.json` (plotting variant).

---

## Reusable for clio-parser

- **Web-grounded → S2-verified retrieval pipeline** (`literature_review_agent.py` + `scholar_utils.py`): the canonical "propose-then-verify" RAG. LLM+Google-Search proposes candidate titles/years; Semantic Scholar authenticates via fuzzy title match (`thefuzz.fuzz.ratio > 70`, +10 year-match bonus), date-cutoff filtering (year/month/day, two independent checks), and abstract-presence gating; then bibtex + `citation_map.json` generation and citation-key minting (`_generate_key`). Directly transferable to a parser/retriever that must map noisy citation strings to verified records.
- **`s2_title_search` signature & fields** (`utils/scholar_utils.py`): endpoint, fields list, headers, timeout, and the exact accept threshold — a ready reference for clio-parser's S2 calls.
- **Citation-string → title normalization** (`utils/content_parsing_utils.py::extract_paper_title_from_citation` with `gemini-3-flash-preview`) and the P0/P1 priority taxonomy + S2-ID-based F1 (`autoraters/citation_f1.py`) — a concrete recipe for measuring retrieval quality against a ground-truth bibliography.
- **De-dup by normalized title** (`_normalize_title = re.sub(r"[^a-z0-9]","",title.lower())`) under a lock — simple robust dedup key.
- **Rate-limit discipline**: parallel discovery (10 threads) but **sequential** S2 enrichment with `time.sleep(1.0)`; `429` backoff in the F1 evaluator.
- **Structured-plan-as-contract**: outline JSON schema drives downstream agents (search tasks, plotting, section writing) — a clean separation of "planning" from "execution" worth emulating.

## Open questions

- The brief's labels "PaperBanana" and "AgentReview" are real upstream projects but appear here only as (a) `paper_banana_utils.py` expecting an external `../../PaperBanana/` data dir (few-shot pools + style guides) that is NOT in this repo, and (b) `agent_review.py` adapting AgentReview's role descriptions. Where do those external assets/datasets come from at runtime? (README says dataset released separately.)
- The literal "5-phase peer review" and "PaperWritingBench" from the brief are not present verbatim; they likely refer to the arXiv paper's terminology. Confirm against the paper if exact phase fidelity matters.
- `gemini-3.1-pro-preview` / `gemini-3-pro-image-preview` / `gemini-3-flash-preview` and the 2026 copyright/arXiv id suggest these are forward-dated placeholders; real model IDs would need substitution.
- `joblib` used in `citation_f1.py` but missing from `requirements.txt`.
- The S2 cutoff logic exists in TWO places with slightly different month/day handling (`scholar_utils.is_date_valid` vs `literature_review_agent._is_paper_allowed`) — worth reconciling if reused.
```

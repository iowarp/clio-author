# papervizagent (PaperBanana / PaperVizAgent) — Deep Study Notes

Repo: `/home/shazzadul/Illinois_Tech/Summer26/RA/clio-author/artifact/repos/papervizagent`
Source: Google Research — official implementation of **PaperBanana** (renamed **PaperVizAgent**), a reference-driven multi-agent framework for automated academic illustration (diagram + plot) generation. arXiv 2601.23265.

---

## 1. Purpose, Tech Stack, Language, Dependencies, License

- **Purpose:** Transform raw scientific content (a method section + figure caption, or raw data + visual intent) into publication-quality academic **diagrams** or **plots**, via an orchestrated pipeline of specialized LLM/VLM agents with in-context learning from reference examples and an iterative critic refinement loop. Outputs are benchmarked against human-drawn figures using a VLM-as-Judge.
- **Language:** Python 3.12 (managed with `uv`).
- **Tech stack / dependencies** (`requirements.txt`): `google-genai` (primary — Gemini via Vertex AI), `anthropic` (`AsyncAnthropicVertex`), `openai` (`AsyncOpenAI`, incl. GPT-Image), `streamlit` (demo UI), `matplotlib` (plot code execution), `pillow` (image conv), `numpy`, `tqdm`, `json_repair` (robust JSON parsing of model output), `aiofiles` (async incremental save), `python-dotenv`, `pyyaml`, `google-auth`. Everything is **async** (`asyncio`).
- **License:** Apache 2.0 (`LICENSE`; every source file carries the "Copyright 2026 Google LLC / Apache License 2.0" header).
- **Containerization:** `Dockerfile` present; `scripts/run_main.sh` and `scripts/run_demo.sh` bootstrap a `uv` venv, stub empty `ref.json` files, and run.

---

## 2. Full Repo Structure

```
papervizagent/
├── main.py                  # CLI entrypoint (argparse → ExpConfig → PaperVizProcessor batch run)
├── demo.py                  # Streamlit UI (2 tabs: Generate Candidates / Refine Image)
├── requirements.txt
├── Dockerfile
├── README.md
├── LICENSE (Apache 2.0), CONTRIBUTING.md, code-of-conduct.md, .gitignore
├── agents/
│   ├── __init__.py
│   ├── base_agent.py        # BaseAgent (ABC) — async process(data) interface
│   ├── retriever_agent.py   # RetrieverAgent  (NOTE: docstring mislabeled "Vanilla Agent")
│   ├── planner_agent.py     # PlannerAgent
│   ├── stylist_agent.py     # StylistAgent
│   ├── visualizer_agent.py  # VisualizerAgent (image-gen for diagram / matplotlib-code for plot)
│   ├── critic_agent.py      # CriticAgent
│   ├── vanilla_agent.py     # VanillaAgent (baseline, direct generation)
│   └── polish_agent.py      # PolishAgent (polish a GT image to style guide; not in main 5)
├── utils/
│   ├── __init__.py
│   ├── config.py            # ExpConfig dataclass
│   ├── paperviz_processor.py# PaperVizProcessor — the orchestration engine
│   ├── generation_utils.py  # call_gemini/claude/openai_with_retry_async + image gen
│   ├── eval_toolkits.py     # VLM-as-Judge referenced eval (4 dims + tiered overall)
│   └── image_utils.py       # convert_png_b64_to_jpg_b64
├── prompts/
│   ├── __init__.py
│   ├── diagram_eval_prompts.py  # 4 referenced-comparison judge prompts (diagram)
│   └── plot_eval_prompts.py     # 4 referenced-comparison judge prompts (plot)
├── style_guides/
│   ├── generate_category_style_guide.py     # offline tool to synthesize style guides from ref images
│   ├── neurips2025_diagram_style_guide.md   # synthesized "NeurIPS Look" aesthetic guide
│   └── neurips2025_plot_style_guide.md
├── configs/
│   └── model_config.template.yaml           # copy → model_config.yaml (gitignored)
├── scripts/  run_main.sh, run_demo.sh
├── visualize/  show_pipeline_evolution.py, show_referenced_eval.py  (Streamlit viewers)
└── assets/  teaser_figure.jpg, method_diagram.png
```
Dataset (`data/PaperBananaBench/{diagram,plot}/`) is expected but **not shipped** (released separately). The framework degrades gracefully without it (retriever falls back to `none`).

---

## 3. The Agents — Roles, Files, Definition

**Base class** (`agents/base_agent.py`): `BaseAgent(ABC)` with constructor `(model_name="", system_prompt="", exp_config=None)` and a single abstract async method:

```python
@abstractmethod
async def process(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
```

Every agent subclasses `BaseAgent`, is constructed with `exp_config=...`, and in `__init__` picks `system_prompt` + a `self.task_config` dict by branching on `exp_config.task_name` ("plot" vs "diagram"). Agents are **stateless transformers of the shared `data` dict** — they read keys, call a model, and write new keys back. (Note: most agent files carry a copy-pasted `"""Vanilla Agent..."""` module docstring — harmless mislabeling.)

The framework's headline is **5 agents** (Retriever, Planner, Stylist, Visualizer, Critic). The repo ships **7 agent classes** (those 5 + Vanilla baseline + Polish utility):

1. **RetrieverAgent** (`retriever_agent.py`) — Generative retrieval: selects Top-10 most relevant reference figures from a candidate pool (`ref.json`) to serve as few-shot examples. Supports `retrieval_setting` ∈ {`auto`, `manual`, `random`, `none`}. In `auto` it feeds the whole candidate pool (diagram: first 200; plot: all) into Gemini and asks for a JSON list of IDs. Domain + visual-intent matching logic lives in `DIAGRAM_RETRIEVER_AGENT_SYSTEM_PROMPT` / `PLOT_...`.
2. **PlannerAgent** (`planner_agent.py`) — Translates method content + caption into a detailed textual figure description, using the retrieved examples (text + reference image) as in-context demonstrations.
3. **StylistAgent** (`stylist_agent.py`) — Refines the planner's description for aesthetics using the synthesized `neurips2025_{task}_style_guide.md`. Must preserve semantic content; only enrich visual attributes.
4. **VisualizerAgent** (`visualizer_agent.py`) — Renders description → image. **Diagram path**: direct image generation (Gemini image model or GPT-Image). **Plot path**: generate matplotlib **code** then `exec()` it in a `ProcessPoolExecutor` worker (`_execute_plot_code_worker`).
5. **CriticAgent** (`critic_agent.py`) — VLM that inspects the rendered image against source context, returns JSON `{critic_suggestions, revised_description}`; the literal sentinel `"No changes needed."` short-circuits the loop.
6. **VanillaAgent** (`vanilla_agent.py`) — Baseline: directly generate image/plot-code from method+caption with no planner/stylist/critic.
7. **PolishAgent** (`polish_agent.py`) — Utility (mode `dev_polish`): two-step polish of an existing GT image — generate ≤10 style suggestions, then regenerate a polished image. Not part of the core generation pipeline.

---

## 4. Shared-State `data: Dict` Communication Pattern (KEY)

There is **no message bus** — agents communicate purely by mutating a single `data: Dict[str, Any]` that is threaded through each `process(data)` call and returned. Key naming is **convention-driven** and parameterized by `task_name` ("diagram"/"plot") and a per-round index. This is the most reusable idea for clio-author.

### Input keys (set by caller / dataset; see `demo.create_sample_inputs`)
```python
base_input = {
    "filename": "demo_input",
    "caption": caption,
    "content": method_content,        # str OR dict/list (plot raw data) → json.dumps'd when needed
    "visual_intent": caption,         # caption (diagram) or visual intent (plot)
    "additional_info": {"rounded_ratio": aspect_ratio},   # → image aspect ratio
    "max_critic_rounds": max_critic_rounds,
}
# per-candidate: input_copy["candidate_id"] = i, ["filename"] = f"..._candidate_{i}"
```
`content`, `visual_intent`, `path_to_gt_image`, `additional_info.rounded_ratio` are the canonical inputs every agent reads.

### Keys WRITTEN by each agent (exact conventions)
- **Retriever:** `data["top10_references"]` (List[str] of IDs), `data["retrieved_examples"]` (full example dicts, only populated in `manual` mode; else `[]` and planner re-loads from `ref.json`).
- **Planner:** `data[f"target_{task}_desc{idx}"]` — e.g. `target_diagram_desc0` (the planned description).
- **Stylist:** reads `target_{task}_desc0`, writes `data[f"target_{task}_stylist_desc0"]`.
- **Visualizer:** for each description key `K` present without `f"{K}_base64_jpg"`, writes `data[f"{K}_base64_jpg"]` (JPEG base64). Plot path also writes `data[f"{K}_code"]` (raw matplotlib code). It auto-discovers which descriptions to render by scanning for `target_{task}_desc0`, `target_{task}_stylist_desc0`, and `target_{task}_critic_desc{0..2}`.
- **Critic:** writes per round `data[f"target_{task}_critic_suggestions{round_idx}"]` and `data[f"target_{task}_critic_desc{round_idx}"]`. Reads `data["current_critic_round"]` (set by the processor) to decide which prior description/image to critique.
- **Vanilla:** `data[f"vanilla_{task}_base64_jpg"]`.
- **Polish:** `data[f"suggestions_{task}"]`, `data[f"polished_{task}_base64_jpg"]`.
- **Processor:** sets `data["current_critic_round"]` (loop counter) and `data["eval_image_field"]` — a **pointer key** naming whichever `*_base64_jpg` key holds the final image to evaluate.
- **Evaluator:** writes `data[f"{dim}_outcome"]` and `data[f"{dim}_reasoning"]` for dim ∈ {faithfulness, conciseness, readability, aesthetics, overall}.

### Quoted examples
Critic round bookkeeping (`critic_agent.py`):
```python
round_idx = data.get("current_critic_round", 0)
...
data[f"target_{task_name}_critic_suggestions{round_idx}"] = critic_suggestions
data[f"target_{task_name}_critic_desc{round_idx}"] = revised_description
if revised_description.strip() == "No changes needed.":
    data[f"target_{task_name}_critic_desc{round_idx}"] = detailed_description
```
Visualizer reusing a prior render when the critic said no change (`visualizer_agent.py`):
```python
if critic_suggestions.strip() == "No changes needed." and round_idx > 0:
    prev_base64_key = f"target_{task_name}_critic_desc{round_idx - 1}_base64_jpg"
    if prev_base64_key in data:
        data[f"{key}_base64_jpg"] = data[prev_base64_key]
```
The "final image pointer" indirection (`paperviz_processor.py`): `data["eval_image_field"] = current_best_image_key`, and `eval_toolkits` then does `model_image_base64 = sample_data[sample_data["eval_image_field"]]`.

---

## 5. Orchestration Engine — `PaperVizProcessor` (`utils/paperviz_processor.py`)

Constructed with `exp_config` + all 7 agent instances. Three public/private methods drive everything:

### exp_modes (routing in `process_single_query`)
`exp_mode` selects the agent chain (string `if/elif`):
- `vanilla` → VanillaAgent only; `eval_image_field = vanilla_{task}_base64_jpg`.
- `dev_planner` → Retriever → Planner → Visualizer; eval `target_{task}_desc0_base64_jpg`.
- `dev_planner_stylist` → Retriever → Planner → Stylist → Visualizer; eval `target_{task}_stylist_desc0_base64_jpg`.
- `dev_planner_critic` / `demo_planner_critic` → Retriever → Planner → Visualizer → **critic loop (source="planner")**.
- `dev_full` / `demo_full` → Retriever → Planner → Stylist → Visualizer → **critic loop (source="stylist")**. This is the full headline pipeline.
- `dev_polish` → PolishAgent only; `dev_retriever` → Retriever only (no eval).
- `"demo"` in mode ⇒ `do_eval=False` (demo modes skip VLM-judge evaluation).
- Unknown mode → `raise ValueError`.

### Critic ↔ Visualizer refinement loop — `_run_critic_iterations(data, task_name, max_rounds=3, source)`
```python
for round_idx in range(max_rounds):
    data["current_critic_round"] = round_idx
    data = await self.critic_agent.process(data, source=source)
    critic_suggestions = data.get(f"target_{task_name}_critic_suggestions{round_idx}", "")
    if critic_suggestions.strip() == "No changes needed.":
        print(f"[Critic Round {round_idx}] No changes needed. Stopping iteration.")
        break                                   # <-- short-circuit
    data = await self.visualizer_agent.process(data)
    new_image_key = f"target_{task_name}_critic_desc{round_idx}_base64_jpg"
    if new_image_key in data and data[new_image_key]:
        current_best_image_key = new_image_key   # advance "best"
    else:
        # visualization FAILED → roll back to previous best, stop
        break
data["eval_image_field"] = current_best_image_key
```
Notes:
- The **initial fallback best image** depends on `source`: `target_{task}_desc0_base64_jpg` (planner) or `target_{task}_stylist_desc0_base64_jpg` (stylist).
- **"No changes needed." short-circuit** is checked both here (stop the loop) and inside the visualizer (reuse the previous round's bytes instead of re-rendering).
- **Failure rollback:** if the visualizer produces no valid image for the round, the loop breaks and keeps the last good image (defensive against bad matplotlib code / image-gen failures).

### `max_critic_rounds`
Default 3 (`ExpConfig.max_critic_rounds=3`, also CLI `--max_critic_rounds`, demo slider 1–5). In the critic-bearing modes the loop reads `data.get("max_critic_rounds", <config_default>)` so per-sample override is possible. The paper fixes T = 3 rounds. `scripts/run_main.sh` uses `--max_critic_rounds 1`.

### Async / semaphore batch processing — `process_queries_batch(data_list, max_concurrent=50, do_eval=True)`
- An `asyncio.Semaphore(max_concurrent)` caps concurrency (`main.py` and `demo.py` use `concurrent_num = 10`).
- Wraps each doc in `process_with_semaphore`, builds `asyncio.create_task` for all, then `async for future in asyncio.as_completed(tasks)` yields results as they finish (an `AsyncGenerator`).
- A `tqdm` bar shows live win-rates (Model/Tie/Human %) per eval dimension by tallying `{dim}_outcome`.
- `main.py` consumes the generator and **incrementally saves** to JSON every 10 results via `aiofiles`.

---

## 6. PDF / Content Extraction & Retrieval

- **No MinerU, no PyMuPDF/fitz, no in-repo PDF parser.** (`grep` for mineru/pymupdf/fitz/pdf finds nothing operational.) The dataset is expected pre-extracted: each example carries a markdown/text `content` (method section or raw data), a `visual_intent`/`caption`, and `path_to_gt_image`. The demo takes `content`/`caption` as raw text the user pastes (README: "Markdown recommended"). PDFs (`data/.../pdfs/`) exist in the dataset layout but are not parsed by this code.
- **Reference store:** `data/PaperBananaBench/{task}/ref.json` — list of `{id, visual_intent, content, path_to_gt_image}`.
- **Retrieval settings** (`RetrieverAgent.process`):
  - `none` → `top10_references=[]` (graceful when no dataset; auto-fallback if `ref.json` missing).
  - `manual` → load `agent_selected_12.json` (first 10), populate full `retrieved_examples`.
  - `random` → `random.sample` 10 IDs from the pool.
  - `auto` → call Gemini with the entire pool serialized into the prompt (diagram capped at first 200 candidates; plots uncapped), parse the JSON list with `json_repair` (`top10_diagrams`/`top10_plots`).
- **In-context examples (Planner):** if `retrieved_examples` empty, planner re-loads `ref.json`, maps IDs→items, and builds an interleaved text+image few-shot prompt: for each example it appends `{content_label}: ...`, `{visual_intent_label}: ...`, then the **base64 reference image** (`item["path_to_gt_image"]`), then finally the target query. This is true multimodal ICL.

---

## 7. Vision / Image Generation

- **Model selection** comes from `ExpConfig.model_name` (text/reasoning model, e.g. `gemini-3-pro-preview`) and `ExpConfig.image_model_name` (e.g. `gemini-3-pro-image-preview`), loaded from env or `configs/model_config.yaml`.
- **Diagram path = direct image generation.** VisualizerAgent uses `image_model_name`, `use_image_generation=True`.
  - Gemini: `GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio=<rounded_ratio or 1:1>, image_size="1k"))` via `call_gemini_with_retry_async`. In `generation_utils`, models whose name contains `"image"` or `"nanoviz"` are treated as image generators — the code reads `part.inline_data` and base64-encodes it.
  - GPT-Image: `call_openai_image_generation_with_retry_async` (`size="1536x1024"`, `quality="high"`, returns `b64_json`).
  - Output PNG → JPEG via `image_utils.convert_png_b64_to_jpg_b64`.
- **Plot path = matplotlib code.** VisualizerAgent uses the **text** `model_name`, `use_image_generation=False`. Prompt: *"Use python matplotlib to generate a statistical plot based on the following detailed description..."*. The returned code is regex-extracted (```` ```python ... ``` ````), `exec()`'d inside `_execute_plot_code_worker` running in a `ProcessPoolExecutor(max_workers=32)` (backend `Agg`, `savefig` JPEG `dpi=300`), then base64-encoded. Commented-out blocks show how to swap plots to direct image-gen instead.
- **Demo "Refine Image" tab:** `refine_image_with_nanoviz` does free-form image **editing/upscaling** to 2K/4K with chosen aspect ratio via the Gemini image model (`response_modalities=["IMAGE"]`, `ImageConfig(image_size="2K"|"4K")`).
- **Generic content format:** `generation_utils` uses a provider-neutral `[{"type":"text",...}, {"type":"image","source":{"type":"base64","media_type":...,"data":...}}]` list, with `_convert_to_gemini_parts` / `_convert_to_claude_format` / `_convert_to_openai_format` adapters. Retries use exponential backoff capped at 30s; on total failure returns `["Error"]`.

---

## 8. Evaluation — VLM-as-Judge (`utils/eval_toolkits.py`, `prompts/*_eval_prompts.py`)

- **Setting:** *referenced* pairwise comparison. The human ground-truth image (Human) is shown **first**, then the model-generated image (Model); the judge picks a winner per dimension. Driven by `get_score_for_image_referenced(sample_data, task_name, work_dir)` (called from `PaperVizProcessor.evaluation_function`).
- **4 dimensions** (`prompts/diagram_eval_prompts.py`, `plot_eval_prompts.py`), each a strict-JSON `{comparison_reasoning, winner}` prompt with a Core Definition + "Veto Rules" (red lines):
  1. **Faithfulness** — technical alignment to method/caption; vetoes: hallucination, logical contradiction, scope violation, gibberish text. (Sees method + caption + both images.)
  2. **Conciseness** — visual signal-to-noise; vetoes: textual overload (>15-word boxes), literal copy-paste, math dump.
  3. **Readability** — pass/fail baseline; vetoes: rendered caption/title, occlusion/overlap, spaghetti arrows, illegible font, low contrast, non-rectangular layout, black background. **Defaults to "Both are good"** unless a veto fires. (Caption + images only — no method.)
  4. **Aesthetics** — publication polish; vetoes: low-quality artifacts, jarring colors, amateurish styling, inconsistent typography, black background. (Caption + images only.)
- **Per-dim mechanics** (`_run_single_eval_ref`): builds content list (text + GT image + text + model image), routes by model name (`gemini`→Gemini, `gpt/o1/o3`→OpenAI, else→Claude/Vertex), parses with `json_repair`, with regex fallback `_try_regex_extract_winner` and a `valid_winners` set `["Human","Model","Both are good","Both are bad"]`. All 4 dims run concurrently via `asyncio.gather`.
- **Overall = tiered rule** (`_determine_tier_outcome`): **Tier 1 = Faithfulness + Readability**; if it yields Model/Human, that's the overall. If Tier 1 ties, **Tier 2 = Conciseness + Aesthetics** decides. Conflicting winners → Tie; one side wins + other neutral ("Both are good/bad") → that side wins. Written to `overall_outcome` / `overall_reasoning` (with a human-readable `decision_path`).
- **Edge cases:** no GT path → all dims `"N/A - No GT"`; model image missing (generation failed) → **Human wins by default** on all dims.
- **Live metrics:** the batch loop prints rolling `Model/Tie/Human` percentages per dim in the tqdm postfix.

---

## 9. ExpConfig / YAML Config

`utils/config.py` — `@dataclass ExpConfig`:
- Fields: `dataset_name`, `task_name`("diagram"|"plot"), `split_name`, `temperature=1.0`, `exp_mode`, `retrieval_setting`("auto"|"manual"|"random"|"none"), `max_critic_rounds=3`, `model_name`, `image_model_name`, `work_dir`, `timestamp`.
- `__post_init__`: sets TZ to America/Los_Angeles; **if `model_name`/`image_model_name` empty, loads them from `configs/model_config.yaml` → `defaults.{model_name,image_model_name}`**; builds `exp_name = f"{timestamp}_{retrieval_setting}ret_{exp_mode}_{split_name}"`; creates `results/{dataset}_{task}/` dir.
- `configs/model_config.template.yaml` (copy → `model_config.yaml`, gitignored): `defaults.{model_name,image_model_name}`, `google_cloud.{project_id,location}`, `api_keys.{google,openai,anthropic}`, `anthropic.{region,project_id}`.
- `generation_utils.py` resolves creds with precedence **env var → yaml → default** (`get_config_val`), preferring **Vertex AI** (`genai.Client(vertexai=True, project, location)`) and falling back to a Google API key. Anthropic via `AsyncAnthropicVertex`, OpenAI via `AsyncOpenAI`.

### Style-guide synthesis (`style_guides/generate_category_style_guide.py`)
Offline tool feeding the Stylist: batches reference images (BATCH_SIZE=20, concurrency 5) into a VLM with `DIAGRAM_BATCH_ANALYSIS_PROMPT`/`PLOT_...`, then synthesizes all batch reports into `neurips2025_{mode}_style_guide.md`. Philosophy: describe *observed* diverse design options, not rigid prescriptions ("Soft Tech & Scientific Pastels").

---

## Reusable for clio-author

- **Shared-state `data: Dict` pattern as the agent interface.** A single dict threaded through `async process(data) -> data`, with **string-templated, task-and-round-parameterized keys** (`target_{task}_{stage}_desc{round}[_base64_jpg]`). No bus, no schemas — trivial to inspect/serialize/replay, and each stage is independently re-runnable (visualizer skips keys whose `*_base64_jpg` already exists — built-in idempotency/caching). Strong reference for an expert-agent harness.
- **`BaseAgent` minimal contract:** ABC + one async `process` + per-task `system_prompt`/`task_config` chosen in `__init__`. Clean, copy-able.
- **"Final artifact pointer" indirection:** `data["eval_image_field"]` names which key holds the result, decoupling producers from the evaluator.
- **Sentinel-based loop control:** literal `"No changes needed."` to short-circuit a refine loop, plus **rollback-to-last-good** on generation failure and **reuse-previous-bytes** to avoid recompute.
- **Orchestrator design:** mode-string routing to fixed agent chains; `asyncio.Semaphore` + `as_completed` + async-generator yielding + incremental `aiofiles` save + live tqdm metrics. Directly portable batch harness.
- **Provider-neutral content list** + per-provider adapters (`_convert_to_{gemini,claude,openai}_*`) with retry/backoff — a reusable multi-LLM abstraction.
- **VLM-as-Judge eval kit:** decomposed dimensions with explicit "Veto Rules", strict-JSON + regex fallback parsing (`json_repair`), and a **tiered deterministic aggregation** (`_determine_tier_outcome`) instead of averaging scores.
- **Style-guide auto-synthesis** (map-reduce over corpus images → markdown guideline injected as ICL context) is a reusable "learn the house style from examples" trick.

## Open Questions

- **Dataset format details:** `PaperBananaBench` `test.json`/`ref.json`/`agent_selected_12.json` schemas and `path_to_gt_image` conventions are inferred from code only; the dataset is not in-repo ("released shortly").
- **How `content` originates from PDFs:** the `pdfs/` dir exists but no extraction code ships — presumably MinerU/manual was used during dataset construction, outside this repo. Worth confirming against the paper appendix.
- **Module docstring mislabeling:** retriever/planner/stylist/visualizer/critic all say `"""Vanilla Agent..."""` — cosmetic, but indicates the agents were forked from a template; verify no functional copy-paste leaked (none observed).
- **`nanoviz` model name:** treated as an image model in `generation_utils` and referenced in `refine_image_with_nanoviz`; appears to be an internal Google image model alias — exact identity unknown.
- **Plot vs diagram asymmetry:** plot uses matplotlib-code (dpi 300 in visualizer worker, dpi 100 in vanilla worker — inconsistent), diagram uses image-gen; commented code shows both are swappable. Production default per paper is code-based for plots.
- **Claude/OpenAI text paths** exist in `generation_utils`/`eval_toolkits` but the core generation agents call only `call_gemini_with_retry_async`; multi-provider is mainly an eval-time / future-proofing capability.

---

## 10-line Summary

1. PaperVizAgent (a.k.a. PaperBanana, Google Research, Apache-2.0, Python 3.12/async) turns method-text+caption (diagrams) or raw-data+intent (plots) into publication-quality figures.
2. Core is **5 agents** — Retriever, Planner, Stylist, Visualizer, Critic — plus Vanilla (baseline) and Polish utilities; all subclass `BaseAgent` with one async `process(data)->data`.
3. Agents communicate ONLY through a shared `data: Dict` using string-templated keys like `target_{task}_stylist_desc0_base64_jpg` and `target_{task}_critic_desc{round}`.
4. `PaperVizProcessor` (utils/paperviz_processor.py) routes `exp_mode` to a fixed agent chain (`vanilla`, `dev_planner`, `dev_planner_stylist`, `dev_*_critic`, `dev_full`, `demo_*`).
5. The Critic↔Visualizer loop runs up to `max_critic_rounds` (default 3), short-circuiting on the literal `"No changes needed."` and rolling back to the last good image on render failure.
6. Batch processing uses `asyncio.Semaphore` + `as_completed` async-generator + incremental `aiofiles` JSON saves, with live tqdm win-rate metrics.
7. No PDF parser in-repo (no MinerU); `content` arrives pre-extracted; retrieval (`auto/manual/random/none`) supplies multimodal in-context few-shot examples from `ref.json`.
8. Visualizer renders **diagrams via image-gen** (Gemini image / GPT-Image) and **plots via matplotlib code** `exec()`'d in a process pool; PNG→JPG conversion throughout.
9. Evaluation is referenced VLM-as-Judge across 4 vetoed dimensions (faithfulness, conciseness, readability, aesthetics) aggregated by a tiered rule into `overall_outcome`.
10. `ExpConfig` + `configs/model_config.yaml` resolve models/creds (Vertex-first) for Gemini/Anthropic/OpenAI; Stylist's NeurIPS style guide is auto-synthesized offline from reference images.

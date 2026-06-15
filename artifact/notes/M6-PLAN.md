# M6 Build Plan — Figure Agent (PaperBanana-derived)

Adds `clio_parser/experts/figure_agent.py` + figure models. Two capabilities, hermetic-first:
1. **Describe/caption** figures (fills the `FigureInfo.description` slot deferred from M1) — via the
   `LLMClient` (vision optional/gated); hermetic path uses the existing caption + surrounding text.
2. **Generate plots** — produce **matplotlib code** (text) from a plot spec via the LLM; optional
   gated rendering. Diagram image-generation is gated/deferred (needs an image model).

Reference: PaperBanana / papervizagent (Apache-2.0) — the Retriever→Planner→Stylist→Visualizer↔Critic
flow + the "No changes needed." critic short-circuit. We **reuse the existing `CriticRefine`** pattern
for the visualizer↔critic loop rather than re-implementing it.

## Decisions
- **Hermetic-first:** no heavy deps in the default path. Plot **code generation** is just LLM text
  (tested with a canned client). Actual matplotlib **execution** is gated behind an optional `viz`
  extra + `live` marker (executing LLM-generated code is risky → run only in a subprocess with a
  timeout when explicitly enabled; NOT in the default suite).
- Reuse `MemoryBlocks`/`FigureInfo` (describe updates the description), `CriticRefine`/
  `NO_CHANGES_SENTINEL` (visualizer↔critic), expert conventions (never-raises, `_error`, `_coerce_*`),
  `SafeFiles` (write generated code/PNG under a root).
- Code-execution safety: a `render_plot_code` helper runs code via `subprocess` (own process,
  timeout, cwd in an out-dir, `Agg` backend) only when called from a gated path; default never executes.

## Steps
1. **`clio_parser/experts/figure_models.py`** (Pydantic v2): `PlotSpec{kind:Literal["plot","diagram"],
   intent:str, data_hint:str="", aspect_ratio:str|None}`, `FigureDescription{figure_id:int,
   description:str, caption:str|None}`, `FigureArtifact{kind, code:str|None, image_path:str|None,
   description:str|None}` + `from_loose_dict` where useful.
2. **`clio_parser/experts/figure_agent.py`** — `FigureAgentExpert(BaseAgent)` role `figure`,
   `__init__(llm=None,*,files=None)`. Modes via `task.payload["mode"]`:
   - `"describe"`: read figures from `payload["blocks"]`→`MemoryBlocks` (or `payload["figures"]`);
     for each `FigureInfo` lacking a description, prompt the LLM with caption + context → fill
     `description`; return updated `MemoryBlocks` dump + per-figure `FigureDescription`s.
   - `"plot"`: read `PlotSpec` from `payload["spec"]`; prompt the LLM for matplotlib code (must use
     `Agg`, save to a path, no network); extract the ```python``` block (stdlib); if `files` +
     `payload["out_path"]` write the code via `SafeFiles.write_new`; return `FigureArtifact{code=...}`.
     Do NOT execute by default.
   - revise phase (`session.data["critic_feedback"]`): regenerate code/description addressing feedback
     (so the agent can be a `CriticRefine` producer).
   - Never raises; `_error` on bad input/file refusal.
   - Module helper `render_plot_code(code, out_path, *, timeout=20)` (gated): run code in a subprocess
     with `MPLBACKEND=Agg`, timeout, cwd=out-dir; returns the PNG path. Lazy-import; raise
     `RetrievalDependencyError`-style error if matplotlib missing. Used only by gated tests/live.
   - Optional `run_figure_refine(task,*,producer,critic,max_rounds=3)` analog to `run_write_review_loop`
     (visualizer↔critic via `CriticRefine`).
3. **Deps:** optional `viz = ["matplotlib"]`; mypy override; reuse `live` marker. matplotlib NOT a core dep.
4. **Tests** (hermetic): `figure_models` construction/coercion; `figure_agent` describe mode (canned
   client fills descriptions; updated blocks); plot mode (canned client → code extracted; written via
   SafeFiles); revise phase consumes critic_feedback; error paths; Engine integration. Gated `live`
   test: `render_plot_code` actually renders a PNG when matplotlib present (`importorskip`).
5. **Licensing:** header notes PaperBanana/papervizagent (Apache-2.0) behavior reference; no AGPL; BSD-3.

## Smallest hermetic first slice
`figure_models` + `FigureAgentExpert` describe + plot (code-gen only), canned-client tests.

## Risks
- Executing LLM code is dangerous → never in default suite; gated subprocess + timeout only.
- Vision/image-gen for diagrams deferred (needs an image model) — describe + plot-code is the M6 core.
- Figure-id/filename coupling (from M1) still applies; describe uses existing `figure_id`.

## Verification
`uv run pytest` hermetic green; `ruff`/`mypy` clean; no matplotlib import in default path; gated
render test renders a PNG when matplotlib installed; describe fills `FigureInfo.description`.

## Files
- New: `clio_parser/experts/{figure_models,figure_agent}.py`; `tests/experts/test_figure_models.py`,
  `tests/experts/test_figure_agent.py`, `tests/experts/test_figure_render_live.py` (gated).
- Modify: `clio_parser/experts/__init__.py`, `pyproject.toml` (`viz` extra + mypy override).
- Reuse: `ingest/blocks.py` (`FigureInfo`/`MemoryBlocks`), `harness/patterns.py` (`CriticRefine`),
  `tools/files.py` (`SafeFiles`), `experts/{reviewer,write_loop}.py` (conventions/loop shape), `llm/client.py`.

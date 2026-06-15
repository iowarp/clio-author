# M4 Build Plan — Review Capability

Adds the "review papers" half: implements the `Parallel` + `CriticRefine` pattern stubs, an
AgentReview-style rubric, a `reviewer` expert, and multi-reviewer + meta-review synthesis. Rubric
adapted from PaperOrchestra `autoraters/agent_review.py` (**Apache-2.0**, attributed);
parallel-blind-review→synthesis re-implements protoneo's IndependentSynthesis **concept** (AGPL — no
code copied).

## Decisions
- **Hermetic-first:** `EchoLLMClient` default yields non-JSON, so rubric parsing is tested with a
  **canned-JSON fake client**; the echo path is the graceful `parse_error` (never-raises) case.
- **`Parallel` = sequential-collect** (not threads): the harness/LLMClient is sync and
  `SessionContext` is unlocked; threads would race for no gain. Deterministic input-order; agents
  own their own `session.add` (don't double-add — mirror `Sequential`). Shared session (reviewers
  don't read history). [Flag: if true blind isolation needed later, give each agent a child session.]
- **`CriticRefine`** = producer(`agents[0]`)↔critic(`agents[1]`) loop; `max_rounds` from
  `task.payload` (default 3); short-circuit on `"No changes needed."` sentinel (module constant);
  state via `session.data`; **returns the full round history** `list[AgentOutput]` (final = last);
  stop on error-flagged output; <2 agents degrades gracefully; never raises. Generic (review-specific
  writer↔reviewer wiring is M5).
- **Anti-reward-hacking:** producer ≠ critic; reviewer scores a paper it didn't write; numeric axes
  clamped by schema bounds; meta-reviewer is a separate persona.

## Steps
1. **`harness/patterns.py`** — implement `Parallel` and `CriticRefine` (per above); `RoundRobin`
   stays a stub. Expose the no-changes sentinel as a module constant. + hermetic pattern tests.
2. **`experts/review_models.py`** (Pydantic v2, Apache-2.0 attribution): `PaperReview` (summary;
   strengths/weaknesses/questions/limitations: list[str]; ethical_concerns: bool; 1–4 axes
   originality/quality/clarity/significance/soundness/presentation/contribution with `Field(ge,le)`;
   overall 1–10; confidence 1–5; decision Literal[Accept,Reject]) + `from_loose_dict(raw)` (maps
   AgentReview TitleCase keys → snake_case, coerces scalars→lists, clamps numerics, defaults
   missing). `PersonaSpec{knowledgeable,responsible,benign,label}`. `MetaReview` (PaperReview +
   reviewer_count).
3. **`experts/reviewer.py`** — `ReviewerExpert(BaseAgent)` role `reviewer`, default `EchoLLMClient`,
   optional `persona`. `build_reviewer_system_prompt(persona)` (re-typed from AgentReview, attributed).
   `_coerce_paper(raw)->str` (markdown str, or `MemoryBlocks`/dict via `select(detail=...)`); read from
   `payload["paper"|"markdown"|"blocks"]` or `task.description`. `run`: system+user → `llm.complete`
   → extract ```json``` / balanced-brace (stdlib json, NO json_repair) → `PaperReview.from_loose_dict`;
   on parse fail return `AgentOutput(content=raw, structured=None, metadata={"parse_error":...})`
   (never raise); on success `structured=review.model_dump()`, `metadata={persona,decision,overall}`.
   Whole body try/except → `_error`.
4. **`experts/meta_reviewer.py`** — `MetaReviewerExpert(BaseAgent)` role `meta_reviewer` (inclusive-AC
   synthesizer): read reviews from `payload["reviews"]` or `session.history`; LLM path OR
   **deterministic fallback** (rounded mean per axis + majority/threshold decision) so it's hermetic
   offline. + module fn `run_panel(paper, personas, llm, *, synthesize=True)`: build one
   `ReviewerExpert` per persona → `Engine().run(reviewers, Parallel(), task)` → optional
   `MetaReviewerExpert`. (Variance-triggered RoundRobin escalation deferred — note in docstring.)
5. **Tests** (hermetic): `tests/harness/test_patterns_parallel.py` (order, single-add, ≥2 experts,
   Engine), `test_patterns_critic_refine.py` (max_rounds, sentinel short-circuit, history, error-stop,
   <2 agents); `tests/experts/test_reviewer.py` (`CannedJSONLLMClient` happy path → clamped
   `PaperReview`; Echo → parse_error; markdown + MemoryBlocks + dict input; out-of-range clamped;
   missing-paper error; Engine). `tests/experts/test_meta_reviewer.py` (deterministic aggregation of
   3 canned reviews; `run_panel` over Parallel → N reviews + 1 MetaReview; offline fallback). Gated
   `live` reviewer test optional.
6. **Licensing/notes:** Apache-2.0 attribution headers; IndependentSynthesis re-implemented (no AGPL copy).

## Smallest hermetic first slice
`Parallel` + `ReviewerExpert` + `PaperReview.from_loose_dict`, tested with Echo (parse_error) and a
canned-JSON client (structured). Then `CriticRefine`, meta-reviewer + panel.

## Risks
- Parallel isolation (shared vs child sessions) — shared OK now; flag for later.
- CriticRefine return = round-history list (no new result type).
- JSON parsing without a dep → tolerant extractor + clamps + parse_error path; json-repair only as
  an optional extra if live proves insufficient.
- Echo default → non-JSON is the intentional degradation path.

## Verification
`uv run pytest` hermetic green; `ruff`/`mypy` clean; patterns no longer raise NotImplementedError;
reviewer/meta-reviewer never raise on bad input (assert `error`/`parse_error`); each output appended
once. Manual smoke: 3-persona `run_panel` via Parallel → averaged `MetaReview`.

## Files
- Modify: `clio_parser/harness/patterns.py`, `clio_parser/experts/__init__.py`.
- New: `clio_parser/experts/{review_models,reviewer,meta_reviewer}.py`;
  `tests/harness/{__init__,test_patterns_parallel,test_patterns_critic_refine}.py`;
  `tests/experts/{test_reviewer,test_meta_reviewer}.py`.
- Reference (read, don't import/copy): `artifact/repos/paper-orchestra/autoraters/agent_review.py`.
- Reuse: `harness/{base,engine,session,types}.py`, `experts/{paper_qa,citation,echo}.py`,
  `ingest/blocks.py`, `llm/client.py`, `tests/experts/test_paper_qa.py` (RecordingLLMClient shape).

# M5 Build Plan — Write/Edit Capability

Completes Track B: `writer`/`editor` experts (wtf-p outline→plan→write→revise taxonomy, **MIT**,
mirrored as Python — no code copy), a safe `tools/files.py`, and writer↔reviewer wiring through the
existing `CriticRefine`. Section-writing behavior referenced from PaperOrchestra (Apache-2.0).

## Decisions
- **Hermetic-first:** tests use canned/recording fake clients; assert prompt composition + file ops
  + structure, not LLM prose.
- **`SafeFiles(root)`** trust boundary: all reads/writes confined to `root`; `write_new` =
  `O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW` (no clobber, no symlink); `apply_edit` = guarded overwrite of
  a harness-created file (exact `count` match else error; atomic temp+`os.replace`); `read` =
  `O_RDONLY|O_NOFOLLOW`; refuse `..`/absolute (`FileOutsideRootError`). Generalizes M3's atomic write.
- **Writer dual-role** keyed on `session.data["critic_feedback"]`: draft (round 0) vs revise (later) —
  so it's the single `CriticRefine` producer. `EditorExpert` = standalone feedback-driven revision.
- **Sentinel termination (must-have):** `ReviewerExpert` never emits `NO_CHANGES_SENTINEL`, so add a
  `ReviewerAsCritic` adapter mapping `decision=="Accept"` (or no weaknesses) → sentinel so
  `CriticRefine` can stop early. Default "done" = Accept decision.
- Whole-section replace (not diff hunks) for M5. Never-raises experts.

## Steps
1. **`tools/__init__.py` + `tools/files.py`** — `SafeFiles` (read/write_new/apply_edit, `_resolve`
   traversal guard) + exceptions (`FileToolError`/`FileOutsideRootError`/`RefusedWriteError`/
   `EditNotApplicableError`/`SymlinkRefusedError`). Tests `tests/tools/test_files.py` (write-new,
   refuse-overwrite, refuse-symlink, refuse `..`/absolute, apply_edit zero/multi-match, read round-trip).
2. **`experts/write_models.py`** (Pydantic v2): `SectionOutline{title,section_path,goal,word_budget,
   citation_hints,figure_refs,subsections(recursive)}`, `PaperOutline{title,vision,sections}`,
   `SectionPlan{outline,tasks,claims,sources}` + `from_loose_dict` coercion. Tests.
3. **`experts/writer.py`** — `WriterExpert(BaseAgent, role="writer")`, `__init__(llm=None,*,files=None)`.
   Draft phase (no critic_feedback): assemble source (`MemoryBlocks.select(section_path,detail="full")`
   or `payload["source"]`) + outline/plan (`payload["outline"|"section_plan"]`), inline only what the
   section needs (section isolation), call LLM. Revise phase: inline `session.data["draft"]` +
   `critic_feedback`. Keep `\cite{}`/figure placeholders from hints (don't invent citations). If
   `files` + `payload["out_path"]`: `files.write_new` (draft) / `apply_edit` (revise). Output content
   summary + `structured{section_path,draft,out_path,word_count}` + metadata{phase,wrote}. Never raises.
4. **`experts/editor.py`** — `EditorExpert(role="editor")`: read prose (`payload["draft"]`/
   `session.data["draft"]`/`files.read(target)`) + feedback (`payload["review"]`→`PaperReview`
   weaknesses/questions, or `critic_notes`/`session.data["critic_feedback"]`); targeted revision;
   apply via `apply_edit`. Never raises.
5. **`experts/write_loop.py`** — `ReviewerAsCritic` adapter (wraps `ReviewerExpert`; emits
   `NO_CHANGES_SENTINEL` on Accept/no-weaknesses, else renders weaknesses as feedback) +
   `run_write_review_loop(task,*,writer,reviewer,max_rounds=3,session=None)->list[AgentOutput]` running
   `CriticRefine` over `[writer, ReviewerAsCritic(reviewer)]`. Do NOT modify `patterns.py`.
6. **Tests:** `tests/experts/test_{write_models,writer,editor,write_loop}.py` (canned clients; file ops;
   revise consumes critic_feedback; loop draft→review→revise→sentinel-stop + max_rounds cap + error
   halt; Engine integration). Optional gated `live`.
7. **Licensing:** headers note wtf-p (MIT) taxonomy mirrored + PaperOrchestra (Apache-2.0) behavior ref; no AGPL. BSD-3.

## Smallest hermetic first slice
`tools/files.py` + minimal `WriterExpert` writing one section to a new file under a tmp root.

## Risks
- Sentinel termination → `ReviewerAsCritic` (Accept→sentinel); confirm "done" signal.
- Edit granularity → whole-section replace for M5.
- SafeFiles single-root; editor copies external drafts into root (never edits user source in place).
- Follow-up (out of scope): refactor `CitationExpert` write onto `SafeFiles` (don't fork safety logic).

## Verification
`uv run pytest` hermetic green; `ruff`/`mypy` clean; safety assertions (overwrite/symlink/traversal
refusals, apply_edit match guards); loop evolution of `session.data` + early stop + error halt;
offline writer smoke writes a file under tmp root.

## Files
- New: `clio_parser/tools/{__init__,files}.py`, `clio_parser/experts/{write_models,writer,editor,write_loop}.py`;
  `tests/tools/{__init__,test_files}.py`, `tests/experts/test_{write_models,writer,editor,write_loop}.py`.
- Modify: `clio_parser/experts/__init__.py`.
- Reuse (read-only): `harness/patterns.py` (`CriticRefine`,`NO_CHANGES_SENTINEL`), `experts/citation.py`
  (atomic-write pattern), `experts/{reviewer,review_models}.py`, `ingest/blocks.py`, `harness/{base,engine,session,types}.py`, `llm/client.py`.

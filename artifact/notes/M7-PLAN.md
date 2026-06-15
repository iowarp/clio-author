# M7 Build Plan — Hardening

Closes the gaps flagged across M1–M6: (1) **table fidelity** (the gap no reference solved),
(2) **generalized equations** (M1's default path was thin; domain regexes are opt-in), and
(3) a **baseline eval report** (turn the gated baseline harness into a metrics report). All
hermetic, regex/string-based; no new runtime deps.

## Steps
1. **`clio_parser/ingest/tables.py`** — `process_tables(content: str) -> str` (regex, idempotent,
   pure):
   - Detect contiguous GFM table blocks (runs of lines containing `|`).
   - Ensure a header **separator row** (`| --- | --- |`) follows the header row if missing.
   - Normalize each row to the block's max column count (pad short rows with empty cells; keep extra
     cells). Trim leading/trailing pipes consistently.
   - Drop stray blank lines *inside* a table block; merge an obviously-split continuation row
     (a `|`-less line immediately under a table row → appended to the previous cell) — conservative.
   - Leave non-table text untouched; never corrupt a code fence.
   Wire into `postprocess/__init__.py` pipeline order: sections → citations → equations → figures →
   bibliography → **tables** → cleanup (cleanup already preserves `|` rows). Remove the M1
   `# TODO(M7): tables.py` note.
2. **Generalize `equations.py`** — strengthen the default (`domain_fixes=False`) path so it handles
   arbitrary papers, not just transformer/GAN: keep generic de-spacing, delimiter normalization,
   subscript/superscript spacing, `\\`-handling; ensure the transformer/GAN-specific regexes stay
   strictly behind `domain_fixes=True`. Add tests proving generality on non-transformer equations and
   that the generic path is domain-neutral (no spurious rewrites).
3. **`clio_parser/eval/__init__.py` + `clio_parser/eval/report.py`** —
   - `compute_md_metrics(markdown: str) -> dict` (pure): counts of sections (headings), linked
     citations (`[[n]](#ref-n)`), embedded figures (`![`), tables (GFM blocks), references. Reusable
     by `tests/baselines/`.
   - `build_report(results: dict) -> str` (pure): render a Markdown report comparing clio-parser vs
     reference metrics (PDF→MD fidelity counts; citation-verification rate; review win indicators) —
     operate on a metrics dict, hermetic. The actual real-PDF run stays gated in `tests/baselines/`.
   - Optional `scripts/run_baseline_report.py` (gated; needs `pdf` extra + the two papers) that runs
     ingest on the fixtures, computes metrics, and writes a report — not part of the default suite.

## Tests (hermetic)
- `tests/ingest/test_tables.py`: separator insertion; ragged-row normalization; blank-line removal;
  split-row merge; idempotence; non-table and code-fence content untouched; end-to-end
  `process_markdown` keeps a well-formed table well-formed.
- extend `tests/ingest/test_equations.py`: generic de-spacing on a non-transformer equation; assert
  `domain_fixes=False` does not apply transformer/GAN rewrites; `domain_fixes=True` still does.
- `tests/eval/test_report.py`: `compute_md_metrics` on a fixture (known counts); `build_report`
  produces Markdown containing the expected rows; both pure/hermetic.

## Risks
- Table heuristics can mis-merge — keep conservative (only merge a `|`-less line directly under a
  table row; never touch code fences); idempotence test guards.
- Equation generalization must not regress existing tests — run the full equations suite.
- Eval report's real-PDF path is gated (network + `pdf` extra); only the pure metric/report builders
  are in the default suite.

## Verification
`uv run pytest` hermetic green (tables + equations + eval); `ruff`/`mypy` clean; `process_markdown`
idempotent on a table fixture; equations default path domain-neutral.

## Files
- New: `clio_parser/ingest/tables.py`, `clio_parser/eval/{__init__,report}.py`,
  `tests/ingest/test_tables.py`, `tests/eval/{__init__,test_report}.py`; optional
  `scripts/run_baseline_report.py` (gated).
- Modify: `clio_parser/ingest/postprocess/__init__.py` (add tables pass), `equations.py` (generalize),
  `tests/ingest/test_equations.py`.
- Reuse: `ingest/postprocess/*`, `tests/baselines/` (use `compute_md_metrics`).

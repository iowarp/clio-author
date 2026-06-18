# M3 Build Plan — Citation Grounding (`scholar.py` + `citation` expert)

Adds `clio_author/retrieval/scholar.py` (Semantic Scholar retrieval + pure verification) and
`clio_author/experts/citation.py` (discover → verify → **suggestions only**, never overwrites a
bibliography). Mirrors M2's `rag.py`/`paper_qa.py` patterns. Verification logic adapted from
PaperOrchestra `utils/scholar_utils.py` (**Apache-2.0**, attributed).

## Decisions
- **Hermetic-first:** S2 HTTP behind a lazy/gated client; verification LOGIC is pure deterministic
  functions tested offline. `fuzzy_ratio` uses `thefuzz` if available else a **stdlib
  `difflib.SequenceMatcher` fallback** (0–100) — default tests need no `thefuzz`.
- **Safety (hard):** emit `suggested.bib`/suggestions only; refuse any write whose basename is
  `references.bib` or clobbers an existing user bib. Default = no file write (artifact in `structured`).
- **Candidates provided** via `task.payload` (LLM/web discovery deferred); `EchoLLMClient` default
  treats input as candidates.
- **Default client = None** → if not injected at `run`, return error-flagged output (explicit; never guess/network).
- **≥90%** = coverage metric `int(len(candidates)*0.9)` reported (`meets_90pct`), not a hard gate.

## Steps
1. **Deps/gating** (`pyproject.toml`): optional `scholar = ["thefuzz", "httpx"]`; add to mypy overrides; reuse `live` marker.
2. **`retrieval/scholar.py`** (attribution header → PaperOrchestra Apache-2.0):
   - Models (Pydantic v2): `Reference{query_title,year_hint,raw}`, `Candidate{title,year,reason}`,
     `S2Record{paper_id,title,authors,venue,year,abstract,citation_count,journal,publication_date}`,
     `VerifiedCitation{record,score,citation_key,bibtex}`.
   - `ScholarClient` Protocol: `search_title(title, year_hint, cutoff_date) -> list[S2Record]`.
   - `SemanticScholarClient` (lazy `httpx`; S2 graph search `limit=3`, fields, `X-API-KEY` from
     `SEMANTIC_SCHOLAR_API_KEY`, 5s timeout; `[]` on non-200/empty; `RetrievalDependencyError` if httpx missing).
   - `FakeScholarClient(dict[title -> list[S2Record]])` — hermetic test double.
   - Pure functions: `fuzzy_ratio` (thefuzz|difflib), `is_date_valid`, `best_match(query,records,
     threshold=70,year_bonus=10)` (date-gate + abstract-presence + `>threshold`), `mint_citation_key`,
     `dedupe` (by paper_id; a/b/c key collisions), `verified_coverage(candidates,verified)->
     (min_required,ratio,meets)`, `to_bibtex` (@article/@inproceedings), and `verify(references,
     client,*,cutoff_date,threshold)` orchestrator (the client-injection seam).
3. **`experts/citation.py`** — `CitationExpert(BaseAgent)` (role `citation`, modeled on `PaperQAExpert`):
   `__init__(llm=None,*,client=None,cutoff_date=None,threshold=70)`; system prompt states the
   suggestions-only rule. `run`: read `payload["candidates"]`/`["references"]` (coerce via
   `Candidate.model_validate`); if no client → error; `scholar.verify(...)`; `verified_coverage`;
   build `suggested_bibtex` + `citation_map`; if `payload["out_dir"]` write only `suggested.bib`/
   `suggested_citation_map.json` (refuse `references.bib`); return `AgentOutput(structured={verified,
   suggested_bibtex,citation_map,coverage}, metadata={num_candidates,num_verified,meets_90pct,wrote})`;
   never raises.
4. **Tests:** hermetic `tests/retrieval/test_scholar.py` (threshold boundary 70/71; year-bonus;
   `is_date_valid`; abstract-presence reject; `dedupe`; `verified_coverage` rounding incl. len==0;
   `verify` with `FakeScholarClient`); hermetic `tests/experts/test_citation.py` (verified set;
   suggestions-only; out_dir writes `suggested.bib`; `references.bib` refused + user file untouched;
   missing-candidates/no-client/client-raises error paths; Engine/Sequential). Gated
   `tests/retrieval/test_scholar_live.py` (`@pytest.mark.live`, real S2, importorskip).
5. **Licensing/notes:** Apache-2.0 attribution header; bib-safety in docstring + system prompt.

## Smallest hermetic first slice
Models + pure functions (difflib path) + `FakeScholarClient` + `test_scholar.py`; then
`CitationExpert` + `test_citation.py` (incl. safety). `SemanticScholarClient` + live test last.

## Risks
- `thefuzz` vs hermetic → stdlib `difflib` fallback (parity check in a gated test).
- Discovery (LLM/web) deferred; provided-candidates path is primary.
- No-client default → explicit error, not network.
- Write guard compares resolved basenames; refuse clobbering `references.bib`.

## Verification
`uv run pytest tests/retrieval/test_scholar.py tests/experts/test_citation.py` hermetic green;
full `uv run pytest` green; `ruff`/`mypy` clean; `import clio_author.retrieval.scholar,
clio_author.experts.citation` works without the `scholar` extra; `pytest -m live` for real S2.

## Files
- New: `clio_author/retrieval/scholar.py`, `clio_author/experts/citation.py`,
  `tests/retrieval/{test_scholar,test_scholar_live}.py`, `tests/experts/test_citation.py`.
- Modify: `pyproject.toml`, `clio_author/experts/__init__.py`.
- Reuse/templates: `retrieval/rag.py`, `experts/paper_qa.py`, `harness/{base,types}.py`, `llm/client.py`.
- Adapt-from (Apache-2.0): `artifact/repos/paper-orchestra/utils/scholar_utils.py`.

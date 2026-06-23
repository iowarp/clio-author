# clio-author usage

clio-author is a standalone multi-agent harness a host invokes either **in-process** (import) or as
a **subprocess** (the `clio-author` CLI). This document is the full action reference plus the
configuration seams (optional extras, the `LLMClient`, scholar backends, and Gemini vision).

- **Adapter surface** — `ClioAuthorSubagent` (in `clio_author.integration.clio_adapter`): two
  methods, `capabilities()` and `run(action, payload)`. Both return JSON-serializable dicts and
  never raise; any failure is captured into an `error` field.
- **Typed surface** — `ClioAuthorAgent` (in `clio_author.agent`): the same routing with typed
  convenience methods, returning an `AgentOutput` (`agent`, `content`, `structured`, `metadata`).

Every action degrades gracefully: missing inputs or failures produce an output whose
`metadata["error"]` (or top-level `error`) describes the problem rather than raising.

The CLI maps onto the adapter. `run(action, payload)` returns:

```json
{"action": "...", "content": "...", "structured": {...} | null, "metadata": {...}}
```

The CLI exits `1` when the result has a top-level `error` or `metadata.error`, else `0`.

> **Running the CLI examples below.** `clio-author` is a console script inside the project's `uv`
> environment, not on your global `PATH`. Prefix every example with **`uv run`** (e.g.
> `uv run clio-author ingest 2601.23265`), or activate the venv once (`source .venv/bin/activate`)
> and call `clio-author` directly. Actions needing a heavy extra take the matching flag on the run
> (`uv run --extra pdf clio-author ingest …`). The bare `clio-author …` form shown below assumes an
> activated venv.

> **Output format (`structured` vs `prose`).** Every action defaults to `structured` — JSON for a
> host agent to branch on. Pass `--format prose` (CLI flag on dedicated text subcommands) or
> `{"format": "prose"}` in any payload to get a human-readable text answer instead: `structured`
> becomes `null` and the prose lands in `content`. `review` has the model *write* the prose; the
> data-shaped actions (`cite`, `meta_review`, `kg`, `describe_figures`, `coherence`)
> render their result as text.

> **File inputs for large payloads.** Every action that accepts blocks, sections, candidates, or
> source text has a companion `--*-file` flag (e.g. `--blocks-file`, `--paper-file`,
> `--sections-file`, `--markdown-file`, `--text-file`, `--candidates-file`, `--source-file`). Use
> these for real papers: a 200 KB+ inline `--blocks-json` hits the shell's argument-list limit.
> File inputs read UTF-8 text; JSON file inputs are parsed as JSON.

> **Saving results with `--out FILE`.** Every action (including `capabilities`) accepts `--out FILE`
> as a generic output flag. Behavior depends on the file extension:
>
> - **`.json`** — writes the full indented JSON result (`action`, `content`, `structured`,
>   `metadata`).
> - **Any other extension** (`.md`, `.txt`, etc.) — writes the prose `content` string when present
>   and non-empty; falls back to the full JSON when there is no prose (e.g. for
>   structured-only results).
>
> On success, `[saved to FILE]` is printed to stderr; the JSON result is always also printed to
> stdout so piping is unaffected. If the write fails (e.g. a bad path), a warning is printed to
> stderr but the CLI does not error.
>
> This flag is especially useful for the **print-only** actions that have no `out_dir`/`out_path`
> of their own: `ask`, `review`, `edit`, `polish`, `coherence`, and `meta_review`. Previously,
> saving their output required redirecting stdout (`> review.json`); `--out` is simpler and works
> alongside `--format prose`:
>
> ```bash
> clio-author review --paper-file clio-out/2601.23265/paper.md --format prose --out review.md
> clio-author ask   --question "..." --blocks-file clio-out/2601.23265/blocks.json --out answer.json
> clio-author polish --text-file draft.md --voice concise --format prose --out polished.md
> ```
>
> The structured-artifact actions (`ingest`, `cite`, `kg`, `compose`, `export`) still write their
> primary artifacts via `out_dir`/`out_path` payload keys (see individual action entries). `--out`
> complements those — it is the one place to capture the adapter result dict itself.

---

## Action catalog (25 actions)

Payload keys below are exactly the keys each expert reads. Keys marked *(optional)* have a fallback.

---

### 1. `ingest`

Convert an arXiv id / URL / local PDF / paper title / topic into clean Markdown + memory blocks.

- **Reads:** `source` (arXiv id, arXiv/HTTP URL, local PDF path, paper title, or topic string);
  `out_dir` *(optional)* — when set, writes `paper.md`, `blocks.json`, and `img/figureN.png` there.
  From the CLI the default is `clio-out/<slug>/` in the current directory; from the library default
  (`out_dir=None`) a temporary directory is used and figures land in `<tmp>/img/`.
- **Returns:** `content` = processed Markdown; `structured` = a `MemoryBlocks` dump (`metadata`,
  `sections`, `figures`); `metadata` = `{extractor, source_url, image_dir, out_dir, wrote}`.
  `wrote` lists the paths of files written to disk.
- **Extra:** requires `pdf` for real extraction (Docling primary, PyMuPDF OCR fallback, lazy-imported).
  Without it the run returns `metadata["error"]` describing the missing dependency.
- **Title/topic resolution** uses the public arXiv Atom API (stdlib, no extra required); it issues
  one HTTP request and returns the top hit. An unresolvable title/topic surfaces as
  `metadata["error"]`.

```bash
clio-author ingest 2601.23265                         # arXiv id
clio-author ingest "Attention Is All You Need"        # paper title
clio-author ingest "transformer self-attention"       # topic
clio-author ingest /path/to/paper.pdf                 # local PDF
```
```python
sub.run("ingest", {"source": "2601.23265", "out_dir": "clio-out/2601.23265"})
agent.ingest("path/to/paper.pdf")
```

---

### 2. `ask`

Answer a question grounded only in the provided memory blocks (selective context injection).

- **Reads:** `question` *(optional — falls back to the task description)*; `blocks` (a `MemoryBlocks`
  or its `model_dump()` dict).
- **Returns:** `content` = the answer; `structured` = `{cited_block_ids, retrieved}`; `metadata` =
  `{k, num_blocks}`.
- **Extra:** `rag` swaps the default deterministic `HashingEmbedder` + in-memory `RagRetriever` for a
  `SentenceTransformer` embedder + LanceDB. A real `LLMClient` is needed for useful answers.
- **File inputs:** `--blocks-file clio-out/2601.23265/blocks.json` (preferred for real papers).

```bash
clio-author ask --question "What is the main result?" \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```
```python
sub.run("ask", {"question": "What is the main result?", "blocks": blocks_dump})
agent.ask("What is the main result?", blocks_dump)
```

---

### 3. `review`

Produce a structured, persona-conditioned peer review. Optionally multimodal: when a vision client
is configured (`CLIO_VISION=gemini`) and figures are supplied, the reviewer looks at each figure
image and folds a description of what it actually shows into the reviewed text.

- **Reads:**
  - `paper` *(optional — falls back to `markdown`, then `blocks`, then the task description)*;
    a `MemoryBlocks` paper is rendered to text.
  - `persona` *(optional `PersonaSpec`)*.
  - `ground` *(optional bool)* — retrieve related prior work via the configured scholar client and
    ground weaknesses/questions in it; adds `metadata["related_work"]`.
  - `figures` *(optional)* — a list of `{figure_id?, image_path, caption?}` dicts to look at with
    vision. When absent, falls back to `blocks.figures` when `blocks` is in the payload.
  - `blocks` *(optional)* — a `MemoryBlocks` dump; figures are drawn from it when `figures` is not
    supplied explicitly.
- **Returns:** `content` = one-line summary (decision + overall); `structured` = a `PaperReview`
  dump (summary, strengths, weaknesses, questions, limitations, the 1–4 axes, overall 1–10,
  confidence, decision); `metadata` = `{persona, decision, overall}`. With vision active and figures
  supplied, `metadata` also carries `vision_review=True` and `figures_seen` (count of figures whose
  image was successfully described). If the LLM response has no parseable JSON, `structured` is
  `null` and `metadata["parse_error"]` is set.
- **Extra:** none; needs a real `LLMClient` to produce a parseable review. Vision path needs
  `CLIO_VISION=gemini` and a `GEMINI_API_KEY`.
- **File inputs:** `--paper-file clio-out/2601.23265/paper.md`; `--figures-file figures.json` (or
  `--figures-json '[{...}]'` inline).

```bash
# text-only review:
clio-author review --paper-file clio-out/2601.23265/paper.md --format prose

# multimodal review — reviewer sees the actual figure images:
CLIO_VISION=gemini GEMINI_API_KEY=... \
clio-author review --paper-file clio-out/2601.23265/paper.md \
  --figures-file clio-out/2601.23265/figures.json --format prose
```
```python
# text-only:
sub.run("review", {"paper": "# Title\n\nAbstract..."})

# multimodal (figures list + vision client configured):
sub.run("review", {
    "paper": "# Title\n\nAbstract...",
    "figures": [{"figure_id": 1, "image_path": "clio-out/2601.23265/img/figure1.png", "caption": "Overview"}],
})
# or supply blocks and let the reviewer pull figures from them:
sub.run("review", {"paper": "# Title\n\nAbstract...", "blocks": blocks_dump})
```

---

### 4. `meta_review`

Aggregate several reviews into a single area-chair meta-review (deterministic, offline).

- **Reads:** `reviews` *(optional — a list of `PaperReview`/dicts; when absent, recovers reviewer
  outputs from the session history)*.
- **Returns:** `content` = meta-decision summary; `structured` = a `MetaReview` dump (per-axis
  rounded means, merged text fields, OR-ed ethical concerns, decision, `reviewer_count`); `metadata`
  = `{decision, overall, reviewer_count}`.
- **Extra:** none. Aggregation is offline arithmetic. Reachable via `clio-author run meta_review`.

```bash
clio-author run meta_review \
  --json '{"reviews": [{"Overall": 7, "Decision": "Accept"}, {"Overall": 5, "Decision": "Reject"}]}'
```
```python
sub.run("meta_review", {"reviews": [review_a_dump, review_b_dump]})
```

---

### 5. `rebuttal`

Draft an author rebuttal that addresses a peer review point by point, grounded strictly in the
paper, inventing no new results or citations.

- **Reads:**
  - `paper` *(optional — falls back to `draft`, then `markdown`)*; a `MemoryBlocks` paper is
    rendered to text.
  - `review` *(optional)* — a `PaperReview` object or its `model_dump()` dict; weaknesses and
    questions are rendered into directive text via `render_review_feedback`.
  - `review_text` *(optional)* — free-form review text string (used when `review` is not a
    structured `PaperReview`).
  - `critic_notes` *(optional)* — alias for `review_text`.
  - `target` *(optional)* — when set with a `SafeFiles`, the rebuttal is written to this file.
- **Returns:** `content` = the rebuttal prose; `structured` = `{rebuttal}` (same text);
  `metadata` = `{wrote}` (paths written, when `target` was set). Missing `paper`/`review` inputs
  produce an error-flagged output; the expert never raises.
- **Extra:** none; needs a real `LLMClient` for useful prose.
- **File inputs:** `--paper-file clio-out/2601.23265/paper.md`; `--review-file review.json` (or
  `--review-json '{...}'` inline).

```bash
# respond to a structured review saved from a prior review run:
clio-author rebuttal \
  --paper-file clio-out/2601.23265/paper.md \
  --review-file clio-out/2601.23265/review.json \
  --format prose --out rebuttal.md

# respond to a loose dict of weaknesses + questions:
CLIO_LLM=claude clio-author rebuttal \
  --paper-file clio-out/2601.23265/paper.md \
  --review-json '{"weaknesses":["no baseline comparison","evaluation unclear"],"questions":["how is X measured?"]}' \
  --format prose
```
```python
sub.run("rebuttal", {
    "paper": "# Title\n\nAbstract...",
    "review": review_dump,          # PaperReview model_dump()
})
# or free-form review text:
sub.run("rebuttal", {
    "paper": "# Title\n\nAbstract...",
    "review_text": "Weakness 1: ...\nQuestion 1: ...",
})
```

---

### 6. `cite`

Verify citation candidates against scholarly metadata backends and emit **suggestions only**.

- **Reads:** `candidates` *(optional — falls back to `references`)*, a list of `{title, year?,
  reason?}`; `out_dir` *(optional)* — when set, writes `suggested.bib` and
  `suggested_citation_map.json` there.
- **Returns:** `content` = a verified-coverage summary; `structured` = `{verified, suggested_bibtex,
  citation_map, coverage}` (coverage carries the ≥90% target check); `metadata` = `{num_candidates,
  num_verified, meets_90pct, wrote}`.
- **Safety:** never overwrites; refuses any target named `references.bib`, any existing file, or a
  symlink (atomic `O_CREAT|O_EXCL|O_NOFOLLOW` write).
- **Backends:** resolved from `CLIO_SCHOLAR` — see the [Citation backends](#citation-backends-clio_scholar)
  section below.
- **Extra:** the verification logic is pure stdlib (difflib fallback). The `scholar` extra adds
  Semantic Scholar's `httpx` path and `thefuzz`; no-key fallbacks work from the core install.
- **File inputs:** `--candidates-file refs.json`.

```bash
clio-author cite \
  --candidates-json '[{"title": "Attention Is All You Need", "year": 2017}]'
```
```python
from clio_author.retrieval.scholar import FakeScholarClient

agent = ClioAuthorAgent(scholar_client=FakeScholarClient(...))
agent.cite([{"title": "Attention Is All You Need", "year": 2017}], out_dir="/tmp/suggestions")
```

---

### 7. `plan`

Turn an idea (or a provided `PaperOutline`) into per-section **writing plans**: ordered tasks,
claims, sources/evidence, refined word budgets, and citation hints — one `SectionPlan` per section.
These plans are exactly what `write` / `compose` consume via the `section_plan` payload key.

- **Reads:**
  - `idea` *(optional)* — research idea / thesis text; used to generate an outline when none is
    provided.
  - `experimental_log` *(optional)* — results notes folded into the per-section prompts.
  - `outline` *(optional)* — a `PaperOutline` / loose dict; when supplied the outline step is
    skipped and only the per-section plans are generated.
  - `blocks` *(optional)* — `MemoryBlocks` for grounding the plans.
  - `candidates` *(optional)* — citation candidates `[{title, year?}]` folded into citation hints.
  - `out_dir` *(optional)* — when set, writes `plan.json` there.
- **Returns:** `content` = a one-line summary; `structured` = a list of `SectionPlan` dicts
  (each with `tasks`, `claims`, `sources`, `word_budget`, `citation_hints`); `metadata` =
  `{num_sections, plan_errors, wrote}`. A section whose plan JSON fails to parse falls back to a
  `SectionPlan` wrapping the bare outline with empty tasks (counted in `plan_errors`) rather than
  aborting. Each `SectionOutline` in the plan includes `research_needed` (bool) and
  `research_topics` (list of strings) that flag sections benefiting from a `research` action call
  before drafting.
- **Extra:** none; needs a real `LLMClient` for useful plans. Degrades gracefully to echo-path
  fallbacks offline.
- **File inputs:** `--idea-file`, `--log-file`, `--outline-file`, `--blocks-file`,
  `--candidates-file`.

```bash
clio-author plan \
  --idea "Propose a new attention mechanism for long-range dependencies." \
  --outline-json '{"title":"Attention++","sections":[{"title":"Introduction","goal":"Motivate the problem."}]}' \
  --out-dir clio-out/mypaper

# From files:
clio-author plan --idea-file idea.txt --log-file log.txt \
  --outline-file outline.json --blocks-file clio-out/2601.23265/blocks.json \
  --out-dir clio-out/mypaper
```
```python
result = sub.run("plan", {
    "idea": "Propose a new attention mechanism for long-range dependencies.",
    "outline": {"title": "Attention++", "sections": [{"title": "Introduction", "goal": "..."}]},
    "out_dir": "clio-out/mypaper",
})
# Pass the returned plans directly to write:
plans = result["structured"]   # list of SectionPlan dicts
sub.run("write", {"section_plan": plans[0], "source": "..."})
```

---

### 8. `research`

Produce a grounded literature brief for a topic or section: foundational works, recent work,
competing/alternative approaches, open gaps, a synthesis, and confidence. When a scholar client is
configured, each proposed title is verified against it so the brief is grounded in real records
rather than fabricated ones.

- **Reads:**
  - `topic` *(optional — falls back to `section` + `outline` joined with " - ")*.
  - `section` *(optional)* — section name used when no `topic` is given.
  - `outline` *(optional)* — outline context used when no `topic` is given.
  - `blocks` *(optional)* — `MemoryBlocks` for grounding context.
  - `source` *(optional)* — raw text grounding context.
  - `depth` *(optional, `"standard"` | `"deep"`)* — `deep` asks for more sources and precise gaps.
  - `discover` *(optional, bool)* — when `True` and a scholar client is configured, seeds the
    brief's `recent` bucket from real papers found via `discover_papers` before LLM synthesis. Passes
    `limit` (default 10) and `cutoff_date` through to the discovery call.
  - `out_dir` *(optional)* — not currently written by the expert; available for future use via
    `--json '{"out_dir":"..."}'`.
- **Returns:** `content` = a one-line summary (sources, grounded count, gaps, confidence);
  `structured` = a `ResearchBrief` dump (`topic`, `foundational`, `recent`, `competing`, each a list
  of `{title, note, year, grounded, verified_title}`; `gaps`, `synthesis`, `confidence`,
  `recommendations`); `metadata` = `{num_sources, confidence, grounded}`. With no parseable JSON
  (echo path), flags `parse_error` and returns an empty brief — never invents verified citations.
- **Extra:** none for the LLM call. Scholar verification is best-effort; a scholar failure per source
  simply leaves that source ungrounded.
- **File inputs:** `--topic-file`; also `--blocks-file`.

```bash
# By topic:
CLIO_LLM=claude clio-author research \
  --topic "attention mechanisms for long-range dependencies" --format prose

# Deep research with scholar grounding:
CLIO_SCHOLAR=auto CLIO_LLM=claude clio-author research \
  --topic "transformer self-attention" --depth deep --format prose \
  --out research.md

# Seed the brief from real discovered papers:
CLIO_SCHOLAR=auto CLIO_LLM=claude clio-author research \
  --topic "transformer self-attention" --json '{"discover":true}' --format prose

# Section-specific research via --json:
CLIO_LLM=claude clio-author research \
  --json '{"section":"Related Work","outline":"AUTHOR: multi-agent paper lifecycle"}' \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```
```python
sub.run("research", {"topic": "attention mechanisms for long-range dependencies", "depth": "deep"})
# With scholar grounding (CLIO_SCHOLAR configured):
sub.run("research", {"topic": "transformer self-attention", "blocks": blocks_dump})
# With real papers seeding the recent bucket:
sub.run("research", {"topic": "transformer self-attention", "discover": True})
```

---

### 9. `discover`

Find real candidate papers for a topic via scholarly search (Semantic Scholar / OpenAlex / Crossref /
arXiv). Deterministic — no LLM call. Returns only records the search actually returns; never
fabricates titles, authors, or identifiers. Complements `cite` (which verifies titles you already
have) and `research` (which has the LLM *propose* plausible titles).

- **Reads:** `query` (or `topic` as a fallback — first non-empty string wins); `limit` *(optional,
  int, default 10)*; `cutoff_date` *(optional, `"YYYY-MM"` string)*; `out_dir` *(optional)* —
  when set, writes `discovered.json` and `discovered.bib` there.
- **Returns:** `content` = a one-line summary ("Discovered N paper(s) for '…'");
  `structured` = `{papers: [{title, year, authors, venue, abstract, paper_id, url}], count}`;
  `metadata` = `{count, backends_tried, wrote}`. With no scholar client configured (the default
  hermetic path) returns an error-flagged output — never raises.
- **Safety:** never overwrites existing `discovered.json` / `discovered.bib` files (skips on
  conflict); writes are best-effort.
- **Backends:** resolved from `CLIO_SCHOLAR` — see the [Citation backends](#citation-backends-clio_scholar)
  section below. Needs a configured scholar client.
- **Extra:** the `scholar` extra adds the Semantic Scholar `httpx` path; OpenAlex, Crossref, and
  arXiv use stdlib HTTP and need no extra.
- **File inputs:** `--query-file FILE` (query text from file).
- **CLI flags:** `--query`, `--query-file`, `--limit`, `--cutoff-date`, `--out-dir`, `--format`,
  `--json`, `--out`.

```bash
# Find up to 5 real papers:
CLIO_SCHOLAR=auto clio-author discover \
  --query "retrieval augmented generation" --limit 5 --out-dir clio-out/discovered

# With a recency gate and arXiv backend:
CLIO_SCHOLAR=arxiv clio-author discover \
  --query "large language model evaluation" --limit 10 --cutoff-date 2024-01

# From a file:
CLIO_SCHOLAR=auto clio-author discover --query-file topic.txt --limit 5
```
```python
sub.run("discover", {"query": "retrieval augmented generation", "limit": 5, "out_dir": "clio-out/discovered"})
# topic key is accepted as a fallback for query:
sub.run("discover", {"topic": "transformer self-attention", "limit": 10})
```

---

### 10. `verify_work`

Goal-backward check of written prose against the claims it was supposed to make. For each intended
claim, determines whether the prose actually states it (`made`) and whether it is supported with
evidence or argument (`supported`). The overall verdict (`VERIFIED` / `GAPS`) is derived
deterministically from the per-claim results.

- **Reads:**
  - Claims from `claims` (explicit list of strings) or from `section_plan` (a `SectionPlan` /
    loose dict; uses its `claims` field).
  - Prose from `text` / `markdown` / `draft` (first non-empty string).
- **Returns:** `content` = a one-line summary (status, counts); `structured` = a `VerifyResult`
  dump: `{claims: [{claim, made, supported, evidence, gap}], gaps[], status}`; `metadata` =
  `{num_claims, num_gaps, status}` where `status` ∈ `{"VERIFIED", "GAPS"}`.
  With no parseable JSON (echo path), flags `parse_error` and returns `status="GAPS"` — never
  fabricates a VERIFIED verdict.
- **Extra:** none; needs a real `LLMClient` for useful per-claim judgements.
- **File inputs:** `--text-file`; `--section-plan-file`.

```bash
CLIO_LLM=claude clio-author verify-work \
  --text-file clio-out/mypaper/sections/01-introduction.md \
  --claims-json '["AUTHOR unifies ingestion, review, and writing","The harness is grounded"]' \
  --format prose

# From a saved SectionPlan:
CLIO_LLM=claude clio-author verify-work \
  --text-file clio-out/mypaper/sections/01-introduction.md \
  --section-plan-file clio-out/mypaper/plan.json --format prose
```
```python
sub.run("verify_work", {
    "text": "AUTHOR is a multi-agent harness that...",
    "claims": ["AUTHOR unifies ingestion, review, and writing"],
})
# Or from a SectionPlan:
sub.run("verify_work", {
    "text": section_draft,
    "section_plan": plan_dict,   # SectionPlan.model_dump()
})
```

---

### 11. `write`

Draft a single paper section grounded in scoped source material.

- **Reads:** `outline` or `section_plan` (a `SectionOutline`/`SectionPlan` or loose dict — title,
  `section_path`, `goal`, `word_budget`, `citation_hints`, `figure_refs`); section source from
  `blocks` (a `MemoryBlocks`, scoped to the section) or `source`/`materials` *(optional — falls back
  to the task description)*; `vision` *(optional)*; `out_path` *(optional)* — writes the draft under
  the `SafeFiles` root when `files` is configured.
- **Returns:** `content` = the draft prose; `structured` = `{section_path, draft, out_path,
  word_count}`; `metadata` = `{phase, wrote, summary}`.
- **Extra:** none; needs a real `LLMClient` for useful prose.
- **File inputs:** `--source-file clio-out/2601.23265/paper.md`.

```bash
clio-author write --outline "Methods" \
  --source-file clio-out/2601.23265/paper.md --format prose
```
```python
sub.run("write", {"outline": {"title": "Methods", "goal": "Describe the pipeline."}, "source": "..."})
agent.write(outline={"title": "Methods"}, source="...")
```

---

### 12. `edit`

Revise existing prose to address reviewer feedback (one-shot).

- **Reads:** `draft` *(optional — falls back to `session.data["draft"]`, then `files.read(target)`)*;
  feedback from `review` (a `PaperReview`) or `critic_notes` *(optional — falls back to
  `session.data["critic_feedback"]`)*; `target` *(optional)* — when set with a `SafeFiles`, applies
  the revision to that file via a whole-body diff edit.
- **Returns:** `content` = revised text; `structured` = `{revised, target, word_count}`; `metadata` =
  `{wrote}`.
- **Extra:** none; needs a real `LLMClient`. File edits require a `SafeFiles`.

```python
sub.run("edit", {"draft": "...", "review": review_dump})
agent.edit("...", review_dump)
```

---

### 13. `polish`

Polish existing prose for clarity, flow, and academic voice **without changing meaning or removing
citations**.

- **Reads:** prose from `text` (inline string) or `draft` *(optional — falls back to
  `session.data["draft"]`, then `task.description`)*; `voice` *(optional)* — a target voice
  directive (e.g. `"concise"`, `"formal"`); `target` *(optional)* — when set with a `SafeFiles`,
  applies the polished text to that file (whole-body replace).
- **Returns:** `content` = the polished prose; `structured` = `{polished, voice}`; `metadata` =
  `{wrote}`.
- **Invariants:** every `\cite{key}` placeholder and every figure reference is preserved exactly.
  The expert never adds facts or changes claims.
- **Extra:** none; needs a real `LLMClient` to produce improved prose.
- **File inputs:** `--text-file clio-out/mypaper/sections/01-introduction.md`.

```bash
clio-author polish --text-file clio-out/mypaper/sections/01-introduction.md \
  --voice concise --format prose
```
```python
sub.run("polish", {"text": "...", "voice": "concise"})
sub.run("polish", {"text": "...", "target": "sections/01-introduction.md"})
```

---

### 14. `coherence`

Check **cross-section consistency** of a manuscript — terminology drift, contradictions, undefined
terms, duplication, and broken narrative flow.

- **Reads:** sections via one of:
  - `sections` — compose's `[{title, draft}]` list,
  - `markdown` — a full manuscript split on `## ` headings,
  - `text` *(optional fallback)* — a single passage (treated as one untitled section).
- **Returns:** `content` = human-readable issue summary; `structured` =
  `{issues: [{kind, sections, detail}], summary}` (kinds: `terminology`, `contradiction`,
  `undefined`, `duplication`, `flow`); `metadata` = `{num_sections, num_issues}`.
  If the LLM response has no parseable JSON, `structured` is `null` and `metadata["parse_error"]`
  is set.
- **Extra:** none; needs a real `LLMClient` for useful analysis.
- **File inputs:** `--markdown-file clio-out/mypaper/paper.md` or `--sections-file sections.json`.

```bash
clio-author coherence --markdown-file clio-out/mypaper/paper.md --format prose
```
```python
sub.run("coherence", {"markdown": manuscript_text})
sub.run("coherence", {"sections": [{"title": "Introduction", "draft": "..."}, ...]})
```

---

### 15. `check_refs`

Deterministically lint a BibTeX bibliography and cross-check it against the `\cite{}` keys used in
the manuscript prose. Flags malformed entries, duplicate entries, cited-but-missing keys, and
uncited entries. **No LLM call** — always produces a real result, even with the offline echo model.
Emits suggestions only; never modifies any file.

- **Reads:** `bibtex` *(optional)* — a BibTeX string; `markdown` / `text` *(optional)* — prose to
  scan for `\cite{}` keys; `sections` *(optional)* — compose's `[{title, draft}]` list (joined as
  prose). At least one of `bibtex` or prose is required.
- **Returns:** `content` = a one-line issue count summary; `structured` = `{malformed[],
  duplicates[], missing_in_bib[], uncited_entries[], counts}`; `metadata` = counts dict
  (`num_entries`, `num_cited`, `num_malformed`, `num_duplicates`, `num_missing_in_bib`,
  `num_uncited_entries`).
- **Extra:** none; pure Python (no model, no network).
- **File inputs:** `--bibtex-file references.bib`; `--markdown-file paper.md`.

```bash
clio-author check-refs \
  --bibtex-file clio-out/mypaper/references.bib \
  --markdown-file clio-out/mypaper/paper.md

# Inline bibtex + text:
clio-author check-refs \
  --bibtex "@article{key1, title={...}, ...}" \
  --text "We follow \cite{key1} and extend \cite{key2}."
```
```python
sub.run("check_refs", {"bibtex": bibtex_string, "markdown": manuscript_text})
```

---

### 16. `section_review`

Three-layer review of a **single section**: L1 deterministic reference/citation checking
(`check_refs`) → L2 single-section coherence (`coherence`) → L3 persona-conditioned peer review
(`reviewer`). The aggregate severity summary is derived deterministically from the three layer
results — no additional model call for the aggregation.

Severity rules (deterministic): a cited key with no matching bibliography entry is `critical`; a
`contradiction` coherence issue is `major`; a reviewer overall rating below 5 is `major`.

- **Reads:**
  - Section text from `section` / `text` / `markdown` / `draft` (first non-empty).
  - `bibtex` *(optional)* — for the L1 reference check.
  - `persona` *(optional, `PersonaSpec` / loose dict)* — for the L3 reviewer.
  - `out_dir` *(optional)* — available for future persistence; not currently written.
- **Returns:** `content` = a one-line verdict; `structured` = `{layer1, layer2, layer3,
  severity_summary: [{layer, severity, detail}]}`; `metadata` = `{num_findings, max_severity}`.
  L2 and L3 require a real `LLMClient`; L1 always runs deterministically.
- **Extra:** none; L1 is offline, L2/L3 need a real model.
- **File inputs:** `--text-file`; `--bibtex-file`; persona via `--persona-json`.

```bash
CLIO_LLM=claude clio-author section-review \
  --text-file clio-out/mypaper/sections/01-introduction.md \
  --bibtex-file clio-out/mypaper/references.bib --format prose

# With a custom persona:
CLIO_LLM=claude clio-author section-review \
  --text-file clio-out/mypaper/sections/02-methods.md \
  --persona-json '{"label":"strict methods reviewer"}' --format prose
```
```python
sub.run("section_review", {
    "text": section_text,
    "bibtex": bibtex_string,
    "persona": {"label": "strict methods reviewer"},
})
```

---

### 17. `audit`

Deterministic manuscript completeness audit: required sections present, per-section word-count vs
budget, unresolved `[TODO]`/`[CITE:]`/empty `\cite{}` placeholders, and citation coverage. **No
LLM call** — always produces a real result. Emits a checklist and verdict; never modifies the
manuscript.

- **Reads:**
  - `sections` — a list of `{title, draft, word_budget?}` dicts **or** `markdown` (split on `## `
    headings). At least one is required.
  - `outline` *(optional, `PaperOutline` / loose dict)* — provides the required section titles for
    the presence check.
  - `bibtex` *(optional)* — for citation-coverage checking.
  - `candidates` *(optional)* — citation candidates for the ≥90% verified-coverage target.
  - `verified` *(optional)* — pre-verified citations from a prior `cite` run.
- **Returns:** `content` = a one-line verdict ("Audit PASSED" or "Audit FOUND ISSUES: …");
  `structured` = `{missing_sections[], word_counts[], placeholders, coverage}`; `metadata` =
  `{passed, num_sections, num_problems}`.
- **Extra:** none; pure Python (no model, no network).
- **File inputs:** `--sections-file`; `--markdown-file`; `--bibtex-file`; outline via `--json`.

```bash
# From a whole manuscript file:
clio-author audit \
  --markdown-file clio-out/mypaper/paper.md \
  --bibtex-file clio-out/mypaper/references.bib

# With an outline for required-section presence check:
clio-author audit \
  --sections-file clio-out/mypaper/sections.json \
  --bibtex-file clio-out/mypaper/references.bib \
  --json '{"outline":{"title":"AUTHOR","sections":[{"title":"Introduction"},{"title":"Method"},{"title":"Conclusion"}]}}'
```
```python
sub.run("audit", {
    "markdown": manuscript_text,
    "bibtex": bibtex_string,
    "outline": {"title": "AUTHOR", "sections": [{"title": "Introduction"}, {"title": "Method"}]},
})
```

---

### 18. `kg`

Extract a content knowledge graph of a paper -- its claims, methods, datasets, results, metrics,
concepts, and tasks plus the relations between them -- from the paper's memory blocks. This is the
paper's *content* graph, distinct from any citation / literature graph.

Two extraction modes:

- **Single-shot** (default): the LLM extracts the graph in one pass from the blocks' text.
- **Multi-stage pipeline** (`full=True` or a non-empty `stages` list): runs six sequential stages
  (metadata → ontology → extraction → coref → verification → summary), writing per-stage checkpoint
  files under `<out_dir>/kg_pipeline/`. A prior run's checkpoints can be resumed by passing them
  back in `checkpoints` (Python) or `--resume DIR` (CLI).

- **Reads:** `blocks` (a `MemoryBlocks` or its dump); `max_sections` *(optional cap on sections,
  single-shot only)*; `full` *(optional bool)* — run the pipeline; `stages` *(optional comma-
  separated string or list)* — restrict pipeline stages; `checkpoints` *(optional dict)* — seed
  resume; `out_dir` *(optional)*.
- **Returns:** `content` = a one-line summary (or a Mermaid `graph TD` rendering with
  `format=prose`); `structured` = `{nodes, edges}` (each node `{id, label, type, description,
  section_path}`; each edge `{source, target, relation}`; edges whose endpoints are not nodes are
  dropped); `metadata` = `{num_nodes, num_entities, num_edges, wrote}`. Pipeline runs also set
  `metadata["pipeline"]` (stage report) and `metadata["checkpoints"]` (updated checkpoint map). An
  unparseable LLM response flags `metadata["parse_error"]` and returns an empty graph (never raises).
- **Writes:** when `out_dir` is set, writes `<out_dir>/kg.json` and `<out_dir>/kg.mmd` (Mermaid).
  Pipeline mode additionally writes `<out_dir>/kg_pipeline/<stage>.json` for each stage.
- **CLI flags:** `--full`, `--stages <comma-list>`, `--resume <dir>`, `--out-dir`.

```bash
# Single-shot (default):
clio-author kg --blocks-file clio-out/2601.23265/blocks.json --format prose

# Full 6-stage pipeline with checkpoints:
clio-author kg --blocks-file clio-out/2601.23265/blocks.json \
  --full --out-dir clio-out/2601.23265/kg-pipeline

# Resume an interrupted pipeline run:
clio-author kg --blocks-file clio-out/2601.23265/blocks.json \
  --full --resume clio-out/2601.23265/kg-pipeline \
  --out-dir clio-out/2601.23265/kg-pipeline

# Run only specific stages:
clio-author kg --blocks-file clio-out/2601.23265/blocks.json \
  --stages metadata,ontology --out-dir clio-out/2601.23265/kg-pipeline
```
```python
# Single-shot:
sub.run("kg", {"blocks": blocks_dump, "out_dir": "clio-out/2601.23265"})

# Full pipeline with resume:
sub.run("kg", {
    "blocks": blocks_dump,
    "full": True,
    "checkpoints": prior_checkpoint_dict,   # {} on first run
    "out_dir": "clio-out/2601.23265/kg-pipeline",
})
```

---

### 19. `describe_figures`

Fill in descriptions/captions for figures in memory blocks.

- **Reads:** `blocks` (a `MemoryBlocks` whose `figures` get described) **or** `figures` (a list of
  `FigureInfo`/dicts); `context` *(optional surrounding text)*. Caller objects are deep-copied, so
  describing never mutates the input.
- **Returns:** `content` = a "described N of M" summary; `structured` = `{descriptions[],
  blocks?}` (each description = `{figure_id, description, caption}`; the updated `blocks` dump is
  included when blocks were supplied); `metadata` = `{mode: "describe", num_described}`.
- **Vision path (optional):** with `CLIO_VISION=gemini` and a valid `GEMINI_API_KEY`, the figure
  agent *looks at* the actual image file (from `figure.image_path`) and returns a Gemini-generated
  caption. Without vision, the expert writes a text description from the block's metadata only.
  See the [Gemini vision](#gemini-vision-clio_visiongemini) section below.
- **File inputs:** `--blocks-file clio-out/2601.23265/blocks.json`.

```bash
clio-author describe --blocks-file clio-out/2601.23265/blocks.json --format prose
```
```python
sub.run("describe_figures", {"figures": [{"figure_id": 1, "caption": "..."}]})
agent.describe_figures(blocks_dump)
```

---

### 20. `plot`

Generate matplotlib plot **code** (text only; never executed on this path).

- **Reads:** `spec` (a `PlotSpec` or loose dict — `kind` (`"plot"` or `"diagram"`), `intent`,
  `data_hint`, `aspect_ratio`); `out_path` *(optional)* — when set with a `SafeFiles`, writes the
  code there.
- **Returns:** `content` = the extracted Python code; `structured` = `{artifact, out_path}` (artifact
  = `{kind: "plot", code}`); `metadata` = `{mode: "plot", phase, wrote}`.
- **Vision path (optional):** with `CLIO_VISION=gemini`, `spec.kind="diagram"` generates a real
  image PNG using Gemini's image generation API instead of matplotlib code. `spec.kind="plot"` always
  uses the matplotlib code path.
- **Extra:** `viz` (matplotlib) is only needed for the **gated** `render_plot_code` helper, which
  runs the code in a subprocess (`Agg` backend, timeout). Nothing in the default action renders.

```bash
clio-author run plot \
  --json '{"spec": {"kind": "plot", "intent": "bar chart of accuracy by model"}}'
```
```python
sub.run("plot", {"spec": {"kind": "plot", "intent": "bar chart of accuracy by model"}})
agent.plot({"kind": "plot", "intent": "bar chart of accuracy by model"})
```

---

### 21. `compose`

**Whole-paper orchestration.** Drafts a full multi-section manuscript from an idea and optional
experimental log, chaining the existing experts in sequence.

Pipeline: build (or accept) an outline → best-effort citation verification → write each section
(optionally through a per-section writer ↔ reviewer loop) → assemble Markdown → optionally export
LaTeX. Each section is written in a fresh `SessionContext` so state does not leak between sections.

- **Reads:**
  - `idea` — research idea / thesis text (required unless `outline` is given).
  - `experimental_log` *(optional)* — results notes fed to the section writers.
  - `outline` *(optional)* — a `PaperOutline` / loose dict; skips LLM outline generation.
  - `candidates` *(optional)* — citation candidates `[{title, year?}]`; verified before writing.
  - `blocks` *(optional)* — `MemoryBlocks` for grounding section drafts.
  - `review` *(optional, bool)* — run a per-section writer/reviewer refine loop.
  - `max_rounds` *(optional, int, default 3)* — max refine rounds per section.
  - `plan` *(optional, bool)* — run the planner per section before drafting (generates
    `SectionPlan` tasks/claims/sources to guide the writer).
  - `out_dir` *(optional)* — when set, persists `paper.md` + `sections/NN-slug.md`.
  - `latex` *(optional, bool)* — also emit `paper.tex` + `references.bib` alongside the Markdown.
  - `pdf` *(optional, bool)* — compile `paper.pdf` from the written `paper.tex` (implies `latex`;
    tries `tectonic`, then `latexmk`, then `pdflatex` in order; needs `--out-dir`; on success adds
    `metadata["pdf"]` = PDF path; on failure adds `metadata["pdf_error"]` = reason; never fails
    the compose itself).
- **Returns:** `content` = the assembled Markdown manuscript; `structured` = `{outline, sections,
  citations}`; `metadata` = `{num_sections, reviewed, wrote, section_errors, latex}`.
  `wrote` lists every file written to disk. With `pdf=True`, also `metadata["pdf"]` (path) or
  `metadata["pdf_error"]` (reason).
- **Extra:** none; needs a real `LLMClient` for useful drafts. Citation verification needs a
  scholar backend.
- **File inputs:** `--idea-file idea.txt`, `--log-file log.txt`, `--outline-file outline.json`,
  `--candidates-file refs.json`.

```bash
# Minimal: idea only (offline echo produces placeholder sections)
clio-author compose --idea "A new attention mechanism for long-range dependencies."

# Full: real model + review loop + LaTeX output
CLIO_LLM=claude uv run clio-author compose \
  --idea "A new attention mechanism for long-range dependencies." \
  --log "WikiText-103 experiments: BLEU +2.1 over baseline." \
  --candidates-file refs.json \
  --review --max-rounds 2 \
  --out-dir clio-out/mypaper \
  --latex

# Compile PDF in the same call (needs tectonic/latexmk/pdflatex on PATH):
CLIO_LLM=claude uv run clio-author compose \
  --idea "A new attention mechanism for long-range dependencies." \
  --review --out-dir clio-out/mypaper --pdf

# Outputs (--pdf):
#   clio-out/mypaper/paper.md
#   clio-out/mypaper/paper.tex
#   clio-out/mypaper/references.bib
#   clio-out/mypaper/paper.pdf        (if a LaTeX engine is found)
#   clio-out/mypaper/sections/01-introduction.md  (… etc.)
```
```python
result = sub.run("compose", {
    "idea": "A new attention mechanism for long-range dependencies.",
    "experimental_log": "WikiText-103: BLEU +2.1 over baseline.",
    "candidates": [{"title": "Attention Is All You Need", "year": 2017}],
    "review": True,
    "max_rounds": 2,
    "out_dir": "clio-out/mypaper",
    "latex": True,
    "pdf": True,      # compile paper.pdf; sets metadata["pdf"] or metadata["pdf_error"]
})
print("sections:", result["metadata"]["num_sections"])
print("wrote:", result["metadata"]["wrote"])
print("section errors:", result["metadata"]["section_errors"])
```

---

### 22. `export`

Export a composed Markdown manuscript to a standalone LaTeX document (`paper.tex` + optional
`references.bib`).

The converter is pure Python/stdlib — no pandoc, no LaTeX toolchain, no new dependencies. It handles
the Markdown subset the writer emits: headings (`\section` / `\subsection` / `\subsubsection`),
bold / italic / inline code, bullet and numbered lists, Markdown links (rendered as text), and
`\cite{key}` reference markers. Special LaTeX characters are escaped.

- **Reads:** one of:
  - `sections` — compose's `[{title, draft}]` list (preferred when available),
  - `markdown` — a full manuscript string split on `## ` headings.
  Then optionally:
  - `title` *(optional)* — overrides the title extracted from `outline` or the manuscript's `# heading`.
  - `outline` *(optional)* — a `PaperOutline` / dict; its `title` is used when `title` is absent.
  - `bibtex` *(optional, also `suggested_bibtex`)* — BibTeX string appended as `references.bib` and
    referenced via `\bibliography{references}`.
  - `out_dir` *(optional)* — when set, writes `paper.tex` (+ `references.bib` when a bib is present).
  - `pdf` *(optional, bool)* — compile `paper.pdf` from the written `paper.tex` (needs `out_dir`;
    tries `tectonic`, then `latexmk`, then `pdflatex`; on success adds `metadata["pdf"]` = PDF path;
    on failure adds `metadata["pdf_error"]` = reason; never fails the export itself).
- **Returns:** `content` = the full LaTeX source string; `structured` = `{latex, bibtex}`;
  `metadata` = `{wrote, format: "latex", num_sections}`. With `pdf=True`, also `metadata["pdf"]`
  (path on success) or `metadata["pdf_error"]` (reason on failure).
- **Extra:** none; pure stdlib conversion. PDF compilation uses an external LaTeX engine (not
  installed by this package).
- **File inputs:** `--markdown-file clio-out/mypaper/paper.md`, `--bibtex-file refs.bib`,
  `--sections-file sections.json`.
- **CLI flags:** `--title`, `--sections-json`, `--sections-file`, `--markdown-file`,
  `--bibtex-file`, `--out-dir`, `--pdf`, `--json`, `--out`. Note: `export` has no `--format` flag.

```bash
# From a composed paper.md:
clio-author export \
  --markdown-file clio-out/mypaper/paper.md \
  --bibtex-file clio-out/mypaper/references.bib \
  --out-dir clio-out/mypaper

# From compose's structured sections list:
clio-author export \
  --sections-file /tmp/sections.json \
  --title "My Paper Title" \
  --out-dir clio-out/mypaper

# Export and compile PDF in one call:
clio-author export \
  --markdown-file clio-out/mypaper/paper.md \
  --bibtex-file clio-out/mypaper/references.bib \
  --out-dir clio-out/mypaper --pdf
```
```python
result = sub.run("export", {
    "markdown": manuscript_text,
    "bibtex": bibtex_string,
    "out_dir": "clio-out/mypaper",
    "pdf": True,      # compile paper.pdf; sets metadata["pdf"] or metadata["pdf_error"]
})
print(result["content"])    # the .tex source
print(result["metadata"]["wrote"])
# metadata["pdf"] holds the PDF path when compilation succeeded
```

---

### 23. `write_review`

Run a writer ↔ reviewer **critic-refine** loop and return the final output.

- **Reads:** all `write` keys (`outline`/`section_plan`, `blocks`/`source`, `vision`) plus
  `max_rounds` *(optional, default 3)*. The writer drafts, a reviewer-as-critic reviews the draft,
  and the writer revises; the loop stops on an `Accept` (a "No changes needed." sentinel) or an
  error-flagged output.
- **Returns:** the final writer/critic `AgentOutput` of the loop (writer-shaped on the last draft).
- **Extra:** none; a real `LLMClient` drives both producer and critic. Reachable via
  `clio-author run write_review`.

```bash
clio-author run write_review \
  --json '{"outline": {"title": "Methods"}, "source": "...", "max_rounds": 2}'
```
```python
sub.run("write_review", {"outline": {"title": "Methods"}, "source": "...", "max_rounds": 2})
```

---

### 24. `figure_refine`

Run a figure visualizer ↔ critic **critic-refine** loop and return the final output.

- **Reads:** `spec` (forced into `plot` mode), `out_path` *(optional)*, `max_rounds` *(optional,
  default 3)*.
- **Returns:** the final figure `AgentOutput` of the loop (plot-shaped, code in `content`).
- **Extra:** none for the loop itself (code only); `viz` only for the separate gated render.
  Reachable via `clio-author run figure_refine`.

```bash
clio-author run figure_refine \
  --json '{"spec": {"kind": "plot", "intent": "line chart of loss"}, "max_rounds": 2}'
```
```python
sub.run("figure_refine", {"spec": {"kind": "plot", "intent": "line chart of loss"}, "max_rounds": 2})
```

---

### 25. `orchestrate`

Plan and run a sequence of the other actions to achieve a natural-language **goal** (dynamic
multi-step). An LLM proposes a minimal ordered plan of action calls, which are executed through the
router; `@name` references in a step's payload are resolved from prior steps / supplied `inputs`.

- **Reads:** `goal` *(required)*; `inputs` *(optional dict of named values, referenced as `@name`)*;
  `max_steps` *(optional, default 6)*; `out_dir` *(optional — persists `orchestrate.json`)*.
- **Returns:** `content` = a per-step summary; `structured` = `{goal, plan, steps, context_keys}`;
  `metadata` = `{num_steps, actions, errors}`. Never recurses into itself; never raises (an
  unparseable plan → an error-flagged output).
- **Extra:** none; needs a real `LLMClient` to produce a plan (the offline echo model returns
  "could not plan for goal"). Reachable via `clio-author orchestrate` or `run orchestrate`.

```bash
CLIO_LLM=claude CLIO_SCHOLAR=auto clio-author orchestrate \
  --goal "Verify the citation, then aggregate the two reviews into a decision." \
  --inputs-json '{"candidates": [{"title": "Attention Is All You Need", "year": 2017}], "reviews": [{"Overall": 7, "Decision": "Accept"}, {"Overall": 5, "Decision": "Reject"}]}'
```
```python
sub.run("orchestrate", {"goal": "...", "inputs": {"source": "2601.23265"}, "max_steps": 4})
```

---

## How the optional extras gate the heavy paths

The core install (`uv sync`) is hermetic — every action runs offline. Heavy dependencies are
lazy-imported only when their action needs them:

| Extra | Gated path | Default behavior without the extra |
|-------|-----------|-----------------------------------|
| `pdf` | `ingest`: Docling extraction + PyMuPDF OCR fallback | `ingest` returns `metadata["error"]` for the missing dependency |
| `rag` | `ask`: `SentenceTransformerEmbedder` + `LanceDbRetriever` | deterministic `HashingEmbedder` + in-memory `RagRetriever` |
| `scholar` | `cite`: Semantic Scholar `httpx` client + `thefuzz` fuzzy match | citation no-key fallbacks still work |
| `viz` | gated `render_plot_code` (subprocess render) | `plot` emits code text only; never renders |
| `mcp` | the MCP bridge (`python -m clio_author.integration.mcp_bridge`, `fastmcp`) so MCP-only hosts can invoke AUTHOR — see [`INTEGRATION.md`](INTEGRATION.md) | bridge unavailable; in-process + CLI transports still work |

Install a subset as needed, e.g. `uv sync --extra pdf --extra scholar`.

---

## Plugging in a real LLM client

Experts default to `EchoLLMClient` (deterministic, offline) so the harness and tests stay hermetic.
That echo path is fine for `ingest` (deterministic), `meta_review` (arithmetic), `cite`
(verification), and the code-extraction parts of `plot` / `describe_figures`, but `ask` / `review`
/ `write` / `edit` / `polish` / `coherence` / `compose` need a **real** provider to produce useful
output.

**Ready-made providers** ship in `clio_author.llm.providers` (stdlib-only, lazy):
`ClaudeCliLLMClient` (the `claude` CLI — session-based, no API key), `CodexCliLLMClient`
(`codex exec`), and `OllamaLLMClient` (a local Ollama server). The **CLI** selects one via the
`CLIO_LLM` env var (`echo` (default) | `claude` | `codex` | `ollama`; model via `CLIO_LLM_MODEL`,
Ollama URL via `CLIO_OLLAMA_URL`).

```bash
CLIO_LLM=claude  clio-author review --paper-file clio-out/2601.23265/paper.md
CLIO_LLM=codex   clio-author write --outline "Introduction" --source-file clio-out/2601.23265/paper.md
CLIO_LLM=ollama  CLIO_LLM_MODEL=qwen2.5:14b clio-author ask \
  --question "..." --blocks-file clio-out/2601.23265/blocks.json
```

For secrets, the CLI automatically loads `.env.local` from the current working directory, without
overriding real environment variables. Set `CLIO_ENV_FILE=/path/to/file` to use a different local
env file. See [`SECURITY.md`](SECURITY.md) for key rotation and handling rules.

In-process, pass a provider directly: `ClioAuthorAgent(llm=ClaudeCliLLMClient())` or
`ClioAuthorSubagent(llm=resolve_llm("claude"))`. To write your own provider, implement:

```python
def complete(self, messages: list[Message], **kwargs: object) -> str: ...
```

`Message` (from `clio_author.harness.types`) has `role` (`"system" | "user" | "assistant" |
"expert"`), `content: str`, and optional `name` / `metadata`. A minimal real client:

```python
from clio_author.harness.types import Message

class MyLLMClient:
    def __init__(self, model: str) -> None:
        import anthropic
        self._client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
        self._model = model

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        system = "\n".join(m.content for m in messages if m.role == "system")
        turns = [
            {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in messages if m.role != "system"
        ]
        resp = self._client.messages.create(
            model=self._model, system=system or None,
            messages=turns, max_tokens=4096,
        )
        return "".join(block.text for block in resp.content if block.type == "text")
```

Inject it at construction; all experts share the one client:

```python
from clio_author import ClioAuthorAgent

agent = ClioAuthorAgent(llm=MyLLMClient(model="..."))
agent.review("# Title\n...")
```

Both `ClioAuthorAgent` and `ClioAuthorSubagent` also accept `files=SafeFiles(root)` (for the
write-capable experts) and `scholar_client=...` (for `cite`).

---

## Citation backends (`CLIO_SCHOLAR`)

`CLIO_SCHOLAR` selects the citation lookup backend (resolved at CLI startup via
`resolve_scholar_client()`):

| Value | Client | Notes |
|-------|--------|-------|
| `auto` / `cascade` *(default)* | `CascadeScholarClient` | Semantic Scholar → OpenAlex → Crossref → arXiv (first hits win) |
| `semantic` / `s2` | `SemanticScholarClient` | `httpx` required (`scholar` extra); reads `SEMANTIC_SCHOLAR_API_KEY` |
| `openalex` / `oa` | `OpenAlexClient` | stdlib HTTP; no key required; set `OPENALEX_MAILTO` for courtesy |
| `crossref` / `cr` | `CrossrefClient` | stdlib HTTP; no key required; set `CROSSREF_MAILTO` for courtesy |
| `arxiv` | `ArxivScholarClient` | stdlib HTTP; no key required; preprint-focused |
| `off` / `none` / `offline` | `None` | Citation expert reports "no scholar client configured" |

`SEMANTIC_SCHOLAR_API_KEY` reduces HTTP 429 rate-limit errors with the Semantic Scholar client. The
client enforces a cross-process 1-request/second minimum interval for CLI runs and retries once after
HTTP 429.

In-process, pass any `ScholarClient` protocol-compatible object directly:
`ClioAuthorAgent(scholar_client=MyScholarClient())`.

---

## Gemini vision (`CLIO_VISION=gemini`)

`CLIO_VISION` selects the optional image-understanding path for the figure agent and the reviewer
(resolved via `resolve_vision_client()`):

| Value | Client | Notes |
|-------|--------|-------|
| `off` / `none` *(default)* | `None` | Figure agent and reviewer stay on the hermetic text/code path; no image API is called |
| `gemini` / `google` | `GeminiVisionClient` | Reads `GEMINI_API_KEY` or `GOOGLE_API_KEY`; uses stdlib `urllib` REST |

When `CLIO_VISION=gemini` is active:

- `describe_figures` *looks at* the real image file for each figure (from `figure.image_path`) and
  returns a Gemini-generated caption. `metadata["vision_described"]` counts the figures described
  this way; `metadata["text_described"]` counts the fallback path.
- `review` with `figures` (or `blocks` containing figures) in the payload *looks at* each figure
  image and folds a factual description into the reviewed text. Sets `metadata["vision_review"]=True`
  and `metadata["figures_seen"]` (count of images successfully described). Without
  `CLIO_VISION=gemini` or without figures, review behaviour is unchanged.
- `plot` with `spec.kind="diagram"` calls Gemini's image generation API and writes a PNG to
  `out_path` instead of returning matplotlib code. `spec.kind="plot"` always uses the code path.

Model overrides:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CLIO_VISION_MODEL` | `gemini-2.5-flash` | Describe-image model |
| `CLIO_IMAGE_MODEL` | `gemini-2.5-flash-image` | Generate-image model |

Construction is hermetic (no network I/O); API calls happen only inside `describe_image` /
`generate_image`. Any `VisionError` is caught per figure and falls back to the text path, so a
vision failure never propagates or aborts a `describe_figures` / `compose` run.

```bash
CLIO_VISION=gemini GEMINI_API_KEY=... clio-author describe \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```

In-process:

```python
from clio_author.llm.vision import GeminiVisionClient
from clio_author import ClioAuthorAgent

vision = GeminiVisionClient(api_key="...", describe_model="gemini-2.5-flash")
agent = ClioAuthorAgent(vision=vision)
agent.describe_figures(blocks_dump)
```

---

## Running gated `live` / `baseline` tests

The default suite is hermetic and deselects the `live` and `baseline` markers
(`addopts = "-m 'not live and not baseline'"`). To run the gated suites, install the relevant extras
and select the marker:

```bash
# Network / real backends (real embeddings, S2 lookups, matplotlib render):
uv sync --extra rag --extra scholar --extra viz
uv run pytest -m live

# Reference-impl comparisons + real-PDF fidelity:
uv sync --extra pdf
uv run pytest -m baseline
```

`live` tests require network and/or real backends (RAG embeddings, Semantic Scholar, plot rendering);
`baseline` tests compare against reference implementations or run real PDFs through the ingest
pipeline. Neither runs in CI's default hermetic pass.

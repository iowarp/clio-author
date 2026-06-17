# clio-parser usage

clio-parser is a standalone multi-agent harness a host invokes either **in-process** (import) or as
a **subprocess** (the `clio-parser` CLI). This document is the full action reference plus the
configuration seams (optional extras, the `LLMClient`, scholar backends, and Gemini vision).

- **Adapter surface** — `ClioParserSubagent` (in `clio_parser.integration.clio_adapter`): two
  methods, `capabilities()` and `run(action, payload)`. Both return JSON-serializable dicts and
  never raise; any failure is captured into an `error` field.
- **Typed surface** — `ClioParserAgent` (in `clio_parser.agent`): the same routing with typed
  convenience methods, returning an `AgentOutput` (`agent`, `content`, `structured`, `metadata`).

Every action degrades gracefully: missing inputs or failures produce an output whose
`metadata["error"]` (or top-level `error`) describes the problem rather than raising.

The CLI maps onto the adapter. `run(action, payload)` returns:

```json
{"action": "...", "content": "...", "structured": {...} | null, "metadata": {...}}
```

The CLI exits `1` when the result has a top-level `error` or `metadata.error`, else `0`.

> **Running the CLI examples below.** `clio-parser` is a console script inside the project's `uv`
> environment, not on your global `PATH`. Prefix every example with **`uv run`** (e.g.
> `uv run clio-parser ingest 2601.23265`), or activate the venv once (`source .venv/bin/activate`)
> and call `clio-parser` directly. Actions needing a heavy extra take the matching flag on the run
> (`uv run --extra pdf clio-parser ingest …`). The bare `clio-parser …` form shown below assumes an
> activated venv.

> **Output format (`structured` vs `prose`).** Every action defaults to `structured` — JSON for a
> host agent to branch on. Pass `--format prose` (CLI flag on dedicated text subcommands) or
> `{"format": "prose"}` in any payload to get a human-readable text answer instead: `structured`
> becomes `null` and the prose lands in `content`. `review` has the model *write* the prose; the
> data-shaped actions (`cite`, `meta_review`, `literature_graph`, `describe_figures`, `coherence`)
> render their result as text.

> **File inputs for large payloads.** Every action that accepts blocks, sections, candidates, or
> source text has a companion `--*-file` flag (e.g. `--blocks-file`, `--paper-file`,
> `--sections-file`, `--markdown-file`, `--text-file`, `--candidates-file`, `--source-file`). Use
> these for real papers: a 200 KB+ inline `--blocks-json` hits the shell's argument-list limit.
> File inputs read UTF-8 text; JSON file inputs are parsed as JSON.

---

## Action catalog (16 actions)

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
clio-parser ingest 2601.23265                         # arXiv id
clio-parser ingest "Attention Is All You Need"        # paper title
clio-parser ingest "transformer self-attention"       # topic
clio-parser ingest /path/to/paper.pdf                 # local PDF
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
clio-parser ask --question "What is the main result?" \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```
```python
sub.run("ask", {"question": "What is the main result?", "blocks": blocks_dump})
agent.ask("What is the main result?", blocks_dump)
```

---

### 3. `review`

Produce a structured, persona-conditioned peer review.

- **Reads:** `paper` *(optional — falls back to `markdown`, then `blocks`, then the task
  description)*; `persona` *(optional `PersonaSpec`)*. A `MemoryBlocks` paper is rendered to text.
- **Returns:** `content` = one-line summary (decision + overall); `structured` = a `PaperReview`
  dump (summary, strengths, weaknesses, questions, limitations, the 1–4 axes, overall 1–10,
  confidence, decision); `metadata` = `{persona, decision, overall}`. If the LLM response has no
  parseable JSON, `structured` is `null` and `metadata["parse_error"]` is set.
- **Extra:** none; needs a real `LLMClient` to produce a parseable review.
- **File inputs:** `--paper-file clio-out/2601.23265/paper.md`.

```bash
clio-parser review --paper-file clio-out/2601.23265/paper.md --format prose
```
```python
sub.run("review", {"paper": "# Title\n\nAbstract..."})
agent.review("# Title\n\nAbstract...")
```

---

### 4. `meta_review`

Aggregate several reviews into a single area-chair meta-review (deterministic, offline).

- **Reads:** `reviews` *(optional — a list of `PaperReview`/dicts; when absent, recovers reviewer
  outputs from the session history)*.
- **Returns:** `content` = meta-decision summary; `structured` = a `MetaReview` dump (per-axis
  rounded means, merged text fields, OR-ed ethical concerns, decision, `reviewer_count`); `metadata`
  = `{decision, overall, reviewer_count}`.
- **Extra:** none. Aggregation is offline arithmetic. Reachable via `clio-parser run meta_review`.

```bash
clio-parser run meta_review \
  --json '{"reviews": [{"Overall": 7, "Decision": "Accept"}, {"Overall": 5, "Decision": "Reject"}]}'
```
```python
sub.run("meta_review", {"reviews": [review_a_dump, review_b_dump]})
```

---

### 5. `cite`

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
clio-parser cite \
  --candidates-json '[{"title": "Attention Is All You Need", "year": 2017}]'
```
```python
from clio_parser.retrieval.scholar import FakeScholarClient

agent = ClioParserAgent(scholar_client=FakeScholarClient(...))
agent.cite([{"title": "Attention Is All You Need", "year": 2017}], out_dir="/tmp/suggestions")
```

---

### 6. `write`

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
clio-parser write --outline "Methods" \
  --source-file clio-out/2601.23265/paper.md --format prose
```
```python
sub.run("write", {"outline": {"title": "Methods", "goal": "Describe the pipeline."}, "source": "..."})
agent.write(outline={"title": "Methods"}, source="...")
```

---

### 7. `edit`

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

### 8. `polish`

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
clio-parser polish --text-file clio-out/mypaper/sections/01-introduction.md \
  --voice concise --format prose
```
```python
sub.run("polish", {"text": "...", "voice": "concise"})
sub.run("polish", {"text": "...", "target": "sections/01-introduction.md"})
```

---

### 9. `coherence`

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
clio-parser coherence --markdown-file clio-out/mypaper/paper.md --format prose
```
```python
sub.run("coherence", {"markdown": manuscript_text})
sub.run("coherence", {"sections": [{"title": "Introduction", "draft": "..."}, ...]})
```

---

### 10. `literature_graph`

Build a browsable literature graph around one or more seed papers.

- **Reads:** `seed` *(single string)* or `seeds` *(list of strings or `{title, paper_id, year, url}`
  objects)*; `max_nodes` *(optional, default 40)*; `per_seed` *(optional, default 8)*;
  `backend` *(optional: `auto`, `semantic`/`s2`, `openalex`, `off`)*; `out_dir` *(optional)*.
- **Returns:** `content` = graph summary; `structured` = `{backend, seeds, nodes, edges,
  prior_works, derivative_works, related_works}`. Nodes include paper title, authors, year,
  citation count, source link, role, and `ingest_source`. Edges include citation/recommendation
  semantics.
- **Writes:** with `out_dir`, writes `graph.json` and a self-contained `graph.html`. The HTML uses
  color for publication year, node size for citation count, thick outlines for seed papers, and a
  details panel with the paper link plus a copyable `clio-parser ingest ...` command.
- **Backends:** resolved from `CLIO_GRAPH` or the payload's `backend`; see
  [Literature graph backends](#literature-graph-backends-clio_graph).
- **Extra:** `scholar` is needed for Semantic Scholar. `openalex` works without a key/dependency.

```bash
clio-parser graph \
  --seed "Attention Is All You Need" \
  --max-nodes 40 \
  --out-dir clio-out/graphs/attention
```
```python
sub.run("literature_graph", {
    "seed": "Attention Is All You Need",
    "max_nodes": 40,
    "out_dir": "clio-out/graphs/attention",
})
```

---

### 11. `describe_figures`

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
clio-parser describe --blocks-file clio-out/2601.23265/blocks.json --format prose
```
```python
sub.run("describe_figures", {"figures": [{"figure_id": 1, "caption": "..."}]})
agent.describe_figures(blocks_dump)
```

---

### 12. `plot`

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
clio-parser run plot \
  --json '{"spec": {"kind": "plot", "intent": "bar chart of accuracy by model"}}'
```
```python
sub.run("plot", {"spec": {"kind": "plot", "intent": "bar chart of accuracy by model"}})
agent.plot({"kind": "plot", "intent": "bar chart of accuracy by model"})
```

---

### 13. `compose`

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
  - `out_dir` *(optional)* — when set, persists `paper.md` + `sections/NN-slug.md`.
  - `latex` *(optional, bool)* — also emit `paper.tex` + `references.bib` alongside the Markdown.
- **Returns:** `content` = the assembled Markdown manuscript; `structured` = `{outline, sections,
  citations}`; `metadata` = `{num_sections, reviewed, wrote, section_errors, latex}`.
  `wrote` lists every file written to disk.
- **Extra:** none; needs a real `LLMClient` for useful drafts. Citation verification needs a
  scholar backend.
- **File inputs:** `--idea-file idea.txt`, `--log-file log.txt`, `--outline-file outline.json`,
  `--candidates-file refs.json`.

```bash
# Minimal: idea only (offline echo produces placeholder sections)
clio-parser compose --idea "A new attention mechanism for long-range dependencies."

# Full: real model + review loop + LaTeX output
CLIO_LLM=claude uv run clio-parser compose \
  --idea "A new attention mechanism for long-range dependencies." \
  --log "WikiText-103 experiments: BLEU +2.1 over baseline." \
  --candidates-file refs.json \
  --review --max-rounds 2 \
  --out-dir clio-out/mypaper \
  --latex

# Outputs:
#   clio-out/mypaper/paper.md
#   clio-out/mypaper/paper.tex
#   clio-out/mypaper/references.bib
#   clio-out/mypaper/sections/01-introduction.md
#   clio-out/mypaper/sections/02-methods.md  (… etc.)
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
})
print("sections:", result["metadata"]["num_sections"])
print("wrote:", result["metadata"]["wrote"])
print("section errors:", result["metadata"]["section_errors"])
```

---

### 14. `export`

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
- **Returns:** `content` = the full LaTeX source string; `structured` = `{latex, bibtex}`;
  `metadata` = `{wrote, format: "latex", num_sections}`.
- **Extra:** none; pure stdlib conversion.
- **File inputs:** `--markdown-file clio-out/mypaper/paper.md`, `--bibtex-file refs.bib`,
  `--sections-file sections.json`.

```bash
# From a composed paper.md:
clio-parser export \
  --markdown-file clio-out/mypaper/paper.md \
  --bibtex-file clio-out/mypaper/references.bib \
  --out-dir clio-out/mypaper

# From compose's structured sections list:
clio-parser export \
  --sections-file /tmp/sections.json \
  --title "My Paper Title" \
  --out-dir clio-out/mypaper
```
```python
result = sub.run("export", {
    "markdown": manuscript_text,
    "bibtex": bibtex_string,
    "out_dir": "clio-out/mypaper",
})
print(result["content"])    # the .tex source
print(result["metadata"]["wrote"])
```

---

### 15. `write_review`

Run a writer ↔ reviewer **critic-refine** loop and return the final output.

- **Reads:** all `write` keys (`outline`/`section_plan`, `blocks`/`source`, `vision`) plus
  `max_rounds` *(optional, default 3)*. The writer drafts, a reviewer-as-critic reviews the draft,
  and the writer revises; the loop stops on an `Accept` (a "No changes needed." sentinel) or an
  error-flagged output.
- **Returns:** the final writer/critic `AgentOutput` of the loop (writer-shaped on the last draft).
- **Extra:** none; a real `LLMClient` drives both producer and critic. Reachable via
  `clio-parser run write_review`.

```bash
clio-parser run write_review \
  --json '{"outline": {"title": "Methods"}, "source": "...", "max_rounds": 2}'
```
```python
sub.run("write_review", {"outline": {"title": "Methods"}, "source": "...", "max_rounds": 2})
```

---

### 16. `figure_refine`

Run a figure visualizer ↔ critic **critic-refine** loop and return the final output.

- **Reads:** `spec` (forced into `plot` mode), `out_path` *(optional)*, `max_rounds` *(optional,
  default 3)*.
- **Returns:** the final figure `AgentOutput` of the loop (plot-shaped, code in `content`).
- **Extra:** none for the loop itself (code only); `viz` only for the separate gated render.
  Reachable via `clio-parser run figure_refine`.

```bash
clio-parser run figure_refine \
  --json '{"spec": {"kind": "plot", "intent": "line chart of loss"}, "max_rounds": 2}'
```
```python
sub.run("figure_refine", {"spec": {"kind": "plot", "intent": "line chart of loss"}, "max_rounds": 2})
```

---

## How the optional extras gate the heavy paths

The core install (`uv sync`) is hermetic — every action runs offline. Heavy dependencies are
lazy-imported only when their action needs them:

| Extra | Gated path | Default behavior without the extra |
|-------|-----------|-----------------------------------|
| `pdf` | `ingest`: Docling extraction + PyMuPDF OCR fallback | `ingest` returns `metadata["error"]` for the missing dependency |
| `rag` | `ask`: `SentenceTransformerEmbedder` + `LanceDbRetriever` | deterministic `HashingEmbedder` + in-memory `RagRetriever` |
| `scholar` | `cite` + `literature_graph`: Semantic Scholar `httpx` client + `thefuzz` fuzzy match | citation no-key fallbacks and graph OpenAlex fallback still work |
| `viz` | gated `render_plot_code` (subprocess render) | `plot` emits code text only; never renders |

Install a subset as needed, e.g. `uv sync --extra pdf --extra scholar`.

---

## Plugging in a real LLM client

Experts default to `EchoLLMClient` (deterministic, offline) so the harness and tests stay hermetic.
That echo path is fine for `ingest` (deterministic), `meta_review` (arithmetic), `cite`
(verification), and the code-extraction parts of `plot` / `describe_figures`, but `ask` / `review`
/ `write` / `edit` / `polish` / `coherence` / `compose` need a **real** provider to produce useful
output.

**Ready-made providers** ship in `clio_parser.llm.providers` (stdlib-only, lazy):
`ClaudeCliLLMClient` (the `claude` CLI — session-based, no API key), `CodexCliLLMClient`
(`codex exec`), and `OllamaLLMClient` (a local Ollama server). The **CLI** selects one via the
`CLIO_LLM` env var (`echo` (default) | `claude` | `codex` | `ollama`; model via `CLIO_LLM_MODEL`,
Ollama URL via `CLIO_OLLAMA_URL`).

```bash
CLIO_LLM=claude  clio-parser review --paper-file clio-out/2601.23265/paper.md
CLIO_LLM=codex   clio-parser write --outline "Introduction" --source-file clio-out/2601.23265/paper.md
CLIO_LLM=ollama  CLIO_LLM_MODEL=qwen2.5:14b clio-parser ask \
  --question "..." --blocks-file clio-out/2601.23265/blocks.json
```

For secrets, the CLI automatically loads `.env.local` from the current working directory, without
overriding real environment variables. Set `CLIO_ENV_FILE=/path/to/file` to use a different local
env file. See [`SECURITY.md`](SECURITY.md) for key rotation and handling rules.

In-process, pass a provider directly: `ClioParserAgent(llm=ClaudeCliLLMClient())` or
`ClioParserSubagent(llm=resolve_llm("claude"))`. To write your own provider, implement:

```python
def complete(self, messages: list[Message], **kwargs: object) -> str: ...
```

`Message` (from `clio_parser.harness.types`) has `role` (`"system" | "user" | "assistant" |
"expert"`), `content: str`, and optional `name` / `metadata`. A minimal real client:

```python
from clio_parser.harness.types import Message

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
from clio_parser import ClioParserAgent

agent = ClioParserAgent(llm=MyLLMClient(model="..."))
agent.review("# Title\n...")
```

Both `ClioParserAgent` and `ClioParserSubagent` also accept `files=SafeFiles(root)` (for the
write-capable experts) and `scholar_client=...` (for `cite`).

---

## Literature graph backends (`CLIO_GRAPH`)

`CLIO_GRAPH` selects the backend for `literature_graph` / `clio-parser graph`:

| Value | Client | Notes |
|-------|--------|-------|
| `auto` / `cascade` *(default)* | `CascadeLiteratureGraphClient` | Semantic Scholar first, then OpenAlex fallback |
| `semantic` / `s2` | `SemanticScholarGraphClient` | Uses title match, references, citations, and recommendations; reads `SEMANTIC_SCHOLAR_API_KEY` |
| `openalex` / `oa` | `OpenAlexGraphClient` | No key required; related-work fallback |
| `off` / `none` / `offline` | `None` | Graph expert reports "no literature graph client configured" |

The Semantic Scholar graph path is rate-limit aware and spaces requests more conservatively than
single citation checks because one graph run needs several API calls. The graph action writes
portable artifacts:

```bash
uv run --extra scholar clio-parser graph \
  --seed "Attention Is All You Need" \
  --out-dir clio-out/graphs/attention
```

Open `clio-out/graphs/attention/graph.html` directly in a browser. No dev server is required.

In-process, pass a `LiteratureGraphClient` protocol-compatible object directly:
`ClioParserAgent(graph_client=MyGraphClient())`.

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
`ClioParserAgent(scholar_client=MyScholarClient())`.

---

## Gemini vision (`CLIO_VISION=gemini`)

`CLIO_VISION` selects the optional image-understanding path for the figure agent (resolved via
`resolve_vision_client()`):

| Value | Client | Notes |
|-------|--------|-------|
| `off` / `none` *(default)* | `None` | Figure agent stays on the hermetic text/code path; no image API is called |
| `gemini` / `google` | `GeminiVisionClient` | Reads `GEMINI_API_KEY` or `GOOGLE_API_KEY`; uses stdlib `urllib` REST |

When `CLIO_VISION=gemini` is active:

- `describe_figures` *looks at* the real image file for each figure (from `figure.image_path`) and
  returns a Gemini-generated caption. `metadata["vision_described"]` counts the figures described
  this way; `metadata["text_described"]` counts the fallback path.
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
CLIO_VISION=gemini GEMINI_API_KEY=... clio-parser describe \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```

In-process:

```python
from clio_parser.llm.vision import GeminiVisionClient
from clio_parser import ClioParserAgent

vision = GeminiVisionClient(api_key="...", describe_model="gemini-2.5-flash")
agent = ClioParserAgent(vision=vision)
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

# clio-parser usage

clio-parser is a standalone multi-agent harness a host invokes either **in-process** (import) or as
a **subprocess** (the `clio-parser` CLI). This document is the full action reference plus the
configuration seams (optional extras and the `LLMClient`).

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
> (`uv run --extra pdf clio-parser ingest …`, `uv run --extra rag clio-parser ask …`); add
> `--no-sync` if you installed extras via `uv pip install`. The bare `clio-parser …` form shown
> below assumes an activated venv.

> **Output format (`structured` vs `prose`).** Every action defaults to `structured` — JSON for a
> host agent to branch on. Pass `--format prose` (CLI flag on dedicated text subcommands) or
> `{"format": "prose"}` in any payload to get a human-readable text answer instead: `structured`
> becomes `null` and the prose lands in `content`. `review` has the model *write* the prose;
> the data-shaped actions (`cite`, `meta_review`, `describe_figures`) render their result as text.

---

## Action catalog (11 actions)

Payload keys below are exactly the keys each expert reads. Keys marked *(optional)* have a fallback.

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
sub.run("ingest", {"source": "2601.23265", "out_dir": "/tmp/my-paper"})
agent.ingest("path/to/paper.pdf")
```

### 2. `ask`

Answer a question grounded only in the provided memory blocks (selective context injection).

- **Reads:** `question` *(optional — falls back to the task description)*; `blocks` (a `MemoryBlocks`
  or its `model_dump()` dict).
- **Returns:** `content` = the answer; `structured` = `{cited_block_ids, retrieved}`; `metadata` =
  `{k, num_blocks}`.
- **Extra:** `rag` swaps the default deterministic `HashingEmbedder` + in-memory `RagRetriever` for a
  `SentenceTransformer` embedder + LanceDB. A real `LLMClient` is needed for useful answers.

```bash
clio-parser ask --question "What is the main result?" --blocks-json '{"sections": [...]}'
```
```python
sub.run("ask", {"question": "What is the main result?", "blocks": blocks_dump})
agent.ask("What is the main result?", blocks_dump)
```

### 3. `review`

Produce a structured, persona-conditioned peer review.

- **Reads:** `paper` *(optional — falls back to `markdown`, then `blocks`, then the task
  description)*; `persona` *(optional `PersonaSpec`)*. A `MemoryBlocks` paper is rendered to text.
- **Returns:** `content` = one-line summary (decision + overall); `structured` = a `PaperReview`
  dump (summary, strengths, weaknesses, questions, limitations, the 1–4 axes, overall 1–10,
  confidence, decision); `metadata` = `{persona, decision, overall}`. If the LLM response has no
  parseable JSON, `structured` is `null` and `metadata["parse_error"]` is set (the default echo
  client naturally hits this path).
- **Extra:** none; needs a real `LLMClient` to produce a parseable review.

```bash
clio-parser review --paper "# Title\n\nAbstract..."
```
```python
sub.run("review", {"paper": "# Title\n\nAbstract..."})
agent.review("# Title\n\nAbstract...")
```

### 4. `meta_review`

Aggregate several reviews into a single area-chair meta-review (deterministic, hermetic).

- **Reads:** `reviews` *(optional — a list of `PaperReview`/dicts; when absent, recovers reviewer
  outputs from the session history)*.
- **Returns:** `content` = meta-decision summary; `structured` = a `MetaReview` dump (per-axis
  rounded means, merged text fields, OR-ed ethical concerns, decision, `reviewer_count`); `metadata`
  = `{decision, overall, reviewer_count}`.
- **Extra:** none. Aggregation is offline arithmetic. Reachable via `clio-parser run meta_review`.

```bash
clio-parser run meta_review --json '{"reviews": [{"Overall": 7, "Decision": "Accept"}, {"Overall": 5, "Decision": "Reject"}]}'
```
```python
sub.run("meta_review", {"reviews": [review_a_dump, review_b_dump]})
```

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
- **Backends:** the CLI resolves `CLIO_SCHOLAR`: `auto`/`cascade` (default) tries Semantic Scholar,
  OpenAlex, Crossref, then arXiv; `semantic`/`s2`, `openalex`, `crossref`, and `arxiv` force one
  backend; `off`/`none`/`offline` disables lookup. OpenAlex/Crossref/arXiv use stdlib HTTP and need no key.
- **Extra:** the verification logic is pure stdlib (difflib fallback). The `scholar` extra only adds
  Semantic Scholar's `httpx` path and `thefuzz`; no-key fallbacks work from the core install.

```bash
clio-parser cite --candidates-json '[{"title": "Attention Is All You Need", "year": 2017}]'
```
```python
from clio_parser import ClioParserAgent
from clio_parser.retrieval.scholar import FakeScholarClient   # hermetic; real: OpenAlexClient etc.

agent = ClioParserAgent(scholar_client=FakeScholarClient(...))
agent.cite([{"title": "Attention Is All You Need", "year": 2017}], out_dir="/tmp/suggestions")
```

### 6. `write`

Draft a single paper section grounded in scoped source material.

- **Reads:** `outline` or `section_plan` (a `SectionOutline`/`SectionPlan` or loose dict — title,
  `section_path`, `goal`, `word_budget`, `citation_hints`, `figure_refs`); section source from
  `blocks` (a `MemoryBlocks`, scoped to the section) or `source`/`materials` *(optional — falls back
  to the task description)*; `vision` *(optional)*; `out_path` *(optional)* — writes the draft under
  the `SafeFiles` root when `files` is configured.
- **Returns:** `content` = the draft prose; `structured` = `{section_path, draft, out_path,
  word_count}`; `metadata` = `{phase, wrote, summary}`.
- **Extra:** none; needs a real `LLMClient` for useful prose. File writes require a `SafeFiles`.

```bash
clio-parser write --outline "Methods" --source "..."
```
```python
sub.run("write", {"outline": {"title": "Methods", "goal": "Describe the pipeline."}, "source": "..."})
agent.write(outline={"title": "Methods"}, source="...")
```

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

### 8. `describe_figures`

Fill in descriptions/captions for figures (for context injection).

- **Reads:** `blocks` (a `MemoryBlocks` whose `figures` get described) **or** `figures` (a list of
  `FigureInfo`/dicts); `context` *(optional surrounding text)*. Caller objects are deep-copied, so
  describing never mutates the input.
- **Returns:** `content` = a "described N of M" summary; `structured` = `{descriptions[],
  blocks?}` (each description = `{figure_id, description, caption}`; the updated `blocks` dump is
  included when blocks were supplied); `metadata` = `{mode: "describe", num_described}`.
- **Extra:** none; needs a real `LLMClient`. (LLM vision captions are future work.)

```bash
clio-parser describe --blocks-json '{"figures": [{"figure_id": 1, "caption": "..."}]}'
```
```python
sub.run("describe_figures", {"figures": [{"figure_id": 1, "caption": "..."}]})
agent.describe_figures(blocks_dump)
```

### 9. `plot`

Generate matplotlib plot **code** (text only; never executed on this path).

- **Reads:** `spec` (a `PlotSpec` or loose dict — `kind` (`plot`/`diagram`), `intent`, `data_hint`,
  `aspect_ratio`); `out_path` *(optional)* — when set with a `SafeFiles`, writes the code there.
- **Returns:** `content` = the extracted Python code; `structured` = `{artifact, out_path}` (artifact
  = `{kind: "plot", code}`); `metadata` = `{mode: "plot", phase, wrote}`.
- **Extra:** `viz` (matplotlib) is only needed for the **gated** `render_plot_code` helper, which
  runs the code in a subprocess (`Agg` backend, timeout). Nothing in the default action renders.

```bash
clio-parser run plot --json '{"spec": {"kind": "plot", "intent": "bar chart of accuracy by model"}}'
```
```python
sub.run("plot", {"spec": {"kind": "plot", "intent": "bar chart of accuracy by model"}})
agent.plot({"kind": "plot", "intent": "bar chart of accuracy by model"})
```

### 10. `write_review`

Run a writer ↔ reviewer **critic-refine** loop and return the final output.

- **Reads:** all `write` keys (`outline`/`section_plan`, `blocks`/`source`, `vision`) plus
  `max_rounds` *(optional, default 3)*. The writer drafts, a reviewer-as-critic reviews the draft,
  and the writer revises; the loop stops on an `Accept` (a "No changes needed." sentinel) or an
  error-flagged output.
- **Returns:** the final writer/critic `AgentOutput` of the loop (writer-shaped on the last draft).
- **Extra:** none; a real `LLMClient` drives both producer and critic. Reachable via
  `clio-parser run write_review`.

```python
sub.run("write_review", {"outline": {"title": "Methods"}, "source": "...", "max_rounds": 2})
```

### 11. `figure_refine`

Run a figure visualizer ↔ critic **critic-refine** loop and return the final output.

- **Reads:** `spec` (forced into `plot` mode), `out_path` *(optional)*, `max_rounds` *(optional,
  default 3)*.
- **Returns:** the final figure `AgentOutput` of the loop (plot-shaped, code in `content`).
- **Extra:** none for the loop itself (code only); `viz` only for the separate gated render.
  Reachable via `clio-parser run figure_refine`.

```python
sub.run("figure_refine", {"spec": {"kind": "plot", "intent": "line chart of loss"}, "max_rounds": 2})
```

---

## How the optional extras gate the heavy paths

The core install (`uv sync`) is hermetic — every action runs offline. Heavy dependencies are
lazy-imported only when their action needs them, so they are absent from the default env:

| Extra | Gated path | Default behavior without the extra |
|-------|-----------|-----------------------------------|
| `pdf` | `ingest`: Docling extraction + PyMuPDF OCR fallback | `ingest` returns `metadata["error"]` for the missing dependency |
| `rag` | `ask`: `SentenceTransformerEmbedder` + `LanceDbRetriever` | deterministic `HashingEmbedder` + in-memory `RagRetriever` |
| `scholar` | `cite`: Semantic Scholar `httpx` client + `thefuzz` fuzzy match | no-key OpenAlex/Crossref/arXiv clients and difflib fuzzy match still work |
| `viz` | gated `render_plot_code` (subprocess render) | `plot` emits code text only; never renders |

Install a subset as needed, e.g. `uv sync --extra pdf --extra scholar`.

---

## Plugging in a real LLM client

Experts default to `EchoLLMClient` (deterministic, offline) so the harness and tests stay hermetic.
That echo path is fine for `ingest` (deterministic), `meta_review` (arithmetic), `cite`
(verification), and the code-extraction parts of `plot`/`describe_figures`, but `ask` / `review` /
`write` / `edit` need a **real** provider to produce useful output.

**Ready-made providers** ship in `clio_parser.llm.providers` (stdlib-only, lazy):
`ClaudeCliLLMClient` (the `claude` CLI — session-based, no API key), `CodexCliLLMClient`
(`codex exec`), and `OllamaLLMClient` (a local Ollama server). The **CLI** selects one via the
`CLIO_LLM` env var (`echo` (default) | `claude` | `codex` | `ollama`; model via `CLIO_LLM_MODEL`,
Ollama URL via `CLIO_OLLAMA_URL`). Citation lookup is selected with `CLIO_SCHOLAR` (`auto`
default | `semantic` | `openalex` | `crossref` | `arxiv` | `off`). Set
`SEMANTIC_SCHOLAR_API_KEY` to authenticate with the S2 API and reduce HTTP 429 rate-limit errors;
set `OPENALEX_MAILTO` / `CROSSREF_MAILTO` for polite no-key fallback usage:

```bash
CLIO_LLM=claude  clio-parser review --paper "# Paper ..."
CLIO_LLM=codex   clio-parser run write --json '{"outline": {"title": "Introduction"}, "source": "..."}'
CLIO_LLM=ollama  CLIO_LLM_MODEL=qwen2.5:14b clio-parser ask --question "..." --blocks-file clio-out/2601.23265/blocks.json
```

For secrets, the CLI automatically loads `.env.local` from the current working directory, without
overriding real environment variables. Set `CLIO_ENV_FILE=/path/to/file` to use a different local
env file. These files are ignored by the repo.

In-process, pass a provider directly: `ClioParserAgent(llm=ClaudeCliLLMClient())` or
`ClioParserSubagent(llm=resolve_llm("claude"))`. To write your own provider, implement the contract:

The contract is a single synchronous method (`clio_parser.llm.client.LLMClient`, a runtime-checkable
`Protocol`):

```python
def complete(self, messages: list[Message], **kwargs: object) -> str: ...
```

`Message` (from `clio_parser.harness.types`) has `role` (`"system" | "user" | "assistant" |
"expert"`), `content: str`, and optional `name` / `metadata`. A minimal real client:

```python
from clio_parser.harness.types import Message

class MyLLMClient:
    """Anthropic example; any provider works — only `complete` is required."""

    def __init__(self, model: str) -> None:
        import anthropic
        self._client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
        self._model = model

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        system = "\n".join(m.content for m in messages if m.role == "system")
        turns = [
            {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in messages
            if m.role != "system"
        ]
        resp = self._client.messages.create(
            model=self._model,
            system=system or None,
            messages=turns,
            max_tokens=4096,
        )
        return "".join(block.text for block in resp.content if block.type == "text")
```

Inject it at construction; all experts share the one client:

```python
from clio_parser import ClioParserAgent, ClioParserSubagent

llm = MyLLMClient(model="...")
agent = ClioParserAgent(llm)                       # or
sub = ClioParserSubagent(llm)
sub.run("review", {"paper": "# Title\n..."})       # now returns a parseable structured review
```

Both `ClioParserAgent` and `ClioParserSubagent` also accept `files=SafeFiles(root)` (for the
write-capable experts) and `scholar_client=...` (for `cite`).

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

`live` tests require network and/or real backends (RAG embeddings, Semantic Scholar, plot
rendering); `baseline` tests compare against reference implementations or run real PDFs through the
ingest pipeline. Neither runs in CI's default hermetic pass.

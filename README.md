# clio-parser

clio-parser turns a scientific paper — an **arXiv link, a PDF, or even just its title** — into clean
Markdown, then lets specialized AI agents **answer questions about it, check its citations, review
it, and help write, compose, export, and edit it**. It runs on its own, and a larger agent (such as
CLIO) can call it as a **subagent**.

> Runs **offline out of the box** with a built-in echo model (good for trying the plumbing). Add a
> real model (Claude / Codex / Ollama) for real answers. Requires **Python ≥ 3.12**. BSD-3-Clause.

---

## 1. Quickstart — copy & paste, top to bottom

**Step 1. Install `uv`** (the only prerequisite — a fast Python runner). Skip if you have it.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Step 2. Get the code and install the core package.**

```bash
git clone https://github.com/SIslamMun/clio-Parser.git
cd clio-Parser
uv sync
```

**Step 3. Confirm it works** (prints the list of 16 things it can do — no model or network needed):

```bash
uv run clio-parser capabilities
```

**Step 4. Turn a real paper into Markdown.** The `--extra pdf` flag adds the PDF/arXiv extractor for
this run. (The first ingest also downloads ~500 MB of extraction models; later runs are fast.)

```bash
uv run --extra pdf clio-parser ingest 2601.23265
```

This creates a folder you can open and read:

```
clio-out/2601.23265/
├── paper.md          # the clean scientific Markdown
├── blocks.json       # structured sections / figures / equations
├── img/              # extracted figure images (figure1.png, …)
└── 2601.23265.pdf    # the downloaded source PDF
```

You can ingest other ways too:

```bash
uv run --extra pdf clio-parser ingest "Attention Is All You Need"   # by paper title
uv run --extra pdf clio-parser ingest ./mypaper.pdf                 # a local PDF file
```

**Step 5. Look at what you got.**

```bash
head -40 clio-out/2601.23265/paper.md
ls clio-out/2601.23265/img/
```

**Step 6. Get a real AI review** (this needs a real model — see [§3](#3-use-a-real-model); the
example uses the Claude CLI):

```bash
CLIO_LLM=claude uv run clio-parser review \
  --paper-file clio-out/2601.23265/paper.md --format prose
```

That is the whole loop: **ingest → read → review.** Everything below is variations on this.

---

## 2. Every command, with a real example

Run any of these after Step 4 above. Add `--format prose` for human-readable text; omit it to get
JSON (the default, handy for programs). Anything that produces text needs a real model
(`CLIO_LLM=…`, see §3); `ingest`, `cite`, and `meta_review` work without one.

### Processing

```bash
# Convert a paper to Markdown + memory blocks (arXiv id | URL | title | topic | local PDF):
uv run --extra pdf clio-parser ingest 2601.23265
```

### Question answering

```bash
# Ask a question, grounded in that paper's blocks:
CLIO_LLM=claude uv run clio-parser ask \
  --question "What problem does this paper solve?" \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```

### Citation verification

```bash
# Verify citations against Semantic Scholar + fallback backends (suggestions only):
uv run --extra scholar clio-parser cite \
  --candidates-json '[{"title": "Attention Is All You Need", "year": 2017}]'
```

### Literature graph visualization

```bash
# Build a Connected-Papers-style HTML graph: node color = year, size = citations.
uv run --extra scholar clio-parser graph \
  --seed "Attention Is All You Need" \
  --max-nodes 40 \
  --out-dir clio-out/graphs/attention

# Open clio-out/graphs/attention/graph.html in a browser.
# Click a node to see paper links and an ingest command for that paper.
```

### Review

```bash
# Peer-review a paper (structured JSON, or --format prose):
CLIO_LLM=claude uv run clio-parser review \
  --paper-file clio-out/2601.23265/paper.md --format prose

# Aggregate several reviews into a single meta-review (no model needed):
uv run clio-parser run meta_review \
  --json '{"reviews": [{"Overall": 7, "Decision": "Accept"}, {"Overall": 5, "Decision": "Reject"}]}'
```

### Writing, composing, and exporting

```bash
# Draft one section from an outline + source material:
CLIO_LLM=claude uv run clio-parser write \
  --outline "Introduction" --source-file clio-out/2601.23265/paper.md --format prose

# Polish a draft for clarity, flow, and academic voice:
CLIO_LLM=claude uv run clio-parser polish \
  --text-file clio-out/2601.23265/paper.md --voice concise --format prose

# Check cross-section consistency of a manuscript:
CLIO_LLM=claude uv run clio-parser coherence \
  --markdown-file clio-out/2601.23265/paper.md --format prose

# Draft a WHOLE paper from an idea (outline → cite → write per section → assemble):
CLIO_LLM=claude uv run clio-parser compose \
  --idea "Propose a new attention mechanism for long-range dependencies." \
  --log "Ran experiments on WikiText-103; BLEU +2.1 over baseline." \
  --review --out-dir clio-out/mypaper --format prose

# Same, but also emit paper.tex + references.bib:
CLIO_LLM=claude uv run clio-parser compose \
  --idea-file idea.txt --log-file log.txt \
  --candidates-file refs.json \
  --review --out-dir clio-out/mypaper --latex

# Export an existing paper.md to LaTeX directly:
uv run clio-parser export \
  --markdown-file clio-out/mypaper/paper.md \
  --bibtex-file clio-out/mypaper/references.bib \
  --out-dir clio-out/mypaper
```

After `compose`, the output directory contains:

```
clio-out/mypaper/
├── paper.md               # assembled Markdown manuscript
├── paper.tex              # (with --latex) standalone LaTeX document
├── references.bib         # (with --latex and citations) BibTeX entries
└── sections/
    ├── 01-introduction.md
    ├── 02-methods.md
    └── …
```

### Figures

```bash
# Generate matplotlib plot code (code text only; never executed by default):
CLIO_LLM=claude uv run clio-parser run plot \
  --json '{"spec": {"kind": "plot", "intent": "training loss vs epoch"}}'

# Describe figures in a paper's memory blocks:
CLIO_LLM=claude uv run clio-parser describe \
  --blocks-file clio-out/2601.23265/blocks.json --format prose
```

### Generic escape hatch

```bash
# Any action by name (edit, write_review, figure_refine, …):
uv run clio-parser run write_review \
  --json '{"outline": {"title": "Methods"}, "source": "...", "max_rounds": 2}'
```

The complete payload reference for every action is in [`docs/USAGE.md`](docs/USAGE.md).

---

## 3. Use a real model

By default clio-parser uses an **offline echo model**, so `review`/`ask`/`write`/`compose` return a
placeholder instead of real text. Pick a real one with the `CLIO_LLM` environment variable:

| `CLIO_LLM` | What it uses | How to get it |
|---|---|---|
| `echo` *(default)* | nothing — offline placeholder | already works |
| `claude` | the `claude` CLI (no API key) | install Claude Code so `claude` is on your PATH |
| `codex` | the `codex` CLI | install the Codex CLI |
| `ollama` | a local model server | install [Ollama](https://ollama.com), then `ollama pull llama3.1:8b` |

```bash
CLIO_LLM=claude uv run clio-parser review --paper-file clio-out/2601.23265/paper.md --format prose
CLIO_LLM=ollama CLIO_LLM_MODEL=llama3.1:8b uv run clio-parser ask \
  --question "..." --blocks-file clio-out/2601.23265/blocks.json
```

Other useful variables:

| Variable | Purpose | Default |
|---|---|---|
| `CLIO_LLM_MODEL` | Override the model name for the selected provider | provider default |
| `CLIO_OLLAMA_URL` | Ollama server address | `http://localhost:11434` |
| `CLIO_VISION` | Gemini vision for `describe_figures` / diagram generation | `off` |
| `CLIO_VISION_MODEL` | Gemini describe model | `gemini-2.5-flash` |
| `CLIO_IMAGE_MODEL` | Gemini image generation model | `gemini-2.5-flash-image` |

### Literature graph backends (`CLIO_GRAPH`)

| `CLIO_GRAPH` | What it uses |
|---|---|
| `auto` *(default)* | Semantic Scholar first, then OpenAlex fallback |
| `semantic` / `s2` | Semantic Scholar only; uses `SEMANTIC_SCHOLAR_API_KEY` when present |
| `openalex` | OpenAlex only; no key required |
| `off` / `none` / `offline` | disable graph lookup |

`clio-parser graph` writes `graph.json` and a self-contained `graph.html` when `--out-dir` is set.
The HTML graph shows publication year by color, citation count by node size, prior/derivative roles,
paper links, and a copyable `clio-parser ingest ...` command for each node.

### Citation backends (`CLIO_SCHOLAR`)

| `CLIO_SCHOLAR` | What it uses |
|---|---|
| `auto` *(default)* | cascade: Semantic Scholar → OpenAlex → Crossref → arXiv |
| `semantic` / `s2` | Semantic Scholar only; set `SEMANTIC_SCHOLAR_API_KEY` to avoid rate limits |
| `openalex` | OpenAlex only; no key required |
| `crossref` | Crossref only; no key required |
| `arxiv` | arXiv only; no key required, preprint-focused |
| `off` / `none` / `offline` | disable citation lookup |

For polite no-key usage, set `OPENALEX_MAILTO` and/or `CROSSREF_MAILTO` to an email address.

### Gemini vision (`CLIO_VISION=gemini`)

When `CLIO_VISION=gemini` is set and a `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is in the
environment, `describe_figures` *looks at* real figure images using the Gemini REST API, and `plot`
with `spec.kind="diagram"` generates a real image PNG instead of matplotlib code. Without this,
both actions use the hermetic text/code path and no image API is ever called.

```bash
CLIO_VISION=gemini GEMINI_API_KEY=... uv run clio-parser describe \
  --blocks-file clio-out/2601.23265/blocks.json
```

### Keeping secrets local

Keep secrets in a local ignored env file instead of pasting them into commands:

```bash
cp .env.local.example .env.local
chmod 600 .env.local
```

Then edit `.env.local` with your keys. `uv run clio-parser ...` loads it automatically. Use
`CLIO_ENV_FILE=/path/to/file` if you want a different file. Never paste API keys into chat, issues,
PRs, or commands; rotate any key that was exposed. See [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 4. Use it as a subagent (from another program)

clio-parser is meant to be **called by a host agent**. Two ways:

### A. In-process (Python) — recommended

Save this as `use_clio.py` and run it with `uv run python use_clio.py`:

```python
from clio_parser.integration.clio_adapter import ClioParserSubagent
from clio_parser.llm.providers import resolve_llm

# Build the subagent. resolve_llm("claude") | "codex" | "ollama" | None (offline echo).
sub = ClioParserSubagent(llm=resolve_llm("claude"))

# 1) Discover what it can do (16 actions).
for a in sub.capabilities()["actions"]:
    print(a["action"], "—", a["description"])

# 2) Ingest a paper (needs the `pdf` extra: uv sync --extra pdf).
ingested = sub.run("ingest", {"source": "2601.23265", "out_dir": "clio-out/demo"})
blocks = ingested["structured"]              # the memory blocks
print("wrote:", ingested["metadata"]["wrote"])

# 3) Ask a grounded question.
answer = sub.run("ask", {"question": "What is the main contribution?", "blocks": blocks})
print(answer["content"])

# 4) Review the paper.
review = sub.run("review", {"paper": ingested["content"]})
print(review["metadata"].get("decision"), review["structured"])

# 5) Draft a whole paper from an idea.
result = sub.run("compose", {
    "idea": "Propose a new attention mechanism for long-range dependencies.",
    "experimental_log": "Ran experiments on WikiText-103; BLEU +2.1 over baseline.",
    "review": True,
    "out_dir": "clio-out/mypaper",
})
print("sections:", result["metadata"]["num_sections"])
print("wrote:", result["metadata"]["wrote"])
```

Every `sub.run(action, payload)` returns a JSON-serializable dict
`{"action", "content", "structured", "metadata"}` and **never raises** — failures show up in
`result["metadata"]["error"]` (or a top-level `"error"`). The adapter imports nothing from the host,
so the coupling is one-directional.

### B. As a subprocess (any language)

Call the CLI and read JSON from stdout (exit code `0` = ok, `1` = error):

```bash
CLIO_LLM=claude uv run clio-parser review --paper-file clio-out/2601.23265/paper.md
# -> {"action": "review", "content": "...", "structured": {...}, "metadata": {...}}
```

---

## 5. The 16 actions at a glance

| # | Action | What it does | Dedicated subcommand |
|---|--------|-------------|----------------------|
| 1 | `ingest` | arXiv id / URL / PDF / title → Markdown + memory blocks | `clio-parser ingest <source>` |
| 2 | `ask` | Answer a question grounded in memory blocks | `clio-parser ask` |
| 3 | `cite` | Verify citation candidates (suggestions only, never edits) | `clio-parser cite` |
| 4 | `review` | Structured peer review of a paper | `clio-parser review` |
| 5 | `meta_review` | Aggregate several reviews into one area-chair meta-review | `clio-parser run meta_review` |
| 6 | `write` | Draft a single section from an outline + source | `clio-parser write` |
| 7 | `edit` | Revise a draft to address reviewer feedback | `clio-parser run edit` |
| 8 | `polish` | Improve prose clarity, flow, and academic voice | `clio-parser polish` |
| 9 | `coherence` | Check cross-section consistency of a manuscript | `clio-parser coherence` |
| 10 | `literature_graph` | Visual paper graph: seed, prior works, derivative works, links, ingest commands | `clio-parser graph` |
| 11 | `describe_figures` | Fill figure descriptions / captions in memory blocks | `clio-parser describe` |
| 12 | `plot` | Generate matplotlib plot code (code text only) | `clio-parser run plot` |
| 13 | `compose` | Whole-paper orchestration: idea → outline → cite → write → assemble | `clio-parser compose` |
| 14 | `export` | Markdown manuscript → standalone LaTeX (`paper.tex` + `references.bib`) | `clio-parser export` |
| 15 | `write_review` | Writer ↔ reviewer critic-refine loop | `clio-parser run write_review` |
| 16 | `figure_refine` | Figure visualizer ↔ critic refine loop | `clio-parser run figure_refine` |

Actions without a dedicated subcommand are reachable via `clio-parser run <action> --json '...'`.

---

## 6. Optional extras (install only what you need)

The core install is tiny and offline. Each heavy capability is opt-in:

```bash
uv sync --extra pdf        # real PDF/arXiv extraction (Docling + PyMuPDF) — needed for `ingest`
uv sync --extra rag        # real semantic search for `ask` (sentence-transformers + LanceDB)
uv sync --extra scholar    # live Semantic Scholar for `cite` + `graph` (httpx + thefuzz)
uv sync --extra viz        # actually render plot images (matplotlib)
uv sync --all-extras       # everything at once
```

`torch` is pinned to the CPU build, so `uv sync --all-extras` resolves cleanly. (GPU users: see the
`[tool.uv.index]` note in `pyproject.toml`.)

---

## 7. Test it

```bash
uv run pytest                        # the offline test suite (no network, no model downloads)
uv run pytest -m live                # real-backend tests (need the extras + network)
uv run python scripts/real_test.py   # full real end-to-end run; set CLIO_TEST_LLM=claude|codex|ollama
```

---

## 8. Troubleshooting

- **`clio-parser: command not found`** — it lives in the project's venv; always call it as
  `uv run clio-parser …` (or `source .venv/bin/activate` first).
- **`ingest` says a dependency is missing** — run `uv sync --extra pdf`.
- **First `ingest` is slow** — Docling downloads ~500 MB of models once; subsequent runs are fast.
- **`review`/`ask`/`write`/`compose` output looks like a placeholder** — you're on the default echo
  model; set `CLIO_LLM=claude` (or `codex`/`ollama`).
- **`cite` returns nothing** — try `CLIO_SCHOLAR=openalex` or `CLIO_SCHOLAR=arxiv`; for Semantic
  Scholar specifically, set `SEMANTIC_SCHOLAR_API_KEY` to reduce rate limits.
- **`torchvision::nms` error after installing `rag`/`pdf`** — reinstall the matching CPU wheel:
  `uv pip install --reinstall torchvision --index-url https://download.pytorch.org/whl/cpu`.
- **`compose` / `export` produce no `.tex` file** — `--latex` requires `--out-dir` to be set so a
  `SafeFiles` can be rooted there; or use `export --markdown-file` to convert an existing `paper.md`.

---

## More

- **Full action & payload reference, providers, output details** → [`docs/USAGE.md`](docs/USAGE.md)
- **API keys and local env-file handling** → [`docs/SECURITY.md`](docs/SECURITY.md)
- **Design and architecture** → [`artifact/notes/DESIGN.md`](artifact/notes/DESIGN.md)
- **Working in this repo (for agents/contributors)** → [`AGENTS.md`](AGENTS.md)
- **Changes** → [`CHANGELOG.md`](CHANGELOG.md)

## License

BSD-3-Clause. Adapts MIT / Apache-2.0 sources with attribution (see module headers); no AGPL code.

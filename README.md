# clio-parser

clio-parser turns a scientific paper — an **arXiv link, a PDF, or even just its title** — into clean
Markdown, then lets specialized AI agents **answer questions about it, check its citations, review
it, and help write and edit it**. It runs on its own, and a larger agent (such as CLIO) can call it
as a **subagent**.

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

**Step 3. Confirm it works** (prints the list of things it can do — no model or network needed):

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

```bash
# Convert a paper to Markdown + memory blocks (arXiv id | URL | title | topic | local PDF):
uv run --extra pdf clio-parser ingest 2601.23265

# Ask a question, grounded in that paper's blocks:
CLIO_LLM=claude uv run clio-parser ask \
  --question "What problem does this paper solve?" \
  --blocks-file clio-out/2601.23265/blocks.json

# Verify citations against Semantic Scholar (suggestions only — never edits your refs):
uv run --extra scholar clio-parser cite --candidates-json '[{"title": "Attention Is All You Need", "year": 2017}]'

# Peer-review a paper (structured JSON, or prose):
CLIO_LLM=claude uv run clio-parser review --paper-file clio-out/2601.23265/paper.md --format prose

# Draft a section from an outline + source material:
CLIO_LLM=claude uv run clio-parser write \
  --outline "Introduction" --source-file clio-out/2601.23265/paper.md --format prose

# Generate matplotlib code for a figure:
CLIO_LLM=claude uv run clio-parser run plot \
  --json '{"spec": {"kind": "plot", "intent": "training loss vs epoch"}}'

# Any other action by name (meta_review, edit, describe_figures, write_review, figure_refine):
uv run clio-parser run meta_review \
  --json '{"reviews": [{"Overall": 7, "Decision": "Accept"}, {"Overall": 5, "Decision": "Reject"}]}'
```

The complete payload reference for every action is in [`docs/USAGE.md`](docs/USAGE.md).

---

## 3. Use a real model

By default clio-parser uses an **offline echo model**, so `review`/`ask`/`write` return a
placeholder instead of real text. Pick a real one with the `CLIO_LLM` environment variable:

| `CLIO_LLM` | What it uses | How to get it |
|---|---|---|
| `echo` *(default)* | nothing — offline placeholder | already works |
| `claude` | the `claude` CLI (no API key) | install Claude Code so `claude` is on your PATH |
| `codex` | the `codex` CLI | install the Codex CLI |
| `ollama` | a local model server | install [Ollama](https://ollama.com), then `ollama pull llama3.1:8b` |

```bash
CLIO_LLM=claude uv run clio-parser review --paper-file clio-out/2601.23265/paper.md --format prose
CLIO_LLM=ollama CLIO_LLM_MODEL=llama3.1:8b uv run clio-parser ask --question "..." --blocks-file clio-out/2601.23265/blocks.json
```

Other useful variables: `CLIO_LLM_MODEL` (model name), `CLIO_OLLAMA_URL` (default
`http://localhost:11434`), and `SEMANTIC_SCHOLAR_API_KEY` — set this to make `cite` reliable, since
the public Semantic Scholar endpoint rate-limits anonymous requests.

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

# 1) Discover what it can do.
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

## 5. Optional extras (install only what you need)

The core install is tiny and offline. Each heavy capability is opt-in:

```bash
uv sync --extra pdf        # real PDF/arXiv extraction (Docling + PyMuPDF) — needed for `ingest`
uv sync --extra rag        # real semantic search for `ask` (sentence-transformers + LanceDB)
uv sync --extra scholar    # live Semantic Scholar for `cite`
uv sync --extra viz        # actually render plot images (matplotlib)
uv sync --all-extras       # everything at once
```

`torch` is pinned to the CPU build, so `uv sync --all-extras` resolves cleanly. (GPU users: see the
`[tool.uv.index]` note in `pyproject.toml`.)

---

## 6. Test it

```bash
uv run pytest                        # the offline test suite (no network, no model downloads)
uv run pytest -m live                # real-backend tests (need the extras + network)
uv run python scripts/real_test.py   # full real end-to-end run; set CLIO_TEST_LLM=claude|codex|ollama
```

---

## 7. Troubleshooting

- **`clio-parser: command not found`** — it lives in the project's venv; always call it as
  `uv run clio-parser …` (or `source .venv/bin/activate` first).
- **`ingest` says a dependency is missing** — run `uv sync --extra pdf`.
- **First `ingest` is slow** — Docling downloads ~500 MB of models once; subsequent runs are fast.
- **`review`/`ask`/`write` output looks like a placeholder** — you're on the default echo model; set
  `CLIO_LLM=claude` (or `codex`/`ollama`).
- **`cite` returns nothing** — the public Semantic Scholar endpoint rate-limited you; set
  `SEMANTIC_SCHOLAR_API_KEY`.
- **`torchvision::nms` error after installing `rag`/`pdf`** — reinstall the matching CPU wheel:
  `uv pip install --reinstall torchvision --index-url https://download.pytorch.org/whl/cpu`.

---

## More

- **Full action & payload reference, providers, output details** → [`docs/USAGE.md`](docs/USAGE.md)
- **What it can do + the 11 actions at a glance** → see §2 above; design in
  [`artifact/notes/DESIGN.md`](artifact/notes/DESIGN.md)
- **Working in this repo (for agents/contributors)** → [`AGENTS.md`](AGENTS.md)
- **Changes** → [`CHANGELOG.md`](CHANGELOG.md)

## License

BSD-3-Clause. Adapts MIT / Apache-2.0 sources with attribution (see module headers); no AGPL code.

# AUTHOR — Manual Test Guide (from scratch)

A complete, copy-paste walkthrough for a **brand-new person**: set up the project, exercise **every
one of the 26 actions** from the CLI, then drive AUTHOR from **Python**, **Claude Code**, and the
**CLIO agent**. Run the blocks top to bottom; each step says what to run, what to type, and what you
should see.

> Personal scratch doc — not part of the published repo. Delete it or add `MANUAL-TEST.md` to
> `.gitignore` if you don't want it tracked.

**Legend**
- 🟢 = works fully **offline** (no model, no network)
- 🌐 = needs **network** (PDF download / scholarly backends)
- 🤖 = needs a **real model** (`CLIO_LLM=…`); on the offline echo model it returns a placeholder
- Outputs are JSON on **stdout**; logs go to **stderr** (add `2>/dev/null` for clean JSON)

---

## 0. Prerequisites

```bash
# 1) Install uv (the only prerequisite) — skip if you already have it
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL -l          # reload PATH

# 2) Get the code and enter it
git clone <repo-url> clio-author      # or: cd into your existing checkout
cd clio-author

# 3) Install core (offline) + all heavy extras (pdf/rag/scholar/viz/mcp)
uv sync --all-extras
#   first run also primes the venv; the first `ingest` later pulls ~500 MB of Docling models once
```

### 0.1 Optional: real model + API keys

Most "writing/reviewing" actions need a real model. Pick one with `CLIO_LLM`
(`claude` | `codex` | `ollama` | `lmstudio` | `openrouter` | `litellm`). Keep keys in a local file
that loads automatically:

```bash
cp .env.local.example .env.local 2>/dev/null || touch .env.local
chmod 600 .env.local
# add only what you'll use, e.g.:
#   SEMANTIC_SCHOLAR_API_KEY=...      # nicer rate limits for cite/discover
#   GEMINI_API_KEY=...                # for CLIO_VISION=gemini
#   OPENROUTER_API_KEY=...            # for CLIO_LLM=openrouter
```

For these CLI tests `claude` is the easiest real model (no API key if Claude Code is logged in):

```bash
export CLIO_LLM=claude        # used by the 🤖 steps below; unset it to see the offline echo path
```

### 0.2 Health check (🟢)

```bash
uv run clio-author capabilities        # -> name=clio-author, 26 actions, each with phase + needs_source
uv run clio-author lifecycle           # -> the phase -> actions map (frame…ship…drive)
uv run ruff check clio_author tests    # -> All checks passed!
uv run mypy clio_author                # -> Success: no issues found in 74 source files
uv run pytest -q                       # -> ~605 passed, a few skipped/deselected
```

Make a scratch folder for artifacts so nothing lands in odd places:

```bash
mkdir -p mt-out          # everything below writes under ./mt-out
```

---

## Part A — Every action from the CLI

Walk the **author lifecycle**: Read → Understand → Sources → Plan → Draft → Strengthen → Referee →
Respond → Ship → Drive. We use **arXiv 1706.03762** ("Attention Is All You Need") — swap any id/PDF.

### A1 · Read & gather

**`ingest`** 🌐 — paper → clean Markdown + memory blocks + figures.
```bash
uv run --extra pdf clio-author ingest 1706.03762 --json '{"out_dir":"mt-out/attn"}'
ls mt-out/attn/            # expect: paper.md  blocks.json  img/  1706.03762.pdf
head -40 mt-out/attn/paper.md
```
*Expect:* `metadata.extractor=docling`, dozens of sections, several figures. **Other source forms:**
```bash
uv run --extra pdf clio-author ingest "Attention Is All You Need"   # by title (arXiv search)
uv run --extra pdf clio-author ingest ./some-local.pdf              # a local PDF
```

**`gather`** 🌐 — many sources → one merged `context.json` (a drop-in `--blocks-file`).
```bash
mkdir -p mt-out/notes && printf '# My idea\n\nA faster attention variant for long sequences.\n' > mt-out/notes/idea.md
uv run --extra pdf clio-author gather \
  --sources 1706.03762 mt-out/notes/ \
  --out-dir mt-out/ctx
ls mt-out/ctx/             # expect: context.json  context.md
```
*Expect:* `metadata.ingested` ≥ 2, merged sections labelled `[1706.03762] …` / `[idea.md] …`.

### A2 · Understand

**`ask`** 🤖 — grounded Q&A over the blocks.
```bash
uv run clio-author ask --question "What problem does this paper solve?" \
  --blocks-file mt-out/attn/blocks.json --format prose
```
*Expect (with a real model):* a 2–4 sentence grounded answer. *(Echo model → a placeholder echo.)*

**`kg`** 🤖 — content knowledge graph; `--full` runs the 6-stage pipeline with checkpoints.
```bash
uv run clio-author kg --blocks-file mt-out/attn/blocks.json --format prose          # single-shot
uv run clio-author kg --blocks-file mt-out/attn/blocks.json --full --out-dir mt-out/kg   # pipeline
ls mt-out/kg/              # expect: kg.json (+ kg_pipeline/ checkpoints when --full)
```

**`experiment`** 🤖🌐 — extract reference papers' design/experiments → recreate an evaluation plan.
```bash
uv run --extra pdf clio-author experiment \
  --sources 1706.03762 \
  --idea "A faster attention variant for long sequences" \
  --out-dir mt-out/eval --format prose
ls mt-out/eval/            # expect: experiment_designs.{json,md} + evaluation_plan.{json,md}
```

### A3 · Sources & citations

**`discover`** 🌐 — find real candidate papers (no model).
```bash
CLIO_SCHOLAR=auto uv run clio-author discover \
  --query "efficient transformers long context" --limit 5 --out-dir mt-out/lit --format prose
ls mt-out/lit/             # expect: discovered.json  discovered.bib
```

**`cite`** 🌐🟢(no model) — verify candidate titles → BibTeX suggestions (never overwrites).
```bash
CLIO_SCHOLAR=auto uv run clio-author cite \
  --candidates-json '[{"title":"Attention Is All You Need","year":2017}]' --format prose
```
*Expect:* `metadata.num_verified` ≥ 1 and a BibTeX entry.

**`check-refs`** 🟢 — deterministic BibTeX lint + in-text `\cite{}` cross-check (no model).
```bash
printf '@article{vaswani2017,\n title={Attention Is All You Need}, year={2017}\n}\n' > mt-out/refs.bib
printf 'We build on transformers \\cite{vaswani2017} and also \\cite{missing2020}.\n' > mt-out/body.md
uv run clio-author check-refs --bibtex-file mt-out/refs.bib --markdown-file mt-out/body.md --format prose
```
*Expect:* flags `missing2020` as cited-but-missing.

**`research`** 🤖🌐 — grounded literature brief (foundational/recent/competing + gaps).
```bash
CLIO_SCHOLAR=auto uv run clio-author research \
  --topic "efficient attention mechanisms" --depth deep --format prose
```

### A4 · Plan & write

**`plan`** 🤖 — idea → per-section blueprints (tasks, claims, sources, word budgets).
```bash
uv run clio-author plan \
  --idea "A faster attention variant for long sequences" \
  --blocks-file mt-out/ctx/context.json --out-dir mt-out/plan --format prose
ls mt-out/plan/            # expect: plan.json
```

**`write`** 🤖 — draft ONE section from source material.
```bash
uv run clio-author write --outline "Introduction" \
  --source-file mt-out/attn/paper.md --format prose
```

**`compose`** 🤖 — whole paper: idea → outline → cite → write → assemble; `--latex`/`--pdf`.
```bash
uv run clio-author compose \
  --idea "A faster attention variant for long sequences" \
  --log "On WikiText-103, perplexity improved 4% at 2x longer context." \
  --plan --review --latex --pdf --out-dir mt-out/paper
ls mt-out/paper/           # expect: paper.md, sections/, paper.tex, references.bib, (paper.pdf if a LaTeX engine is installed)
```

**`revise`** 🤖 — `--mode feedback` (address review) or `--mode style` (polish; aliases `edit`/`polish`).
```bash
uv run clio-author revise --mode style --text "We propose a method. It is good. It is fast." --voice concise --format prose
uv run clio-author revise --text "We propose a system." \
  --review-json '{"weaknesses":["no baseline comparison"]}' --format prose
# aliases still work:
uv run clio-author polish --text "We propose a method. It is good." --voice formal --format prose
uv run clio-author run edit --json '{"draft":"We propose X.","review":{"weaknesses":["unclear"]}}'
```

**`coherence`** 🤖 — cross-section consistency (terminology, contradictions, flow).
```bash
uv run clio-author coherence --markdown-file mt-out/paper/paper.md --format prose
```

### A5 · Strengthen (self-review your own draft)

**`verify-work`** 🤖 — does the prose make + support its planned claims?
```bash
uv run clio-author verify-work --text-file mt-out/attn/paper.md \
  --claims-json '["The model uses self-attention","It outperforms RNN baselines"]' --format prose
```

**`audit`** 🟢 — deterministic completeness: sections, word budgets, unresolved `[TODO]`/`[CITE:]`.
```bash
uv run clio-author audit --markdown-file mt-out/paper/paper.md --bibtex-file mt-out/paper/references.bib --format prose
```

**`section-review`** 🤖 — layered review of ONE section (L1 refs → L2 coherence → L3 persona).
```bash
uv run clio-author section-review --text-file mt-out/attn/paper.md --format prose
```

**`write_review`** 🤖 — writer ↔ reviewer critic-refine loop (run-only).
```bash
uv run clio-author run write_review --json '{"outline":{"title":"Introduction"},"max_rounds":2}'
```

### A6 · Referee (judge others' papers)

**`review`** 🤖 — full structured peer review (Accept/Reject + scores + critique).
```bash
uv run clio-author review --paper-file mt-out/attn/paper.md --ground --format prose --out mt-out/review.md
cat mt-out/review.md
```
Multimodal (sees figures) needs Gemini vision:
```bash
CLIO_VISION=gemini uv run clio-author review --paper-file mt-out/attn/paper.md \
  --figures-json '[{"figure_id":1,"image_path":"mt-out/attn/img/figure1.png","caption":"Transformer"}]' --format prose
```

**`meta_review`** 🟢 — area-chair aggregation of several reviews (run-only, offline arithmetic).
```bash
uv run clio-author run meta_review --json '{"reviews":[{"overall":6,"decision":"weak accept"},{"overall":8,"decision":"accept"}]}'
```

### A7 · Respond (after your reviews come back)

**`rebuttal`** 🤖 — point-by-point author response, grounded in the paper.
```bash
uv run clio-author rebuttal --paper-file mt-out/attn/paper.md \
  --review-json '{"weaknesses":["no ablation on attention heads","unclear scalability"]}' --format prose
```

### A8 · Illustrate (figures)

**`plot`** 🤖 — matplotlib code (run-only); real PNG with `CLIO_VISION=gemini` + `kind:"diagram"`.
```bash
uv run clio-author run plot --json '{"spec":{"kind":"line","title":"Loss vs steps","x":"step","y":"loss"}}'
# actually render it (needs the viz extra):
uv run --extra viz clio-author run plot --json '{"spec":{"kind":"line","title":"Loss"},"out_path":"mt-out/loss.py"}'
```

**`describe`** (describe_figures) 🤖 — caption the figures in blocks; real vision with Gemini.
```bash
uv run clio-author describe --blocks-file mt-out/attn/blocks.json --format prose
CLIO_VISION=gemini uv run clio-author describe --blocks-file mt-out/attn/blocks.json   # real images
```

**`figure_refine`** 🤖 — visualizer ↔ critic loop (run-only).
```bash
uv run clio-author run figure_refine --json '{"spec":{"kind":"line","title":"Throughput"},"max_rounds":2}'
```

### A9 · Ship

**`export`** 🟢 — `paper.md` → `paper.tex` + `references.bib`; `--pdf` compiles (needs a LaTeX engine).
```bash
uv run clio-author export --markdown-file mt-out/attn/paper.md \
  --bibtex-file mt-out/refs.bib --out-dir mt-out/camera-ready --pdf
ls mt-out/camera-ready/    # expect: paper.tex, references.bib, (paper.pdf if tectonic/latexmk/pdflatex is on PATH)
```

### A10 · Drive (goal-driven multi-step)

**`orchestrate`** 🤖 — plan + run a sequence of actions from one natural-language goal.
```bash
uv run clio-author orchestrate \
  --goal "ingest arXiv 1706.03762, then review it and verify its claims" \
  --out-dir mt-out/run --format prose
```

### A11 · The `--sources` shortcut (any grounding action)

Instead of pre-ingesting, point a grounding action straight at files/folders/PDFs:
```bash
uv run --extra pdf clio-author plan --idea "A faster attention variant" --sources 1706.03762 mt-out/notes/ --format prose
```

### A12 · Coverage checklist

Tick each as you go (26 actions): ingest ☐ · gather ☐ · ask ☐ · kg ☐ · experiment ☐ · discover ☐ ·
cite ☐ · check_refs ☐ · research ☐ · plan ☐ · write ☐ · compose ☐ · revise ☐ · coherence ☐ ·
verify_work ☐ · audit ☐ · section_review ☐ · write_review ☐ · review ☐ · meta_review ☐ · rebuttal ☐ ·
plot ☐ · describe_figures ☐ · figure_refine ☐ · export ☐ · orchestrate ☐.

---

## Part B — Drive it as a subagent (in-process Python)

Save as `mt-subagent.py`, then `uv run python mt-subagent.py`:

```python
from clio_author.integration.clio_adapter import ClioAuthorSubagent
from clio_author.llm.providers import resolve_llm

sub = ClioAuthorSubagent(llm=resolve_llm("claude"))   # | "codex" | "ollama" | None (offline echo)

# 1) discovery — every action carries lifecycle phase + needs_source
caps = sub.capabilities()
print(len(caps["actions"]), "actions;", len(caps["lifecycle"]), "phases")

# 2) ingest -> ask -> review (no exceptions ever; failures land in result["metadata"]["error"])
ing = sub.run("ingest", {"source": "1706.03762", "out_dir": "mt-out/sa"})
ans = sub.run("ask", {"question": "What is the main contribution?", "blocks": ing["structured"]})
rev = sub.run("review", {"paper": ing["content"]})
print("answer:", ans["content"][:200])
print("review keys:", list((rev.get("structured") or {}).keys()))
```
*Expect:* prints `26 actions; 9 phases`, then a grounded answer + a review structure. Every call
returns `{"action","content","structured","metadata"}`.

---

## Part C — Drive it from Claude Code

### C1 · Install the `/author` slash command
```bash
mkdir -p .claude/commands
cp integration/claude/author.md .claude/commands/author.md
```
Open this repo in Claude Code and run:
```
/author ingest arXiv 1706.03762 and give me a grounded review
```
Claude runs the `clio-author` CLI, reads the JSON, and reports back.

### C2 · Or just ask Claude to use the CLI directly
In Claude Code (no slash command needed):
```
Use the clio-author CLI in this repo: ingest 1706.03762 into mt-out/c, then run `review`
on the resulting paper.md and summarize the decision and top-3 weaknesses.
```

> **Nesting rule:** Claude is the host, so do **not** set `CLIO_LLM=claude` for the nested calls — it
> recurses and hangs. Prefer the no-model actions for grounding (`cite`, `discover`, `check_refs`,
> `audit`, `ingest`, `gather`), or let an action run on the offline echo model when you only need its
> structure. (The shipped command file already states this.)

---

## Part D — Drive it from the CLIO agent (via the MCP bridge)

CLIO is a FastMCP-gateway agent: it mounts external **MCP servers** declared in
`<workspace>/.clio/mcp.yaml` as `name: <command-or-url>`. AUTHOR ships an MCP bridge exposing two
tools (`capabilities`, `run`), so CLIO can call every action.

### D1 · Install CLIO
```bash
curl -fsSL https://raw.githubusercontent.com/iowarp/clio-agent/main/install/install.sh | bash
# this drops a `clio` command on your PATH
```

### D2 · Make sure AUTHOR's MCP bridge runs
```bash
# from the clio-author checkout — sanity check it launches (Ctrl-C to stop):
uv run --extra mcp python -m clio_author.integration.mcp_bridge      # stdio (default)
```

### D3 · Register AUTHOR with CLIO

Pick **one** of the two transports. Use the **absolute path** to your clio-author checkout.

**Option 1 — stdio (simplest; CLIO spawns the bridge):** in your CLIO working directory create
`.clio/mcp.yaml`:
```yaml
mcp_servers:
  author: uv run --project /ABS/PATH/TO/clio-author --extra mcp python -m clio_author.integration.mcp_bridge
```

**Option 2 — HTTP (long-lived shared server):** start the bridge in its own terminal…
```bash
CLIO_MCP_TRANSPORT=http CLIO_MCP_HOST=127.0.0.1 CLIO_MCP_PORT=8000 \
  uv run --extra mcp python -m clio_author.integration.mcp_bridge
```
…then in `.clio/mcp.yaml`:
```yaml
mcp_servers:
  author: http://127.0.0.1:8000/mcp
```

> **Real model from CLIO → AUTHOR:** the bridge runs AUTHOR with whatever `CLIO_LLM` is in *its* env
> (default `echo`). For real text output set it in the bridge's environment to a provider **different
> from CLIO's own model** (avoid the nesting deadlock). For stdio, prepend it in the command, e.g.
> `... --extra mcp` → `CLIO_LLM=openrouter OPENROUTER_API_KEY=... uv run --project … python -m …`.

### D4 · Run CLIO and use the tools
```bash
clio        # launches the CLIO TUI in the current (workspace) directory
```
Then prompt CLIO:
```
List the tools from the `author` server, then use it to ingest arXiv 1706.03762 and
verify its citations. Report what the author tools returned.
```
CLIO's planner will discover the `author` server's `capabilities`/`run` tools (it namespaces them by
server, e.g. `author_run`), call them, and fold the JSON results into its answer.

*Expect:* CLIO lists ~26 actions from `capabilities`, then calls `run` with `action="ingest"` (and
`cite`/`discover` for grounding) and reports the results. Watch the bridge terminal (HTTP mode) or
CLIO's tool trace to confirm the calls land.

### D5 · Quick non-CLIO proof the bridge works (optional)
```bash
uv run --extra mcp python - <<'PY'
from clio_author.integration.mcp_bridge import build_server      # the FastMCP server CLIO mounts
from clio_author.integration.clio_adapter import ClioAuthorSubagent
server = build_server()
print("bridge server:", getattr(server, "name", server))         # -> clio-author
print(len(ClioAuthorSubagent().capabilities()["actions"]), "actions reachable via run()")
PY
```
*Expect:* `bridge server: clio-author` and `26 actions reachable via run()`.

---

## Cleanup & troubleshooting

```bash
rm -rf mt-out mt-subagent.py        # remove scratch artifacts
```

- **`clio-author: command not found`** → call it as `uv run clio-author …` (it lives in the venv).
- **`ingest` missing-dependency error** → `uv sync --extra pdf`; first run downloads ~500 MB once.
- **Output looks like an echo/placeholder** → you're on the default model; `export CLIO_LLM=claude`.
- **`cite`/`discover` empty** → try `CLIO_SCHOLAR=openalex` or `arxiv`; set `SEMANTIC_SCHOLAR_API_KEY`.
- **`--pdf` says `pdf_error`** → install a LaTeX engine (`tectonic`, `latexmk`, or `pdflatex`); the
  export still succeeds without it.
- **A host (Claude/Codex/CLIO) hangs calling AUTHOR** → the nested `CLIO_LLM` matches the host model;
  use a no-model action or a different nested provider.
- **CLIO doesn't see the `author` tools** → check the path in `.clio/mcp.yaml` is absolute and the
  bridge launches standalone (D2); in HTTP mode confirm the server is still running on the port.

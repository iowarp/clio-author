# AUTHOR (clio-author) — CLI Runbook

Run these **in order, one block at a time**, and inspect the result after each. Every command
prints a JSON result on **stdout** (logs go to stderr — add `2>/dev/null` for clean JSON).
Exit code `0` = ok, `1` = error.

All examples write artifacts under `runbook-out/` in the repo root so you can open them.

---

## 0. One-time setup

```bash
cd ~/Illinois_Tech/Summer26/RA/clio-author      # the repo
uv sync --all-extras                            # installs pdf/rag/scholar/viz + repairs the venv
mkdir -p runbook-out
```

**Keys / models** (put real keys in `.env.local` — auto-loaded, never on the command line):

```bash
# .env.local  (already present in this repo)
SEMANTIC_SCHOLAR_API_KEY=...     # for `cite` (avoids rate limits)
GEMINI_API_KEY=...               # for `describe`/`plot` vision (CLIO_VISION=gemini)
```

- Text actions need a model: `CLIO_LLM=claude` (the `claude` CLI on PATH) — or `codex` / `ollama`.
- Without `CLIO_LLM`, text actions return a harmless offline **echo** placeholder.

---

## 1. Health check

```bash
uv run ruff check clio_author tests        # lint        -> "All checks passed!"
uv run mypy clio_author                    # types       -> "Success: no issues found in 55 source files"
uv run pytest -q                           # 434 tests   -> "434 passed, 3 skipped, 10 deselected"
```

---

## 2. The 16 actions

### 1) capabilities — list everything it can do
```bash
uv run clio-author capabilities
```
**Expect:** `name=clio-author`, `version 0.3.0`, **16 actions**.

---

### 2) ingest — paper → clean Markdown + memory blocks + figures  *(run this first; later steps reuse its output)*
**Settings:** `--extra pdf` (Docling). First run downloads ~500 MB of models.
```bash
uv run --extra pdf clio-author ingest 2601.23265 --json '{"out_dir":"runbook-out/ingest"}'
```
**Expect:** `extractor=docling`, ~125 sections, 12 figures.
**Artifacts:** `runbook-out/ingest/{paper.md, blocks.json, img/figure1..12.png, 2601.23265.pdf}`
*(also works with a title `"Attention Is All You Need"`, a URL, or a local PDF path.)*

---

### 3) ask — answer a question grounded in the paper's blocks
```bash
CLIO_LLM=claude uv run clio-author ask \
  --question "What problem does this paper solve?" \
  --blocks-file runbook-out/ingest/blocks.json --format prose
```
**Expect:** a grounded answer; without `--format prose` you get JSON with `cited_block_ids`.

---

### 4) review — structured peer review
```bash
CLIO_LLM=claude uv run clio-author review --paper-file runbook-out/ingest/paper.md --format prose
```
**Expect:** a prose review (summary / strengths / weaknesses). Add `--ground` (with `CLIO_SCHOLAR=auto`)
to ground critiques in retrieved related work.

---

### 5) write — draft one section from an outline + source
```bash
CLIO_LLM=claude uv run clio-author write \
  --outline "Introduction" --source-file runbook-out/ingest/paper.md --format prose
```
**Expect:** a drafted Introduction grounded in the source.

---

### 6) edit — revise prose to address feedback
```bash
CLIO_LLM=claude uv run clio-author run edit \
  --json '{"draft":"We propose a system. It is good.","review":{"weaknesses":["no baseline comparison","unclear evaluation"]}}'
```
**Expect:** revised text addressing the weaknesses.

---

### 7) polish — improve clarity / flow / voice
```bash
CLIO_LLM=claude uv run clio-author polish \
  --text "We propose a method. It is good. It does many useful things." --voice concise --format prose
```
**Expect:** tightened prose, citations preserved.

---

### 8) cite — verify citations → BibTeX suggestions (never overwrites your refs)
**Settings:** `CLIO_SCHOLAR=auto` cascades Semantic Scholar → OpenAlex → Crossref → arXiv.
```bash
CLIO_SCHOLAR=auto uv run --extra scholar clio-author cite \
  --candidates-json '[{"title":"Attention Is All You Need","year":2017}]' \
  --json '{"out_dir":"runbook-out/cite-out"}'
```
**Expect:** `num_verified=1 meets_90pct=True`.
**Artifacts:** `runbook-out/cite-out/{suggested.bib, suggested_citation_map.json}`

---

### 9) meta_review — aggregate several reviews (offline, no model)
```bash
uv run clio-author run meta_review \
  --json '{"reviews":[{"Overall":7,"Decision":"Accept"},{"Overall":5,"Decision":"Reject"}]}'
```
**Expect:** `decision=Accept overall=6 reviewer_count=2`.

---

### 10) coherence — cross-section consistency check
```bash
CLIO_LLM=claude uv run clio-author coherence \
  --sections-json '[{"title":"Introduction","draft":"Method X improves accuracy by 5% over the baseline."},{"title":"Results","draft":"Method X achieves a 12% gain over the baseline transformer."}]' \
  --format prose
```
**Expect:** flags the **5% vs 12% contradiction** (2 issues).

---

### 11) kg — content knowledge graph (claims/methods/datasets/results + relations)
```bash
CLIO_LLM=claude uv run clio-author kg \
  --blocks-file runbook-out/ingest/blocks.json --json '{"out_dir":"runbook-out/kg-out"}'
```
**Expect:** dozens of nodes/edges across 7 types. *(Full 125-section paper is slower — batched.)*
**Artifacts:** `runbook-out/kg-out/{kg.json, kg.mmd}` (`kg.mmd` is a Mermaid graph).

---

### 12) plot — generate matplotlib code
```bash
CLIO_LLM=claude uv run clio-author run plot \
  --json '{"spec":{"kind":"plot","intent":"bar chart comparing baseline 72 vs ours 89"}}'
```
**Expect:** matplotlib Python code in `content`.

---

### 13) describe — caption a figure by LOOKING at it (Gemini vision)
**Settings:** `CLIO_VISION=gemini` (uses `GEMINI_API_KEY`).
```bash
CLIO_VISION=gemini uv run clio-author describe \
  --blocks-json '{"figures":[{"figure_id":1,"image_path":"'"$PWD"'/runbook-out/ingest/img/figure1.png"}]}' \
  --format prose
```
**Expect:** `vision_described:[1]` + a real description of the image.

---

### 14) export — Markdown sections → LaTeX
```bash
uv run clio-author export --title "Demo Paper" \
  --sections-json '[{"title":"Introduction","draft":"We present **AUTHOR**."},{"title":"Method","draft":"It uses a multi-agent pipeline."}]' \
  --json '{"out_dir":"runbook-out/export-out"}'
```
**Expect:** a compilable `paper.tex`.
**Artifacts:** `runbook-out/export-out/paper.tex`

---

### 15) compose — write a WHOLE paper from an idea (+ optional outline/log/refs) → Markdown + LaTeX
```bash
CLIO_LLM=claude uv run clio-author compose \
  --idea "AUTHOR: a multi-agent system that reads, reviews, and writes scientific papers." \
  --json '{"outline":{"title":"AUTHOR","sections":[{"title":"Introduction","goal":"motivate and state the contribution"},{"title":"Method","goal":"the multi-agent pipeline"}]}}' \
  --latex --out-dir runbook-out/compose-out
```
**Expect:** `num_sections=2 latex=True`.
**Artifacts:** `runbook-out/compose-out/{paper.md, sections/01-*.md, 02-*.md, paper.tex}`
**Variations:** drop the `--json` outline to have it **generate** the outline from the idea; add `--review`
for a writer↔reviewer pass per section; pass `experimental_log`/`candidates`/`blocks` in `--json` to ground it.

---

### 16) write_review — writer ↔ reviewer refine loop
```bash
CLIO_LLM=claude uv run clio-author run write_review \
  --json '{"outline":{"title":"Introduction","goal":"introduce AUTHOR"},"source":"AUTHOR reads, reviews, and writes papers using cooperating agents.","max_rounds":1}'
```
**Expect:** a draft refined through one writer→reviewer→revise round.

---

### 17) figure_refine — visualizer ↔ critic loop, then render to PNG
```bash
CLIO_LLM=claude uv run clio-author run figure_refine \
  --json '{"spec":{"kind":"plot","intent":"line chart of loss decreasing over epochs; save to figure.png"},"max_rounds":1}' \
  > runbook-out/figure_refine.json 2>/dev/null

# render the generated code to an actual image:
uv run --extra viz python -c "
from pathlib import Path; import json
from clio_author.experts.figure_agent import render_plot_code
code = json.load(open('runbook-out/figure_refine.json'))['content']
p = render_plot_code(code, Path('runbook-out/figure.png'), timeout=40)
print('rendered:', p, Path(p).stat().st_size, 'bytes')"
```
**Expect:** refined figure code, then a rendered `runbook-out/figure.png`.

---

## 3. Tips
- Clean JSON: append `2>/dev/null`. Pretty-print: `… 2>/dev/null | python3 -m json.tool`.
- Swap the model anytime: `CLIO_LLM=codex` or `CLIO_LLM=ollama CLIO_LLM_MODEL=llama3.1:8b`.
- Any action is also reachable generically: `uv run clio-author run <action> --json '{...}'`.
- Large inline JSON hits the shell arg limit — use the `--*-file` flags (`--blocks-file`, `--paper-file`,
  `--source-file`, `--candidates-file`, `--sections-file`, `--markdown-file`).
- In-process (from Python): `from clio_author.integration.clio_adapter import ClioAuthorSubagent`
  then `ClioAuthorSubagent(llm=...).run("review", {...})`.

## Appendix — where each expert's LLM prompt lives (if you want to read/tune them)
| Action(s) | System prompt | File |
|---|---|---|
| ask | `PAPER_QA_SYSTEM_PROMPT` | `clio_author/experts/paper_qa.py` |
| review | `REVIEWER_SYSTEM_PROMPT` | `clio_author/experts/reviewer.py` |
| write | `WRITER_SYSTEM_PROMPT` | `clio_author/experts/writer.py` |
| edit | `EDITOR_SYSTEM_PROMPT` | `clio_author/experts/editor.py` |
| polish | `POLISH_SYSTEM_PROMPT` | `clio_author/experts/polish.py` |
| coherence | `COHERENCE_SYSTEM_PROMPT` | `clio_author/experts/coherence.py` |
| kg | `KG_SYSTEM_PROMPT` + `KG_PROMPT` | `clio_author/experts/kg.py`, `clio_author/retrieval/kg.py` |
| plot / describe / figure_refine | figure prompts | `clio_author/experts/figure_agent.py` |
| compose | outline-gen prompt | `clio_author/experts/compose.py` |
</content>

# DESIGN — clio-parser: a standalone multi-agent paper harness

Status: **draft for review**. Grounded in the per-artifact notes + SYNTHESIS.md in this folder.

> **Form:** clio-parser is a **standalone, pure-Python multi-agent agent
> harness** — a *proper agent*, modeled on **papervizagent** (orchestrator/processor + shared-state
> expert agents + critic refinement loop) and **protoneo/knowledge** (`BaseAgent` + `AgentProtocol`
> + deliberation engine + knowledge graph). It is **NOT** an MCP server and **NOT** a
> Markdown/blueprint agent. The CLIO agent integrates it as a **standalone subagent it can invoke**
> (load / unload / invoke); that adapter is thin and deferred — the harness stands and is tested on
> its own.

## 0. Goal

clio-parser combines **paper-to-md + PaperBanana (arXiv 2601.23265)** for *processing papers* and
**wtf-p + PaperOrchestra (arXiv 2604.05018)** for *writing and editing*, decomposed into **expert
agents, retrieval techniques, and read/write/edit tools** so that a main agent can **review and
write papers**. The harness design draws on **papervizagent** and **protoneo/knowledge** as
reference architectures. The result is a single cohesive package the CLIO agent can invoke,
evaluated against those systems as baselines.

## 1. Architecture — the harness

A single importable package with a main orchestrator agent that routes to expert subagents, backed
by retrieval and file read/write/edit tools.

```
clio_parser/
  __init__.py                 # exports ClioParserAgent (the main agent / entry surface)
  agent.py                    # MainAgent: plans -> delegates to experts -> synthesizes (review & write)
  harness/
    base.py                   # BaseAgent (role, model, system_prompt, llm_client, tools) — protoneo-style
    protocol.py               # AgentProtocol interface
    engine.py                 # Orchestration engine (selects a pattern, runs experts, collects results)
    patterns.py               # Sequential | Parallel | RoundRobin | CriticRefine(IndependentSynthesis)
    session.py                # SessionContext + checkpoints (resumable runs)
    types.py                  # Message, AgentOutput, Document, Block, GroundingSource (Pydantic)
  experts/                    # the pure-Python expert subagents
    ingestor.py               # PDF/arXiv -> scientific Markdown + memory blocks (processing)
    figure_agent.py           # figure/table/equation understanding (+ optional PaperBanana-style gen)
    retriever.py              # RAG + Semantic Scholar + (optional) KG retrieval
    reviewer.py               # paper review w/ critic personas + rubric (AgentReview-style)
    writer.py                 # section drafting (outline -> plan -> write), PaperOrchestra/wtf-p taxonomy
    editor.py                 # targeted edits/revisions via read/write/edit tools
    citation.py               # citation discovery + verification (writes suggestions only)
  ingest/                     # processing core (fresh minimal port)
    docling_extract.py        # Docling primary + PyMuPDF OCR fallback
    postprocess/              # sections, citations, equations, figures, bibliography, cleanup
    tables.py                 # NEW: dedicated table fidelity pass (gap nobody solved)
    blocks.py                 # memory-block schemas + selective-injection assembly
  retrieval/
    rag.py                    # embeddings + vector index (LanceDB) over blocks/chunks
    scholar.py                # Semantic Scholar grounding (fuzz>70, date cutoff, >=90% verified)
    kg.py                     # OPTIONAL: re-implemented (not copied) protoneo KG concepts
  tools/
    files.py                  # read / write / edit (propose+apply diff) tools for the agents
  llm/
    client.py                 # provider abstraction (local Gemma/Qwen vision, Ollama, API) — vision-capable
  config.py                   # harness config (models, depths, retrieval, pattern selection)
  cli.py                      # `clio-parser process <url>` / `review <md>` / `write <materials>`
integration/
  clio_adapter.py             # thin shim so CLIO can invoke ClioParserAgent (deferred)
tests/
  baselines/                  # compare against paper-to-md / PaperBanana / PaperOrchestra / protoneo
```

### Main agent loop (review & write)
`MainAgent` (modeled on protoneo's engine + papervizagent's processor): given a task (e.g. "review
this paper", "write the methods section"), it plans, delegates to the relevant experts through the
**engine** + a **pattern**, threads results through a shared session state, runs a **critic-refine**
loop until quality passes, and synthesizes the answer. The LM decides routing; experts are plain
Python classes implementing `AgentProtocol`.

## 2. The two capability tracks

**Track A — Processing papers** (paper-to-md + PaperBanana):
`ingestor` → `ingest/` Docling + postprocess (fresh minimal port of phagocyte/paper-to-md) →
clean scientific Markdown + `figure/equation/code/section` **memory blocks** → `figure_agent` adds
VLM descriptions → blocks stored for **selective context injection** + `retrieval/rag` for big papers.

**Track B — Writing & editing** (wtf-p + PaperOrchestra):
`writer` (outline→plan→write, wtf-p taxonomy) + `citation`/`retriever` (PaperOrchestra Semantic
Scholar grounding) + `reviewer` (AgentReview-style rubric + PaperBanana critic loop) + `editor`
(read/write/edit tools, diff-based). Main agent reviews and writes.

## 3. Reuse map (what we lift vs re-implement)
- **Harness skeleton** ← protoneo `BaseAgent`/`AgentProtocol`/engine/patterns — *re-implement* the
  pattern (AGPL-3.0; don't copy code), keep it permissive (BSD-3 to match CLIO).
- **Processing core** ← fresh minimal port of paper-to-md/phagocyte `postprocess` (MIT / first-party).
- **Critic-refine loop** ← PaperBanana papervizagent (Apache-2.0) — adapt.
- **Semantic Scholar grounding + AgentReview** ← PaperOrchestra (Apache-2.0) — adapt.
- **Writer/reviewer taxonomy** ← wtf-p (MIT) — mirror as Python experts.
- **Retrieval** ← phagocyte processor concepts (LanceDB/Qwen3/OpenCLIP/bge) — fresh port.

## 4. Baseline tests
Same as before, run from `tests/baselines/`: PDF→MD fidelity vs paper-to-md/phagocyte; figure
quality vs PaperBanana (VLM-as-Judge 4 dims); citation verification ≥90% vs PaperOrchestra; review
win-rate vs single-agent; Q&A accuracy with/without selective injection. Fixtures = the two papers
in `artifact/papers/`.

## 5. Milestones
- **M0 — Harness skeleton:** `BaseAgent`/`AgentProtocol`/engine/patterns/session/types + a trivial
  echo expert; `ClioParserAgent.invoke()` works end-to-end.
- **M1 — Processing track:** `ingest/` port + `ingestor` expert → Markdown + blocks; baseline diff.
- **M2 — Retrieval + injection:** `rag.py` + selective block injection + Q&A.
- **M3 — Grounding:** `scholar.py` + `citation` expert.
- **M4 — Review:** `reviewer` + critic-refine pattern + multi-reviewer.
- **M5 — Write/edit:** `writer` + `editor` + file tools (outline→plan→write→revise).
- **M6 — Figures (opt):** `figure_agent` generation.
- **M7 — Harden:** tables, generalized equations, baseline eval report.
- **M8 — CLIO integration:** thin `clio_adapter` so CLIO can invoke the harness.

## 6. Open choices (defaults chosen)
1. **Agent framework:** plain Python (protoneo `BaseAgent` style) — *default*; vs DSPy (CLIO's
   engine). Plain Python keeps the harness independent and testable.
2. **LLM/vision + embedding models:** local Gemma/Qwen vision + Ollama embeddings — *default*.
3. **Knowledge graph (`kg.py`):** include now or defer to post-M7 — *default: defer* (optional).
4. **Phagocyte license:** unspecified — confirm before lifting any code verbatim; the plan is a fresh port regardless.

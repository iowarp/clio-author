# SYNTHESIS — similarities, differences, reuse-vs-rebuild

Cross-artifact synthesis grounded in the per-artifact notes in this folder. The goal: decide
what clio-author **reuses**, what it **adapts**, and what it **builds new**, and how each piece
maps onto CLIO's actual extension points.

## 1. The one fact that drives everything: how CLIO is extended

CLIO (`artifact/repos/clio`, develop) is **not a framework you subclass** — it *is* the agent.
Its only sanctioned extension surface is:

- **Agent Blueprints** — a directory with `AGENT.md` (YAML frontmatter) + `experts/*.md`
  (Markdown-with-frontmatter, body = system prompt). Compiled at runtime to DSPy modules
  (`Predict`/`ChainOfThought`/`ReAct`). Loader `gact/agent_blueprints.py`; schema
  `gact/expert_packs.py::parse_expert_file`; compile `gact/app.py::_build_blueprint_dspy_module`.
- **Declared MCP servers** — every domain tool is an MCP server named in `AGENT.md`
  `mcp_servers:` (or `mcp.yaml`), auto-namespaced to `<ns>_<tool>` by the FastMCP gateway.
- **Built-in fs/shell tools** — `fs_read_file` / `fs_propose_edit` / `fs_apply_edit_write`
  give a ready read/edit/diff surface (edits surface as GACT `file_diffs`).
- **ARC memory + context-files** — context is *compiled, not concatenated*; **no embeddings in
  core**. Selective injection via context-file attachments and ARC `Context`/`DatasetProfile`.

**This describes how CLIO extends *itself*. clio-author is deliberately NOT built that way.**
clio-author is a **standalone, pure-Python multi-agent harness** (a proper
agent like protoneo/papervizagent), not an MCP server or Markdown blueprint. CLIO integrates it as a
**standalone subagent it can invoke** via a thin adapter (deferred). So the CLIO extension facts
above are useful only for the eventual integration shim — the harness itself stands alone. See
DESIGN.md §1.

## 2. What each artifact contributes

| Artifact | License | Lang | The asset we actually want | Reuse mode |
|---|---|---|---|---|
| **phagocyte** (`src/ingestor`) | unspecified (confirm) | Py | `postprocess/process_markdown()` (sections→citations→equations→figures→bib→cleanup), Docling+PyMuPDF two-stage, VLM figure captions, two-layer audit, LanceDB RAG, provider abstraction | **LIFT** (first-party) |
| **paper-to-md** | MIT | Py | Upstream of phagocyte's postprocess; the RAG-JSON schemas (`figures.json`/`equations.json`/`code_blocks.json`/`enrichments.json`); FastMCP server pattern; `pdf2md` depth tiers | ADAPT (schemas → memory blocks) |
| **protoneo** (`knowledge/`,`deliberation/`) | **AGPL-3.0** | Py | KG 6-stage pipeline; deliberation patterns (Sequential/Parallel/RoundRobin/**IndependentSynthesis**); `DomainConfig` kernel/app split; `get_accumulated_context()` selective injection | **RE-IMPLEMENT concepts** (AGPL ⇒ don't copy code into a permissive pkg) |
| **paper-orchestra** (PaperOrchestra) | Apache-2.0 | Py | Two-stage **Semantic Scholar** citation grounding (`scholar_utils.py`, fuzz>70, date cutoff, ≥90% verified); **AgentReview** refinement; outline JSON schema; booktabs table writer | ADAPT (Semantic Scholar tool, review loop) |
| **papervizagent** (PaperBanana) | Apache-2.0 | Py | Critic↔Visualizer **refinement loop** w/ short-circuit; matplotlib code-gen + image-gen; VLM-as-Judge 4 dims; shared-state agent pattern | ADAPT (figure agent + critic loop) |
| **wtf-p** | MIT | JS/MD | The **Claude-Code packaging pattern** (md+YAML agents, thin-orchestrator→agent→quality-loop, manifest installer, WCN compression); 11-agent / 36-command writing workflow taxonomy | TEMPLATE (mirror the agent/command taxonomy as CLIO experts) |
| 2 papers | — | — | The *why* and the *eval methodology* (PaperBananaBench, PaperWritingBench, VLM-as-Judge, win-rate human eval, ~90% citation verification) | METHOD (baseline test design) |

## 3. Similarities across the codebases (the convergent design)

1. **Multi-agent, role-specialized.** PaperBanana (7), PaperOrchestra (5), protoneo (config-driven
   council), wtf-p (11). All split work into experts with one job each. CLIO models this natively
   as blueprint experts + child-expert delegation + `fanout`.
2. **Critic / refinement loop.** PaperBanana critic↔visualizer (T=3, short-circuit on "No changes
   needed"), PaperOrchestra Content-Refinement via AgentReview, protoneo variance-triggered
   round-robin, wtf-p plan-checker + argument-verifier. **Refinement-until-quality is universal.**
3. **Grounding to fight hallucination.** PaperOrchestra → Semantic Scholar verified bib;
   protoneo → KG with confidence scores + grounding verification; wtf-p → BibTeX audit
   (writes to `suggested.*` only). phagocyte → corpus audit + BigSet verify-before-commit.
   **"Verify before you commit/cite" is a shared principle.**
4. **Docling is the de-facto PDF engine.** phagocyte, paper-to-md, and protoneo all use Docling
   (protoneo + phagocyte both add VLM captions). PaperBanana uses MinerU instead (the only outlier).
5. **VLM for figures.** phagocyte (llava/moondream), paper-to-md (qwen3-vl), PaperBanana
   (Gemini/Nano-Banana). Native-vision local models are a primary design target.

## 4. Key differences / tensions to resolve

- **Embeddings: CLIO has none; phagocyte has a full LanceDB stack.** CLIO core retrieval is
  B-tree + keyword + ARC. The requirement to "inject parts or all of the paper" + Q&A means we need
  semantic retrieval. Cleanest: expose phagocyte's processor (LanceDB/Qwen3/OpenCLIP/bge-reranker)
  as a `rag` MCP tool, *not* as a CLIO core change. (CLIO's outer harness already shows `rag`/
  `processor` skills — confirm whether those are phagocyte-derived.)
- **Python vs Claude-Code packaging.** wtf-p proves the Markdown-as-program pattern for Claude
  Code; CLIO uses the *same idea* but its own blueprint schema (not wtf-p's). So we borrow wtf-p's
  **taxonomy** (outliner, planner, writer, reviewer, citation, coherence…) but express it as **CLIO
  blueprint experts**, not wtf-p commands. (The `/wtfp:` skills already in this harness can be a
  reference/fallback, but the deliverable targets CLIO's blueprint format.)
- **License boundary.** protoneo is **AGPL-3.0**; CLIO is BSD-3. We must **re-implement** protoneo's
  KG/deliberation *concepts* rather than vendoring its code, to keep clio-author permissively
  licensed. paper-to-md (MIT), PaperBanana/PaperOrchestra (Apache-2.0), phagocyte (first-party) are
  copy-compatible.
- **MinerU vs Docling.** Standardize on **Docling** (already in phagocyte/protoneo; you own that
  code). Treat MinerU as an optional alternate extractor, not the default.
- **Tables.** Nobody nails tables: phagocyte has *no* dedicated table post-processing; this is the
  single biggest "scientific-paper-perfect" gap to close.
- **Equation repair is brittle.** phagocyte's equation regexes are transformer/GAN-paper-specific.
  Needs generalization (or a VLM-assisted equation pass) for arbitrary arXiv papers.

## 5. The mapping — each capability → clio-author harness component

| Requirement | Source artifact | clio-author realization (standalone harness) |
|---|---|---|
| arXiv/PDF → clean scientific Markdown | phagocyte ingestor + paper-to-md postprocess | `ingest/` (Docling+postprocess, fresh port) driven by `experts/ingestor.py` |
| Vision (figures/tables/eq) w/ local model | phagocyte VLM + paper-to-md qwen3-vl | `experts/figure_agent.py` + `llm/client.py` vision path |
| Store as memory blocks, selective injection | paper-to-md JSON schemas | `ingest/blocks.py` schemas + session-level selective injection |
| Inject part/all of paper for Q&A | phagocyte RAG | `retrieval/rag.py` (LanceDB) + `agent.py` Q&A |
| Break into expert agents | wtf-p taxonomy + protoneo council | `experts/*.py` Python subagents under the engine |
| Retrieval techniques | PaperOrchestra Semantic Scholar + protoneo KG + phagocyte RAG | `retrieval/scholar.py` + `retrieval/rag.py` + optional `retrieval/kg.py` |
| Read/write/edit tools (review & write) | CLIO fs built-ins + wtf-p workflow | `tools/files.py` (read/write/propose+apply-edit) used by writer/editor experts |
| Quality / review loop | PaperBanana critic + PaperOrchestra AgentReview + protoneo deliberation | `harness/patterns.py::CriticRefine` + `experts/reviewer.py` (multi-reviewer) |
| Load/unload/invoke as one package | reference harnesses | `ClioAuthorAgent.invoke()`; `integration/clio_adapter.py` shim (deferred) |
| Test against baselines | both papers' benchmarks | `tests/baselines/` vs paper-to-md/PaperBanana/PaperOrchestra |

## 6. Open cross-cutting questions (carry into DESIGN)

1. Confirm Phagocyte's **license** (permissive?) so we can lift `ingestor` directly.
2. The CLIO `external/clio-agent-marketplace` submodule isn't checked out — we need one real
   `AGENT.md` + declared-MCP example (e.g. `data-semantics`) to copy the idiom exactly.
3. Are this harness's `rag`/`processor` skills the phagocyte processor? If so, retrieval is largely
   solved and we just wire it.
4. Vision path: CLIO's planner passes `images` to multimodal LMs — can the PDF MCP hand back page
   images for a native-vision pass, or is VLM captioning done inside the MCP server?
5. Scope of "writing": full PaperOrchestra-style autonomous drafting, or wtf-p-style human-in-the-loop
   section writing inside CLIO? (Affects how many writer experts we author.)

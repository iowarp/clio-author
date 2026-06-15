# ProtoNeo — Deep Study Notes

Repo: `/home/shazzadul/Illinois_Tech/Summer26/RA/clio-parser/artifact/repos/protoneo`
Source: `github.com/akougkas/protoneo`. Studied read-only, 2026-06-15.

---

## 1. Purpose, Tech Stack, License

**Tagline (README):** "AI peer review for your papers, before you submit." `pyproject.toml` describes it as a **"Composable LLM deliberation runtime."**

Two layers (see `CLAUDE.md`, `docs/kernel.md`):
- **`protoneo/`** — the *kernel*: a domain-agnostic, composable runtime for "LLM councils." Provides agent primitives, deliberation patterns, a knowledge-graph extraction pipeline, multi-provider LLM routing, session management, a WebSocket event bus, pluggable parsers, structured export, and a Vue dashboard.
- **`apps/paper_review/`** — the first *application*: academic paper review. The kernel must never import from `apps.*` (enforced rule).
- **`ui/`** — Vue 3 + Vite frontend.

**Language:** Python `>=3.12,<3.13`; frontend JS (Vue 3). **License:** AGPL-3.0. Version 0.1.0.

**Key dependencies** (`pyproject.toml`): `fastapi`, `uvicorn`, `websockets`, `pydantic>=2`, `litellm>=1.50` (multi-provider LLM routing), `openai`, `httpx`, **`docling==2.96.0`** (IBM, MIT — layout-aware PDF parsing), `weasyprint` (PDF export), `pyyaml`, `markdown`, `charset-normalizer`/`chardet` (encoding detection), `curl-cffi`. Dev: `pytest`, `pytest-asyncio` (asyncio_mode=auto). Entry point script: `protoneo = "protoneo.cli:main"`. 245 tests, no network (LLM client mocked).

**The flow** (README "How It Works"): Upload PDF → Docling parser → Knowledge Graph (6-step pipeline) → Review Panel (technical/novelty/clarity/skeptic reviewers, multi-round deliberation) → Meta-Reviewer synthesis → Review Packet (Markdown/PDF).

---

## 2. Repo Structure

```
protoneo/                 # KERNEL (domain-agnostic; relative imports only)
  agents/      base.py, protocol.py, types.py        # BaseAgent, AgentProtocol, Message/AgentOutput/Document
  deliberation/ engine.py, patterns.py, session.py, types.py
  knowledge/   pipeline.py, ontology.py, graph.py, graph_extractor.py,
               graph_verifier.py, coref_resolver.py, metadata.py,
               visual_evidence.py, parser.py, processor.py, chunker.py, types.py
               parsers/ plaintext.py, markdown.py, docling_parser.py
  llm/         client.py, types.py, registry.py, settings.py, structured.py,
               model_catalog.py, models_dev.py, catalogs.py, discovery.py,
               benchmark.py, policies.py, errors.py
               providers/ oauth_base.py, anthropic_oauth.py, openai_oauth.py, registry.py
  tools/       types.py, web_search.py, semantic_scholar.py, graph_query.py
  config/      schema.py, __init__.py
  api/         app.py, routes.py, events.py, pipeline_control.py
  export/      types.py, json_exporter.py, markdown_exporter.py
  cli.py
apps/paper_review/        # APPLICATION (absolute imports from protoneo.*)
  manifest.py, pipeline.py, review.py, conference.py, prompts.py, schemas.py,
  exporters.py, export.py, api.py, preflight.py, review_context.py, web_context.py,
  context_audit.py, graph_usage.py
  domain/ config.yaml, seeds.yaml, domain_patterns.yaml, prompts/*.md
  profiles/ adaptive.profile.yaml ; prompts/adaptive/*.md
ui/                       # Vue 3 + Vite dashboard
tests/                    # 245 tests, mocked LLM, no network
docs/                     # kernel.md, building-apps.md, paper-review.md
run.py                    # dev launcher -> uvicorn on :5002
```

---

## 3. knowledge/ — The 6-Stage Extraction Pipeline

**Orchestrator:** `protoneo/knowledge/pipeline.py` → class `GraphPipeline`.
`KERNEL_STAGES = ["metadata", "ontology", "extraction", "coref", "verification", "summary"]`.
`GraphPipeline.run(session_id, document, bus, ctl, models, ...)` runs the stages. **The algorithm is kernel-owned; domain expertise is injected via `DomainConfig`** (`self.domain`). Each stage: (1) checks for an existing checkpoint and skips if present; (2) honors `PipelineControl` pause/resume gates; (3) runs; (4) snapshots the graph into `session.graph_after_step[<step>]`; (5) writes a `StageCheckpoint`; (6) emits a bus event. On resume, `KnowledgeGraph.restore_from_snapshot(...)` rebuilds from the last checkpoint's snapshot.

Stage → file mapping:

| Stage | File(s) | What it does |
|---|---|---|
| 1. Metadata | `metadata.py` | Heuristic (no LLM) extract of title, abstract, sections, figure/table/reference counts, citation markers, equation labels, per-section text. Also ingests visual + equation evidence. |
| 2. Ontology | `ontology.py` | Generate domain-specific entity/edge types from `DomainConfig` seeds + LLM discovery + grounding. |
| 3. Extraction | `graph_extractor.py` | Section-aware batched entity/relationship extraction into the `KnowledgeGraph`. |
| 4. Coref | `coref_resolver.py` | Merge duplicate entities; create `ALIAS_OF` edges for abbreviations. |
| 5. Verification | `graph_verifier.py` | 3-pass audit: connectivity, completeness, grounding. |
| 6. Summary | `graph.py` (`ensure_structural_links`, `prune_ungrounded`, `to_agent_briefing`) | Bridge structural links, prune low-confidence nodes, build agent briefing, persist final graph. |

Supporting modules: `parser.py`/`processor.py` (document ingestion), `parsers/` (PlainText/Markdown/Docling), `chunker.py` (fallback chunking), `visual_evidence.py` (VLM figure descriptions), `types.py` (Parser protocol, `DomainConfig`, seeds).

### The Knowledge Graph data model (`knowledge/graph.py`)

Pydantic `BaseModel`s. Core node/edge/annotation types verbatim:

```python
class GraphNode(BaseModel):
    """A node in the knowledge graph."""
    id: str = Field(default_factory=lambda: _uuid.uuid4().hex[:12])
    label: str
    node_type: str  # From ontology: "Method", "Dataset", "Claim", etc.
    description: str = ""
    source_section: str = ""
    source_text: str = ""
    confidence: float = 1.0
    attributes: dict[str, Any] = Field(default_factory=dict)
    annotations: list[GraphAnnotation] = Field(default_factory=list)

class GraphEdge(BaseModel):
    """A directed edge in the knowledge graph."""
    source_id: str
    target_id: str
    edge_type: str  # From ontology: "uses", "evaluates", "extends", etc.
    description: str = ""
    confidence: float = 1.0
    source_text: str = ""

class GraphAnnotation(BaseModel):
    """An annotation added by an agent or during deliberation."""
    agent_id: str
    annotation_type: str  # "strength", "weakness", "question", "consensus"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

`KnowledgeGraph(BaseModel)` holds `nodes: list[GraphNode]`, `edges: list[GraphEdge]`, `ontology: Ontology | None`, `summary`, `paper_title`, `paper_abstract`, `section_names`, and stats `node_count_by_type`/`edge_count_by_type`.

- **Node types** come from the ontology (semantic: `Claim`, `Method`, `Dataset`, `Metric`, `Baseline`, `Result`, `Limitation`, plus fallback `Concept`/`Reference`) and structural: `Paper`/`Document`, `Section`, `Figure`, `Table`, `Equation`.
- **Edge types** — base: `USES`, `EVALUATES_ON`, `COMPARED_AGAINST`, `ACHIEVES`, `EXTENDS`, `CITES`, `PART_OF`, `CONTRADICTS`; structural: `HAS_SECTION`, `CONTAINS`, `APPEARS_IN`, `ALIAS_OF`.
- **Confidence scores** — `float` on both nodes and edges (default 1.0). Verification pass updates them (`node.confidence = max(0.1, min(llm_conf, node.confidence))`); `prune_ungrounded(threshold=0.3)` drops nodes below the bar.
- **Storage / serialization** — Pydantic → JSON. `snapshot()` = `model_dump(mode="json")`; `restore_from_snapshot(data)` rebuilds. `to_d3_format()` emits `{nodes, edges}` for the D3 force-graph UI; `ingest_d3_data()` is the inverse. Final graph saved to `session.knowledge_graph` and to disk at `<storage>/graphs/{session_id}_graph.json`.
- Key methods: `add_node` (dedupes by case-insensitive (label, type), upgrades generic→specific types), `add_edge` (dedupes by src/tgt/type), `redirect_edges` (used in coref merge), `remove_node`, `ensure_structural_links` (adds missing `APPEARS_IN`), `prune_orphans`, `annotate_node`/`annotate_from_review` (agent feedback onto graph), `compute_utilization`, `get_accumulated_context` (entity+relationship summary fed into section-aware extraction), `to_agent_briefing` (markdown brief for reviewers).

### Stage internals

**`ontology.py`** — `Ontology`, `EntityType`, `EdgeType`, `OntologyAttribute` (all Pydantic). Entry: `async generate_ontology(text, llm_client, model="", session_id, conference_context, metadata, markdown, domain_config)`. 4 steps: (1) heuristic `_detect_domain()` keyword→domain (systems/ml/networking/iot/storage/theory); (2) `_discover_with_consistency()` — N=3 parallel LLM calls at temps 0.4/0.5/0.6, self-consistency keeps types in ≥2/3 samples; (3) `_ground_ontology()` (temp 0.15) — rejects types with <2 concrete named examples (anti-hallucination); (4) `_validate_ontology()` — merges base/fallback/structural, caps at 8 custom types. `ontology_to_extraction_prompt()` feeds the extractor.

**`graph_extractor.py`** — `ExtractedGraph`/`GraphEntity`/`GraphRelationship`. Entry: `async extract_graph(text, llm_client, ..., ontology, knowledge_graph, batch_size=4, models)`. Section-aware path: split into sections (LLM `_llm_section_split` if unstructured), subsplit on `###`, split oversized (>5.2K chars); process in **batches of `batch_size`** with each batch seeing accumulated context from prior batches; sections within a batch run in parallel via `asyncio.gather`, round-robin across multiple model endpoints; `_ingest_result` adds nodes + `APPEARS_IN`. `_validate_against_ontology` coerces mismatched types. Chunk-based fallback when no graph passed. Confidence comes from the node default (1.0) and is adjusted later by verification.

**`coref_resolver.py`** — `async resolve_coreferences(graph, llm_client, ...)`. Heuristic `_find_candidate_pairs` (Jaccard >0.3 / substring / acronym), then LLM in chunks of 40 deciding MERGE / ALIAS / DISTINCT, plus a global abbreviation pass. MERGE: redirect edges to keep-node and delete duplicate; ALIAS: create `ALIAS_OF` edge (no merge). Dedupes edges, removes self-loops.

**`graph_verifier.py`** — `VerificationResult` (grounding_issues, missing_concepts, missing_connections, confidence_updates, entities_added, entities_flagged). `async verify_graph(graph, paper_text, llm_client, ..., domain_config)`. 3 passes: (1) **Connectivity** (sequential) — find disconnected nodes/missing `APPEARS_IN`/isolated subgraphs and add edges; (2) **Completeness** (parallel) — scan full text for named entities missing from graph, add up to 15; (3) **Grounding** (parallel) — flag hallucinated entities, lower their confidence. Passes 2+3 run concurrently.

**`metadata.py`** — `DocumentMetadata` (title, abstract, sections, figure/table/reference counts, references, word count, citation_markers, equation_labels, `section_texts`, `section_texts_md`). All heuristic regex (no LLM). `extract_metadata(text)` and `extract_metadata_from_markdown(markdown, flat_text)` (prefers Docling markdown headers). `build_structural_graph()` for pure structure.

**`visual_evidence.py`** — `describe_image(image_path, vlm_config, kind, caption)` POSTs base64 data-URL image to an OpenAI-compatible VLM endpoint; `sanitize_description()` strips think tags; `extract_numeric_claims()` pulls numbers+units; confidence = `0.4 + 0.1*len(claims) + 0.2(if desc>80 chars)`.

**`chunker.py`** — `chunk_text(text, chunk_size=2000, overlap=200)` sentence-boundary-aware greedy splitting; `chunk_document(doc, ...)`.

---

## 4. Document Parsers (`knowledge/parser.py`, `processor.py`, `parsers/`)

**`DocumentProcessor`** (`processor.py`) is a parser registry with priority-based fallback: `register_parser(parser, priority)`, `register_post_processor(fn)`, `async process(path, preferred_parser=None) -> Document`. It builds a candidate list (preferred first, then by priority), tries each in order, applies post-processors to the result text, and raises if all fail. The `Parser` protocol (`knowledge/types.py`) requires `name`, `supported_extensions`, `available()`, `async parse(path, options) -> ParseResult`. `ParseResult` = `{text, markdown, figures_dir, metadata, figures}`.

Built-in parsers (`parsers/`):
- **`PlainTextParser`** (`.txt`/`.text`) — reads with charset detection (charset_normalizer → chardet).
- **`MarkdownParser`** (`.md`/`.markdown`) — reads as-is; sets both `text` and `markdown`.
- **`DoclingParser`** (`.pdf`/`.docx`/`.pptx`/`.html`) — IBM Docling layout-aware extraction: produces markdown with section hierarchy and tables, crops figures to `{stem}_figures/`, returns figures + metadata. `available()` checks the docling import.

**PDF / paper ingestion:** Docling is the primary path (the README diagram: "Docling Parser → layout analysis, table extraction, figure cropping, optional VLM figure descriptions"). `parser.py` adds post-processing: `_strip_line_number_pollution`, `_clean_markdown` (demote VLM headings, trim after References), `repair_formula_placeholders`, `_resolve_caption`. **VLM figure descriptions are inlined by Docling's `PictureDescriptionApiOptions`** during the single parse pass (no separate enrichment step — see CLAUDE.md gotcha), wired via `build_vlm_config()` in `llm/settings.py`. NOTE: `docs/kernel.md` lists `PyMuPDFParser`/`Pdf2MdParser` as the PDF parsers, but the actual code ships `DoclingParser`; CLAUDE.md explicitly forbids re-adding PyMuPDF. So the relationship to "paper-to-md" is: Docling *is* the PDF→markdown converter here.

---

## 5. agents/

- **`agents/protocol.py`** — `AgentProtocol` (runtime_checkable Protocol): properties `agent_id`, `role`, `model`, `system_prompt`; methods `async process(context, message) -> Message` and `async review(document) -> AgentOutput`. Also `SessionContext` protocol (read-only view: `session_id`, `messages`, `agent_outputs`, `documents`). Agents are described as *stateless callables*; state lives in `SessionContext`.
- **`agents/types.py`** — Pydantic types:
  - `Message{role, content, agent_id?, timestamp, metadata}`
  - `AgentOutput{agent_id, agent_role, content, structured?, metadata, timestamp}`
  - `Document{document_id, filename, text, markdown, chunks, metadata}`
  - `GroundingSource{source_type ('document'|'retrieval'|'tool'), source_id, config}`
- **`agents/base.py`** — `BaseAgent` (the concrete `AgentProtocol` impl, backed by `LLMClient`). Constructor signature:

```python
def __init__(self, role, model, system_prompt, llm_client,
             agent_id=None, focus="", max_tokens=4096,
             temperature=None, top_p=None, top_k=None, min_p=None,
             repeat_penalty=None, reasoning_effort=None, phase_policy=None,
             presence_penalty=None, frequency_penalty=None,
             tools: ToolRegistry | None = None):
```

  Key methods: `process()` and `process_stream(on_token=...)` (build OpenAI-format messages via `_build_messages`, which enforces strict user/assistant alternation for Qwen/LM-Studio jinja templates and merges consecutive same-role messages); `review(document, ...) -> AgentOutput`; `_inference_kwargs()` packs sampler controls (`top_k`/`min_p`/`repeat_penalty` go into `extra_body` for local OpenAI-compatible servers). Streaming strips thinking tags via `llm_client._strip_thinking`.

**Configuration** is via `config/schema.py::AgentConfig` (`role`, `model`, `system_prompt`, `focus`, `max_tokens`, `grounding`, all the sampler params, `reasoning_effort`, `phase_policy`). The engine converts each `AgentConfig` to a `BaseAgent` in `_create_agent`.

**Tools** — `BaseAgent` takes an optional `ToolRegistry`. `available_tools()` returns name/description pairs; `call_tool(name, query, **kwargs)` dispatches through the registry (raises if no tools attached). Tool use is **controlled, opt-in** — only agents constructed with a registry can call tools, and dispatch validates availability. It does *not* alter the default review/deliberation message flow (tools are out-of-band).

---

## 6. deliberation/

- **`engine.py` — `DeliberationEngine(llm_client, session_manager)`**. `async run(session_id, agent_configs, deliberation_config, user_message, on_event, stream)` → sets session RUNNING, builds agents, initializes context, dispatches on `config.pattern` via `_execute_pattern`: `"independent_synthesis"`→`_run_independent_synthesis`, `"sequential"`→`_run_sequential`, `"round_robin"`→`_run_round_robin`. Records total cost via `llm_client.session_cost(session_id)`. `_create_agent(id, config)` builds a `BaseAgent`.

- **`patterns.py` — the 4 patterns.** Each pattern's `execute(...)` returns a `PhaseResult`.
  - **`SequentialPattern`** — agents run in order; each sees prior outputs; output N → input N+1. Adds each response to `context` and extracts structured JSON via `_try_extract_json`.
  - **`ParallelPattern`** — all agents run concurrently (`asyncio.gather`, `include_history=False`, blind to each other); retries failed/empty agents once; collects `failed_agents`.
  - **`RoundRobinPattern`** — multi-round, agents take turns. `execute(agents, context, rules, on_event, stream, paper_context="")`. Builds a **self-contained prompt** per turn (`_build_deliberation_prompt`) with app source context, all Phase-1 reviews labeled YOUR/PEER, prior deliberation turns, and a score-diversity check — calls `process(include_history=False)` to avoid agreement bias from duplicated unlabeled history. Coerces stray full-review JSON into a "delta." Detects >90%-similar near-duplicate outputs.
  - **`IndependentSynthesisPattern`** — the primary product pattern, 3 phases. Verbatim docstring + variance logic:

```python
class IndependentSynthesisPattern:
    """
    The primary pattern for the PC Paper Reviewer product.

    Phase 1: All reviewer agents work in parallel (blind).
    Phase 2: Round-robin deliberation where reviewers see each other.
    Phase 3: A synthesizer agent produces the final output.
    """
    def __init__(self):
        self._parallel = ParallelPattern()
        self._round_robin = RoundRobinPattern()
        self._sequential = SequentialPattern()
```

  Phase 1 = `ParallelPattern.execute(reviewers, ...)`; aborts if all fail, continues on partial. **Variance-triggered depth (Phase 2):** parse merit scores from Phase-1 outputs (`_extract_merit_scores` reads `overall_merit.score`), `score_spread = max - min`:
    - `effective_rounds = max(2, rules.max_rounds)` when >1 reviewer (minimum 2-round PC panel).
    - spread ≤ 1.0 → consensus: **preserve** configured depth (policy `configured_preserved_low_score_spread`); emit `consensus_detected`.
    - spread ≥ 2.0 → contested: **deepen** to `min(max(effective_rounds, 3), 4)` (policy `deepened_high_score_spread`); emit `contested_detected`.
    - `1.0 < spread < 2.0` → configured depth.
  Runs `RoundRobinPattern.execute(..., paper_context=user_message.content)` with adjusted `DeliberationRules`. **Phase 3** = `SequentialPattern.execute([synthesizer], synthesis_prompt, ...)` where the synthesis prompt concatenates every prior output labeled `[role]` plus an `ORIGINAL SOURCE CONTEXT` block, explicitly instructing the synthesizer to fact-check and **preserve disagreements rather than flatten consensus**. Returns `DeliberationResult{session_id, phases, final_output, duration_seconds, metadata}` (metadata records `configured/effective_deliberation_rounds`, `deliberation_round_policy`, `score_spread`, `independent_review_scores`, `deliberation_stop_reason`).

- **`session.py`** —
  - `SessionContext(session_id)`: mutable in-memory state — `_messages`, `_agent_outputs: dict[agent_id, list[AgentOutput]]`, `_documents`, `_metadata`. Methods `add_message`, `add_output`, `add_document`; read-only property views. Passed by reference to all patterns/agents so each output is immediately visible downstream.
  - `SessionManager(storage_dir)`: persists `Session` records as JSON; `create`, `get`, `update`, `list_sessions`, and `get_context(session_id)` (returns/creates the in-memory `SessionContext`).
  - `Session(BaseModel)`: `session_id`, `status` (CREATED/RUNNING/COMPLETED/FAILED/STOPPED), timestamps, `result`, `error`, pipeline state — `current_stage`, `last_checkpoint`, `checkpoints: list[StageCheckpoint]`, `pipeline_steps`, `graph_after_step`, `knowledge_graph`, `config`, `app_data`.
  - `StageCheckpoint{stage_name, completed_at, output_key, idempotent=True}` + `StepState` (status/timing/model_used/nodes_added/edges_added/entities_flagged). Resume: pipeline checks `_has_checkpoint`, skips completed stages, restores graph from `graph_after_step[<key>]` snapshot.

- **`types.py`** — `DeliberationRules{max_rounds=3, timeout_seconds=600, visibility='open'|'blind'}`; `PhaseResult{phase_name, mode, outputs, messages, failed_agents, duration_seconds}`; `DeliberationResult{session_id, phases, final_output, total_cost, duration_seconds, completed_at, metadata}`.

---

## 7. config/ — DomainConfig & kernel/domain separation

The central separation-of-concerns mechanism is `knowledge/types.py::DomainConfig` (a dataclass) — "Domain expertise injected by an application into kernel knowledge modules. The kernel provides the algorithms. The application provides the prompts, seeds, and classification rules." Fields group into: ontology generation (`base_entity_types`, `base_edge_types`, `fallback_entity_types`, `structural_entity_types`, `structural_edge_types`, `domain_patterns`, `domain_keywords`, `ontology_discovery_prompt`, `ontology_grounding_prompt`), graph extraction (`extraction_system_prompt`, `extraction_batch_size`), verification (`verify_*_prompt`), and presentation (`structural_node_types`, `summary_template`, `summary_max_chars`). Seeds are `SeedEntity{name, description, attributes, examples}` and `SeedEdge{name, description, source_targets}`.

`config/schema.py` holds the runtime config and the app-extension contract:
- `ProtoNeoConfig{providers, agents, deliberation, storage}` with `from_env()`; `AgentConfig`, `PhaseConfig{name, mode, agents, max_rounds, visibility, input}`, `DeliberationConfig{pattern, phases}`, `LLMProviderConfig`, `StorageConfig`.
- **`AppManifest`** — the app↔kernel contract: `name`, `display_name`, `version`, `router: APIRouter` (mounted under `/api/apps/{name}/`), `on_register: Callable[[AppRegistration], None]`, `domain_config: DomainConfig`, `profile_dir`, `prompt_dir`, `result_schema`, `score_fields`, `pipeline_stages` (appended after kernel stages).
- **`AppRegistration`** — a *constrained* facade given to apps in their `on_register` callback: only `register_parser(parser, priority)`, `register_exporter(exporter)`, `register_tool(tool)`. Apps never touch raw framework internals.

So the kernel runs fixed algorithms (6-stage pipeline, 4 patterns); the paper-review app supplies all the domain knowledge through `DomainConfig` (its `domain/seeds.yaml`, `domain/domain_patterns.yaml`, `domain/prompts/*.md`) and registers parsers/exporters/tools/routes via the manifest.

---

## 8. Retrieval / Grounding / Selective Context Injection

- **`GroundingSource`** (`agents/types.py`) declares a source (`document`/`retrieval`/`tool`) an agent may ground against; `AgentConfig.grounding` carries the agent's grounding setting.
- **`KnowledgeGraph.get_accumulated_context()`** — produces a rich entity+relationship summary fed back into the extractor so each section/batch is extracted *with awareness of what's already in the graph* (incremental, deduplicating extraction). `to_agent_briefing()` produces the markdown brief reviewers receive.
- **Selective context injection in deliberation:** `RoundRobinPattern` deliberately calls agents with `include_history=False` and instead hand-builds a labeled, self-contained prompt (own review vs. peer reviews vs. prior deliberation turns). This is selective injection to prevent the agreement bias that raw history would cause. The synthesizer (Phase 3) additionally gets the `ORIGINAL SOURCE CONTEXT` block for fact-checking.
- **Tools as retrieval** (`tools/`): `web_search.py` (Brave / SearXNG / opt-in DuckDuckGo), `semantic_scholar.py` (S2 graph API: search/paper/citations/references), and **`graph_query.py`** — deterministic, LLM-free queries over the knowledge graph (`overview`, `claims_without_support`, `methods_evaluation`, `baselines`, `claim_evidence`, `section_coverage`, `entity`). The `Tool` protocol (`tools/types.py`): `name`, `description`, `available()`, `async execute(query, **kwargs) -> ToolResult{data, source, cached}`; `ToolRegistry.dispatch(name, query, **kwargs)` with availability validation.

---

## 9. CLI / Entry Points

- **`protoneo/cli.py::main()`** (the `protoneo` console script). argparse flags `--host` (0.0.0.0), `--port` (5002), `--reload`, repeatable `--app MODULE:ATTR` (also `PROTONEO_APPS` env, comma-separated). `_load_app_manifest` imports `module:attribute` and asserts it's an `AppManifest`; builds `ProtoNeoConfig.from_env()`; `create_app(config, apps=...)` (from `api/app.py`); runs uvicorn. The CLI itself never imports `apps.*` — apps are passed by manifest spec.
- **`run.py`** — dev launcher: builds config, `create_app(config, apps=[paper_review_manifest])`, `uvicorn.run(..., port=5002)`.
- The FastAPI app (`api/`) exposes session/graph/pipeline/export/settings/providers routes (full list in `docs/kernel.md`) plus a WebSocket event bus (`SessionEventBus` in `api/events.py`) emitting `step_started`, `graph_updated`, `ontology_ready`, `agent_streaming`, `stage_complete`, `consensus_detected`, `contested_detected`, etc. `api/pipeline_control.py::PipelineControl` provides pause/resume/cancel gating consumed by `GraphPipeline`.

### LLM layer note (Claude/Anthropic)
`llm/client.py` routes via **LiteLLM** for API-key providers (Ollama, LM Studio, OpenRouter, OpenAI) and via **direct HTTP** for OpenAI ChatGPT/Codex OAuth (`https://chatgpt.com/backend-api/codex/responses`). An **Anthropic "Claude Max" OAuth provider exists but is currently disabled** (`llm/providers/anthropic_oauth.py`, commented out in `client.py` and `providers/registry.py`). Its hardcoded constants: authorize `https://claude.ai/oauth/authorize`, token `https://platform.claude.com/v1/oauth/token`, redirect `https://platform.claude.com/oauth/code/callback`, client id `9d1c250a-e61b-44d9-88ed-5944d1962f5e`, scopes include `user:inference`/`user:sessions:claude_code`, 5-min refresh buffer. No hardcoded Claude *model ids* — model ids come from discovery/registry. OAuth tokens stored at `~/.protoneo/tokens/{provider}.json` (chmod 600) with PKCE. Sampler/`reasoning_effort` controls flow per-agent; local servers get `top_k`/`min_p`/`repeat_penalty` via `extra_body`.

---

## Reusable for clio-parser

- **6-stage KG pipeline is the headline reusable asset** (`knowledge/pipeline.py` + the per-stage modules). The metadata→ontology→extraction→coref→verify→summary decomposition, with **per-stage checkpoints + snapshot resume**, is directly applicable to a parser/extractor harness. Note the durability pattern: snapshot graph into `session.graph_after_step[step]`, write `StageCheckpoint`, skip-on-resume.
- **kernel/domain separation via `DomainConfig` + `AppManifest`/`AppRegistration`** is a clean template: keep generic extraction algorithms in a kernel, inject all prompts/seeds/keywords/classification through a single config object; apps register parsers/exporters/tools through a constrained facade and never import kernel internals. This is exactly the "expert-agent harness" shape.
- **Anti-hallucination grounding techniques worth lifting:** ontology grounding rejects entity types with <2 concrete examples; self-consistency over N parallel samples (≥2/3 vote); 3-pass verifier (connectivity/completeness/grounding) that adds missing entities and lowers confidence on ungrounded ones; `prune_ungrounded(0.3)`. Confidence is a first-class float on every node/edge.
- **Pydantic-everywhere → JSON** node/edge model with `snapshot()`/`restore_from_snapshot()`/`to_d3_format()` is a simple, copyable serialization story.
- **`graph_query.py`** — deterministic, LLM-free graph queries — is a clean retrieval-tool design (typed query verbs over the parsed structure).
- **Parser registry with priority fallback** (`DocumentProcessor`) + the thin `Parser` protocol is a good ingestion abstraction; Docling is the PDF→markdown engine of choice here (with inline VLM figure captioning).
- **Selective-context injection** pattern (build labeled self-contained prompts, `include_history=False`) is a reusable trick to control bias/redundancy when feeding accumulated state to an LLM.
- **`structured.py`** thinking-tag stripping + best-effort JSON salvage (`extract_json_object`, brace-matching, truncation salvage) is robust LLM-output parsing worth reusing for any "parse the model's JSON" need.

## Open Questions

- **Docs vs. code drift on parsers:** `docs/kernel.md` advertises `PyMuPDFParser`/`Pdf2MdParser`; the code ships `DoclingParser` and CLAUDE.md bans PyMuPDF. Which is canonical for clio-parser's ingestion comparison? (Code wins, but worth flagging.)
- **`get_accumulated_context` location:** the prompt expected it on the session; it actually lives on `KnowledgeGraph` (graph-level context for extraction), while deliberation state accumulation is via `SessionContext.add_*`. Confirm which "accumulated context" matters for clio-parser.
- **Anthropic provider disabled** — is the intent to re-enable Claude routing, or has the project standardized on OpenAI/local? The full Claude Max OAuth impl is present but dead-code.
- I did not deep-read `apps/paper_review/*` internals, the `api/` route handlers, the Vue UI, or `llm/benchmark.py`/`discovery.py`/`policies.py` — only the kernel surfaces the task named. The paper-review `domain/` YAMLs and `prompts/adaptive/*.md` are the concrete `DomainConfig` payloads if a worked example is needed.
- `extraction_batch_size` default differs: `DomainConfig` says 3, `extract_graph`/pipeline default 4. Minor, but note the effective value is the pipeline's `extraction_batch_size=4`.

# CLIO Agent — Deep-Study Notes (integration target for clio-parser)

Repo studied: `/home/shazzadul/Illinois_Tech/Summer26/RA/clio-parser/artifact/repos/clio`
Branch: `develop` (HEAD = `475a8a3 Bundle GACT TUI for CLIO releases`). Read-only; nothing modified.

> Bottom line up front: CLIO has **no privileged Python "expert" classes anymore**. Experts and their tools are loaded from **file-backed Agent Blueprints** (`AGENT.md` + `experts/*.md` Markdown-with-frontmatter), and all domain tools are **declared MCP servers** mounted into a FastMCP gateway. To add PDF/paper capability you author an Agent Blueprint + an MCP server (or a marketplace pack) — you do **not** edit core Python. This is the single most important fact for the integration.

---

## 1. What CLIO is

- **CLIO Agent** = "Cognitive Layer for Adaptive Universal Data & Intelligent Operations." An autonomous agent for **scientific data management** (HDF5/Parquet/CSV inspection, I/O reasoning) in HPC contexts. It is the **Intelligence Layer (CEI)** of the IOWarp platform (https://iowarp.org). `README.md` L14-27; `CLIO_VISION.md` L9.
- **Explicitly "not a framework — it IS the agent."** `CLIO_VISION.md` L9; `docs/tui/01-overview.md` L9.
- **Packaging:** `pyproject.toml` L5-11 — published as PyPI package `clio-agent` (namespace `iowarp`). BSD-3-Clause.
- **Tech stack / language:** Python **>=3.12** (locked), managed by **uv**. Package name `clio-agent`, import root `clio_agent`. Version `0.5.1`.
- **Core dependencies** (`pyproject.toml` L37-53):
  - `dspy>=3.1.3` — the **internal** LM-programming engine (signatures, modules `Predict`/`ChainOfThought`/`ReAct`, optimizers like SIMBA). DSPy is an implementation detail, never user-facing (`.claude/CLAUDE.md` RULE 3).
  - `fastmcp>=3.2.4` — MCP protocol + tool gateway (mount/proxy composition).
  - `fastapi`, `uvicorn`, `sse-starlette` — the **GACT** backend server (shipped product surface).
  - `h5py`, `pyarrow`, `matplotlib` — built-in scientific file handling.
  - `rich`, `prompt-toolkit` — CLI TUI.
  - `sortedcontainers`, `lru-dict`, `msgspec` — ARC memory internals (B-tree index, LRU cache, serialization).
  - Optional extras: `optimizers` (scipy/numpy), `adios` (adios2), `codex`, `iowarp` (pyzmq), `argonne` (globus-sdk).
- **LM providers:** LM Studio, Ollama, OpenAI, Anthropic, OpenRouter, OpenAI Codex, Argonne ALCF gateway. Provider glue under `src/clio_agent/providers/` (`registry.py`, `claude_code_litellm.py`, `codex_litellm.py`, `argonne_auth.py`).

---

## 2. Repo structure (top level)

| Path | Holds |
|---|---|
| `src/clio_agent/` | All production code (see §3). |
| `tests/` | Mirrors runtime layout: `test_core/`, `test_arc/`, `test_tools/`, `test_gact/` (largest — ~60 files), `test_experts/`, `test_providers/`, `test_real_cases/`, `test_stress_benchmark/`. |
| `docs/` | Architecture + design docs (~70 files). `docs/tui/` = the gact-tui integration spec (9 numbered docs). |
| `ai-docs/` | Reference material (DSPy source mirror `docs/ref/dspy/`, FastMCP refs). |
| `external/` | **Git submodules** (not checked out in this clone): `gact-tui` (the Go/Bubbletea TUI) and `clio-agent-marketplace` (the default Agent Blueprint registry). `.gitmodules`. |
| `benchmark/` | NDP/EarthScope/genomics benchmark "cases" with `GOAL.md`/`prompt.txt`. |
| `install/` | `clio` launcher CLI (bash/powershell): `clio start|stop|status|doctor|...`. |
| `scripts/` | demo data, benchmark runners, `build_clio_tui.sh`. |
| `docker/` | Separate images for `clio-web`, `clio-tui`, `clio-api`. |
| `.claude/CLAUDE.md` | **Extremely informative** dev rule file — read it; documents the 3-tier + ARC + optimizer + IOWarp design, DSPy/FastMCP patterns, and "superseding principles." |
| `pyproject.toml`, `uv.lock` | Manifests. `AGENTS.md`, `PLAN.md`, `TASK.md`, `CLIO_VISION.md`, `CHANGELOG.md` | Project docs. |

### `src/clio_agent/` modules

- `agent.py` — **Tier-1 `ClioAgent`** main orchestrator (planner loop). ~3700 lines.
- `harness.py` — `RunTrace`, `RouteDecision`, `ToolObservation`, tool-result normalization/compaction, file-path extraction.
- `config.py` / `conf.py` — multi-provider LM config + persisted settings.
- `conversation_manager.py`, `errors.py` (structured `ClioError`/`RoutingError`/`ToolError`/`ExpertError`/etc).
- `signatures/main_agent_sig.py` — DSPy signatures: `AgentActionSignature`, `AgentAnswerSignature`, `ChatAgentSignature`.
- `registry/registry.py` — `AgentRegistry` + `AgentCapability` (thread-safe agent discovery; **discovery, not routing** — model is the router).
- `registry/capability_matcher.py` — keyword/capability matching.
- `arc/` — ARC memory (`memory.py`, `cache.py` LRU, `index.py` B-tree, `lsm.py` LSM-tree metrics, `storage.py`, `retrieval.py`, `context_compiler.py`, `coordinator.py`, `schema.py`, `live.py`).
- `tools/` — `gateway.py` (FastMCP mount/proxy), `mcp_config.py` (declared-server parsing), `catalog.py` (tool ownership/visibility), `execution.py` (sync executor boundary + `to_dspy_tools`), `file_policy.py`, `fs_write.py`, and `servers/` (only `fs_server.py` + `shell_server.py` — HDF5/Parquet are now external marketplace MCPs).
- `gact/` — **the GACT v0.2 FastAPI server** (`app.py` is ~22.5k lines!). Contains the live agent runtime, blueprint compilation, sessions, MCP handshake, permissions, memory endpoints. Also `agent_blueprints.py`, `expert_packs.py`, `user_agents.py`, `workspaces.py`, `sessions.py`, `events.py`, `semantic_events.py`, `scheduler.py`, `types.py`.
- `runtime/` — `nanoagent.py` (Tier-3 spawn primitive), `hooks.py`, `status.py` (doctor), `trace.py`, `lm_activity.py`.
- `optimizer/` — `instrumentation.py`, `trainer.py` (SIMBA), `variants.py`, `runner.py`.
- `prompt_packs/builtin/` — Markdown system prompts (`clio.main.planner.md`, `clio.chat.md`, `clio.expert.*.md`, profiles `light/heavy/small_model/...`).
- `agent_blueprints/builtin/` — **retired** in-repo blueprint root (only `__init__.py`; kept for migration diagnostics, NOT used at runtime — see `agent_blueprints.builtin_agent_blueprints_root()`).
- `providers/` — provider auth + litellm bridges.
- `ui/cli.py` (Rich REPL + `doctor`), `ui/api.py` (legacy REST).

---

## 3. Agent architecture + entry points

**Three tiers** (`README.md` L18, `docs/tui/01-overview.md` L19-39):
- **Tier 1 — `ClioAgent`** (`src/clio_agent/agent.py`): the main orchestrator. A **planner loop** (NOT a hardcoded router). It calls the DSPy `action_planner` (`dspy.Predict(AgentActionSignature)`) which emits a JSON action `{action: tool|expert|answer|none, ...}`. The loop (`_run_agent_loop`, agent.py L562-1004) executes tools, delegates to experts, or answers, up to `DEFAULT_AGENT_MAX_STEPS = 8`. The **model is the router/decider**, not keyword heuristics (`.claude/CLAUDE.md` superseding principle #1).
- **Tier 2 — Experts**: registry-loaded **Agent Blueprint** nodes compiled to a DSPy module at runtime (see §4). Native Python experts (`DataExpert`, etc.) were **removed** (`docs/DSPY_BLUEPRINT_EXPERT_RUNTIME.md` L196-200; `agent.py::_dispatch_expert_action` L1385-1424 now *rejects* native dispatch).
- **Tier 3 — child experts / nanoagents**: declared by the blueprint graph, invoked via bounded runtime primitives (synchronous child-delegation tools + `fanout`). `runtime/nanoagent.py`; GACT `_build_child_expert_tool` / `_build_fanout_tool` (app.py L5055, L5196).

**Entry points** (`pyproject.toml` L111-117):
- `clio-agent = clio_agent.ui.cli:run_cli` — interactive Rich CLI / `doctor`.
- `clio-agent-api = clio_agent.ui.api:main` — legacy REST (`/health`, `/query`, `/experts`, `/metrics`, `/doctor`).
- `clio-agent-gact = clio_agent.gact.app:main` — **the GACT server**, the real product surface the TUI talks to (FastAPI factory `create_app()` at app.py L12157+, `main()` runs uvicorn).
- Shipped UX: the `install/clio` launcher boots the GACT server and attaches the `gact-tui` binary (`README.md` L55-70).

**Request flow:** user query -> ARC context retrieval -> planner action -> tool call (FastMCP, ARC-cached) / expert delegation -> answer synthesis -> store conversation/metrics/routing in ARC. `agent.py::forward` L388-560.

---

## 4. EXTENSION MODEL — Agent Blueprints (THE KEY SECTION)

### 4.1 What a "subagent/expert" is and where it comes from

Experts are **file-backed Agent Blueprints**, not code. The canonical loader is
`src/clio_agent/gact/agent_blueprints.py`. A **blueprint** is a directory whose root file is **`AGENT.md`** (Markdown + YAML frontmatter). Experts inside it are Markdown files with frontmatter parsed by `src/clio_agent/gact/expert_packs.py::parse_expert_file`.

**Discovery roots** (`agent_blueprints.py::agent_blueprint_roots` L69-76):
- Global: `$XDG_CONFIG_HOME/clio-agent/agent-blueprints/` (default `~/.config/clio-agent/agent-blueprints/`)
- Workspace: `<cwd>/.clio/agent-blueprints/`

`discover_agent_blueprints()` (L117) walks both roots; each subdir containing `AGENT.md` becomes an `AgentBlueprintDefinition`. On first run, `ensure_default_registry_bootstrap()` (L164) **git-clones the pinned marketplace** (`DEFAULT_REGISTRY_URL = git@github.com:JaimeCernuda/clio-agent-marketplace.git`, default blueprint id **`data-semantics`**, L36-41) into the global root unless `CLIO_AGENT_DISABLE_DEFAULT_REGISTRY_BOOTSTRAP=1`.

### 4.2 Loading / compiling / invoking

- `load_agent_blueprints()` (L303) -> `_load_blueprint_agents()` (L915): globs `experts/*.md` (and declared `includes`), skipping `prompts/`, `commands/`, `skills/`, `tools/`, `profiles/`. Each file becomes an **`AgentDef`** (`gact/types.py`) via `parse_expert_file`.
- **Expert frontmatter schema** (`expert_packs.py::parse_expert_file` L204-329): `id`, `title`, `description`, `parent_id`, `tier`, `keywords`/`tags`, `tools` (allowed tool names), `skills`, `commands`, `prompt_id`, `prompt_profile`, `provider`, `model`, `module` (`{kind: predict|chain_of_thought|react}`), `signature` (typed `inputs`/`outputs`), `structured_outputs`, `fanout`, `capability_refs`, `param_*`. The body after frontmatter is the **system prompt**.
- **Compilation to DSPy** happens in GACT: `gact/app.py::_build_blueprint_dspy_module` (L5448) builds a `BlueprintExpertModule(dspy.Module)`:
  - `module.kind` -> `dspy.Predict` (L5465) / `dspy.ChainOfThought` (L5467) / `dspy.ReAct` (L5474, a `_RetainingReAct`).
  - For ReAct, tools = `_dynamic_agent_tools(...)` + `_dynamic_child_expert_tools(...)` (L5469-5472).
  - `docs/DSPY_BLUEPRINT_EXPERT_RUNTIME.md` is the contract spec.
- **Child experts (Tier 3):** every declared parent-child edge can expose a generated internal tool like `delegate_to_<child>` that runs the child synchronously (`_build_child_expert_tool`, app.py L5055). `fanout` (`_build_fanout_tool` L5196) is the bounded parallel worker primitive.

### 4.3 Registry — discovery vs routing

`registry/registry.py::AgentRegistry` is **thread-safe register/unregister/get/list/find_agents_by_keyword/route_query**. Per `.claude/CLAUDE.md` superseding principle #1, the registry is used for **discovery only**; the LM decides routing via structured output. Core registers exactly one Python agent at startup — `"utility"` (shell_bash + fs_propose_edit), `agent.py` L276-289. Everything else is blueprint-loaded.

### 4.4 How to ADD a new subagent or tool (the recipe)

To add a **new expert/subagent**:
1. Create a blueprint dir with `AGENT.md` (frontmatter: `id`, `version`, `title`, `root_expert`, optional `mcp_servers:` map, `includes`) under `~/.config/clio-agent/agent-blueprints/<id>/` (global) or `<cwd>/.clio/agent-blueprints/<id>/` (workspace).
2. Add `experts/<name>.md` files (frontmatter `id`/`parent_id`/`tier`/`module.kind`/`tools`/`signature` + system-prompt body).
3. (For tools) declare MCP servers in `AGENT.md` frontmatter `mcp_servers:` (see §5) and list their tool names in each expert's `tools:`.
4. Programmatic install: `agent_blueprints.install_agent_blueprint(source=<git-or-path>, scope="global"|"workspace", ...)` (L701) — copies into the install root and writes `.clio-install.md` provenance. Also `update_installed_agent_blueprint` (L821), `uninstall_agent_blueprint` (L843).
5. Over REST, the GACT app exposes blueprint endpoints (app.py imports `install_agent_blueprint`/`load_agent_blueprints` at L11837) plus `/v1/agents/extract` (L16800) to harvest a user agent from past sessions, and a user-agent store (`gact/user_agents.py`).
6. Validation: `validate_agent_blueprint_path` (L317) returns enabled/errors; invalid files become **disabled `AgentDef` rows with `validation_errors`** (never silently dropped). Tool refs are validated in `_validate_agent_tool_references` (L488): built-ins (`TOOL_CATALOG` + memory tools) pass; declared-MCP namespaces pass iff declared in `mcp_servers`; legacy `tools/*.md` descriptors are **disabled until explicitly enabled/trusted**.

**Also extensible per blueprint:** `tools/*.md` (disabled MCP descriptors, `load_mcp_descriptors` L559), `hooks/*.py` (lifecycle hooks for events `pre_tool`/`post_tool`/`pre_message`/`post_message`/`semantic_event`/`on_error`; disabled until trusted, `load_hook_descriptors` L654), `prompts/`, `commands/`, `skills/` subdirs (referenced from frontmatter). Hooks doc: `docs/AGENT_BLUEPRINT_PACKAGED_HOOKS.md`.

**Legacy path still supported:** `clio-pack.yaml` "Expert Packs" (`expert_packs.py::discover_expert_packs`, roots `~/.config/clio-agent/expert-packs/` + `.clio/expert-packs/`, plus loose `experts/` dirs). The newer `AGENT.md` blueprint loader wraps/adapts this.

---

## 5. Tool system

- **Core ships only universal in-process built-ins:** `fs` and `shell` FastMCP servers (`tools/servers/fs_server.py`, `shell_server.py`). Mounted by `gateway.py::_mount_builtins` (L47) under namespaces `fs`/`shell` (also reserved: `web`). The static base catalog lives in `tools/catalog.py::TOOL_CATALOG` — only `shell_bash`, `fs_propose_edit`, `fs_read_file`, `fs_apply_edit_write`.
- **Every domain tool is a declared MCP server** (HDF5/Parquet/NDP/etc. now come from the marketplace, NOT core). Declared via `mcp_servers:` frontmatter in `AGENT.md`, or user/workspace `mcp.yaml`. Parsed by `tools/mcp_config.py` into `MCPServerSpec` (string command -> stdio, or http(s) URL; `${VAR}` expansion supported). `transport_for()` (L325) builds the FastMCP `StdioTransport`/URL; for stdio it pins `CLIO_KIT_ARTIFACTS=<workspace>` and spawns with `cwd=<workspace>`.
- **Gateway composition:** `tools/gateway.py::build_gateway` (L107) proxy-mounts each declared spec next to the built-ins under its name as namespace, yielding `<namespace>_<tool>` names (lazy `FastMCP.as_proxy(Client(transport_for(spec)))` — no subprocess until first call; unreachable server just yields an empty namespace).
- **Runtime catalog derivation:** `build_tool_catalog` (L251) enumerates connected gateway tools and synthesizes `ToolCatalogEntry`(owner=namespace, tags, `visible_to`). **Visibility = which experts list the tool in `tools:`** (`_expert_visibility` L227); planner sees a tool iff a planner-visible expert lists it. `set_active_catalog()` installs it process-wide; accessors `tool_owner`/`tool_visible_to`/`tool_names_for_owner` read it.
- **Execution boundary:** `tools/execution.py` — `create_sync_tool_executor(gateway)` returns the sync executor (`ToolExecutor`) with `.call_tool(name, args)` and `.to_dspy_tools()` (bridges MCP tools to `dspy.Tool` via `dspy.Tool.from_mcp_tool`). The agent resolves a **per-workspace** executor (`agent.py::_active_tool_executor` L355). `experts/native_tools.py::NativeToolRunner` records provenance.
- **Tool design rules** (`.claude/CLAUDE.md` RULE 5, `docs/MCP_TOOL_INTEGRATION.md`): max 5-7 curated composite tools per expert, each with an "Agent Story" docstring; no auto-generation.

---

## 6. Memory / context model (ARC)

- **ARC = Adaptive Retrieval Cache** (`src/clio_agent/arc/`, doc `docs/ARC_MEMORY_LAYER.md`). `ARCMemory` (`arc/memory.py`) = LRU cache (hot, O(1), `cache.py`) + B-tree index (search, O(log N), `index.py`) + LSM-tree (write-heavy metrics, `lsm.py`) over a pluggable `ARCStore` (`storage.py`, default `LocalFSStore`; seam for an IOWarp CTE backend). Rooted at `<data_dir>/arc`.
- **Record kinds** (`arc/schema.py`, msgspec-encoded): `Conversation`, `Invocation`, `Metrics`, `Context`, `DatasetProfile`, `ProceduralMemory` (what worked/failed before), `VariantRecord`, plus `RoutingDecision`, `NanoagentSpawn`.
- **Context is COMPILED, not concatenated** (`.claude/CLAUDE.md` RULE 6): `arc/context_compiler.py` filter -> compact -> enrich -> assemble into bracketed sections (`[Available Tools]`, `[Available Data]`, `[Retained session context]`, ...). `arc/retrieval.py::ContextRetriever`. The agent strips sections per scope (`agent.py::_strip_context_sections` L1264).
- **No embeddings / vector store in core.** Retrieval is B-tree + keyword + procedural memory, not semantic embeddings. (Note: this clone's *outer* harness exposes `processor`/`rag` skills, but those are NOT part of CLIO core.)
- **Memory tools** exposed to blueprints: `memory_search_sessions`, `memory_read_session_summary`, `memory_read_context_frame` (`agent_blueprints.py::_MEMORY_TOOL_NAMES` L412; wired in app.py L18106). Cross-session search doc: `docs/CROSS_SESSION_MEMORY_SEARCH.md`.
- **GACT memory/context endpoints:** `/v1/sessions/{sid}/context/frames`, `/context/files` (file mention attachments), `/memory/events`, `/compact`. Context-file lifecycle docs: `docs/SESSION_CONTEXT_ATTACHMENT_LIFECYCLE.md`, `docs/FILE_MENTION_CONTEXT_ATTACHMENTS.md`.

---

## 7. Existing PDF / document / paper handling

**Essentially none.** Grep for `pdf`/`arxiv`/`docling`/`pymupdf`/`paper review` across `src` + `docs`:
- `tools/execution.py` L768 — `.pdf` appears only in `_ARTIFACT_SUFFIXES` (a list recognizing output-artifact file types for provenance; alongside `.png`, `.csv`, `.md`, ...). No parsing.
- `docs/EXPERT_SYSTEM_DESIGN.md` L74-81 describes a **planned (never-built) "ResearchExpert"** (search_papers / analyze_schema / extract_context) — historical design note, explicitly predates #629 and was never implemented; native experts were removed.
- No PDF text extraction, no bibliography/citation handling, no paper read/write/edit tools anywhere in core. **This is a green field — the integration adds net-new capability.**

The closest reusable substrate: `fs_read_file` / `fs_apply_edit_write` / `fs_propose_edit` built-ins (read/edit text files, with diff proposals surfaced as `file_diffs`).

---

## 8. MCP support

CLIO is **both an MCP client and (potentially) an MCP server** (`docs/tui/05-tools.md` L61-71):
- **Client (primary):** the gateway proxies declared MCP servers; experts consume them as `dspy.Tool`s via `to_dspy_tools()`. Stdio + http(s) transports (`mcp_config.transport_for`).
- **Server:** the `gateway` FastMCP object can itself be served (in-memory for tests; stdio; `gateway.http_app()` over uvicorn) — not exposed by default.
- **GACT REST MCP management:** `GET/POST /v1/mcp/servers`, `/v1/mcp/handshake`, `/v1/mcp/servers/{sid}/call|tools|resources|prompts`, `DELETE /v1/mcp/servers/{sid}` (app.py L15580-16622). Handshake tests in `tests/test_gact/test_mcp_handshake.py`, `tests/test_providers/test_handshake_*`.
- **Declared-server config precedence** (`mcp_config.load_mcp_servers` L293): workspace `.clio/mcp.yaml` > user `~/.config/clio-agent/mcp.yaml` > pack `AGENT.md` frontmatter > built-ins.

---

## 9. Config and settings format

- **LM provider via env** (`config.py`, `docs/tui/07-providers-config.md`): `CLIO_LM_PROVIDER`, `CLIO_LM_API_BASE`, `CLIO_LM_MODEL`, `CLIO_LM_API_KEY`/`CLIO_LM_ENDPOINT`. `load_config_from_env()`.
- **File access policy** (`tools/file_policy.py`): `CLIO_ALLOWED_ROOTS` (colon-separated; default cwd in dev / `/tmp` in prod), `CLIO_MAX_FILE_SIZE_BYTES`, `CLIO_ALLOW_SYMLINKS`. Doc `docs/PERMISSIONS.md`.
- **Runtime knobs:** `CLIO_ENVIRONMENT`, `CLIO_ARC_BACKEND` (local|cte), `CLIO_LOG_LEVEL`, `CLIO_PORT`, `CLIO_PREFIX`/`CLIO_BIN_DIR`, `CLIO_LM_DISABLE_THINKING`, `CLIO_KIT_ARTIFACTS`, `CLIO_AGENT_DISABLE_DEFAULT_REGISTRY_BOOTSTRAP`.
- **Persisted config:** `conf.py` (settings/migrations; tests `test_conf*.py`). Config home `~/.config/clio-agent/`.
- **Per-blueprint config:** YAML frontmatter in `AGENT.md`/expert `.md`; `mcp.yaml` for MCP servers; `.clio-install.md` for install provenance.

---

## 10. What "GACT TUI" is (HEAD commit "Bundle GACT TUI for CLIO releases")

- **GACT** = the terminal UI client for CLIO, an **external repo** (`https://github.com/iowarp/gact-tui`, submodule `external/gact-tui`), referenced in README as "a Bubbletea terminal UI." It is a **Go/Bubbletea TUI binary** that the `clio` launcher downloads/bundles per platform.
- **GACT also names the server-side surface** it talks to: `src/clio_agent/gact/` — the FastAPI app (`gact/app.py`, entry `clio-agent-gact`) exposing the `/v1/*` API the TUI drives (sessions, streaming SSE, agents/blueprints, MCP, permissions, diffs, memory, providers). Spec: `docs/tui/` (esp. `06-endpoints.md`, `09-integration-plan.md`).
- The HEAD commit bundles the prebuilt TUI binary into CLIO releases (`scripts/build_clio_tui.sh`, `.github/workflows/clio-bundles.yml`, `docker/Dockerfile.clio-tui`).
- "GACT" likely = Generic/Graphical Agent Control Terminal (acronym not spelled out in repo). Tests for the server side: `tests/test_gact/` (~60 files — the richest test area).

---

## 11. Cleanest attachment points for a PDF subagent + paper read/write/edit tools

Given the architecture, **the integration should be additive via the blueprint + MCP model, not core edits.** Concretely:

1. **PDF/paper tools = a new declared MCP server.** Write a FastMCP server (e.g. `paper`/`pdf` namespace) exposing curated tools like `pdf_extract_text`, `pdf_outline`, `paper_read_section`, `paper_propose_edit`, `paper_write`. Mount it by declaring it in a blueprint's `AGENT.md` `mcp_servers:` (string command form, e.g. `paper: uvx clio-paper-mcp`) or in user/workspace `mcp.yaml`. It will auto-namespace to `paper_*` and flow through `build_gateway` / `build_tool_catalog` with zero core changes. Pattern reference: `docs/MCP_TOOL_INTEGRATION.md`.
2. **PDF subagent = a new Agent Blueprint expert.** Add `experts/paper_review.md` (and children like `paper_writer`, `citation_checker`) inside a blueprint dir. Set `module.kind: react`, list the `paper_*` + `fs_*` tools, write a strong system-prompt body, declare `parent_id`/`children` for delegation. Install via `install_agent_blueprint(source=..., scope=...)` or drop into `<cwd>/.clio/agent-blueprints/`. The GACT runtime compiles it to `dspy.ReAct` automatically (`_build_blueprint_dspy_module`).
3. **Edit surface already exists:** reuse the built-in `fs_propose_edit` / `fs_apply_edit_write` so paper edits surface as GACT `file_diffs` (rendered/approved in the TUI) — `agent.py::_file_diffs_from_trace` L1620.
4. **For paper-context retrieval:** attach PDFs/markdown via the **context-files** endpoint (`POST /v1/sessions/{sid}/context/files`) and/or store extracted text as ARC `DatasetProfile`/`Context` records so it's compiled into prompts. If semantic retrieval over papers is wanted, it must be added (core has no embeddings) — cleanest as an MCP `rag_search` tool or a CTE-backed `ARCStore`.
5. **Lifecycle hooks** (`hooks/*.py` in a blueprint) can post-process tool output (e.g., auto-extract citations on `post_tool`) once enabled/trusted — `docs/AGENT_BLUEPRINT_PACKAGED_HOOKS.md`.
6. **Avoid:** editing `agent.py` routing, adding native Python expert classes, or hardcoding tools in `catalog.py` — all of these violate the documented design (`.claude/CLAUDE.md` RULES 1, 5; native-expert-removal in `DSPY_BLUEPRINT_EXPERT_RUNTIME.md`).

**Single best attachment point:** ship a **marketplace-style Agent Blueprint** (its own dir with `AGENT.md` + `experts/*.md` + a `paper` MCP server declared in `mcp_servers:`), installable into the global/workspace blueprint store. That is the idiomatic, zero-core-patch extension.

---

## Reusable for clio-parser

- **Agent Blueprint format** (`AGENT.md` frontmatter + `experts/*.md`) is the entire extension contract — author PDF experts as Markdown, no Python core changes. Loader: `gact/agent_blueprints.py`; expert schema: `gact/expert_packs.py::parse_expert_file`; DSPy compile: `gact/app.py::_build_blueprint_dspy_module`.
- **Declared-MCP tool model** (`tools/mcp_config.py` + `tools/gateway.py`): a PDF/paper MCP server plugs in via a one-line `mcp_servers:` declaration; visibility is per-expert via `tools:`.
- **Built-in fs tools** (`fs_read_file`/`fs_apply_edit_write`/`fs_propose_edit`) + GACT `file_diffs` give a ready read/edit/diff surface for paper files.
- **ARC + context-files endpoints** give a place to inject paper context without embeddings; `DatasetProfile`/`Context`/`ProceduralMemory` schemas are reusable.
- **Child-expert delegation + fanout** primitives support a multi-stage paper pipeline (read -> review -> write -> cite) as a blueprint graph.
- **Validation/doctor**: blueprint validation surfaces disabled rows with errors instead of crashing — good for CI of authored packs (`scripts/validate_marketplace_blueprints.py`).
- **Marketplace registry** (`external/clio-agent-marketplace`) is the distribution channel; a paper-review blueprint could live there or be installed locally.

## Open questions

1. The **`external/clio-agent-marketplace`** and **`external/gact-tui`** submodules are **not checked out** in this clone — I could not read an actual real-world `AGENT.md` or a real declared MCP server (e.g. how `data-semantics` declares NDP/HDF5 servers). Need to `git submodule update --init` (or fetch the marketplace at pinned commit `908e013...`) to see concrete examples and the exact `data` expert frontmatter.
2. Does the GACT runtime support **hot-reload** of a newly dropped workspace blueprint within a live session, or is a server restart/`/v1/prompts/reload`-style call needed? (`/v1/prompts/reload` exists; blueprint reload path unverified.)
3. **Hooks/MCP-descriptor trust model**: packaged `hooks/*.py` and `tools/*.md` are "disabled until explicitly enabled and trusted" — where/how is trust granted (env, a `/v1` endpoint, a config flag)? Not fully traced.
4. Is there any **binary attachment** path for PDFs (the planner extracts `images` for multimodal LMs — `agent.py` `images` param), or only text? PDF bytes -> text must be done by the MCP tool side.
5. **CTE/IOWarp `ARCStore`** backend (`CLIO_ARC_BACKEND=cte`) is a seam but appears unimplemented in this clone — relevant if paper corpora need scalable persistence.
6. The legacy `clio-pack.yaml` Expert Pack path vs `AGENT.md` Blueprint path: which is the going-forward authoring format the marketplace uses? (Code supports both; docs favor `AGENT.md`.)

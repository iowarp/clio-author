# A2A support — design note

Status: **v1 implemented** (`clio_author/integration/a2a_card.py` + `a2a_server.py`;
console script `clio-author-a2a`). Synchronous `message/send` + the Agent Card; one
skill per tool (24) and per role (7). Streaming / `tasks/get` remain future work.
Scope: expose clio-author to **any** A2A-capable host agent over the open
**Agent-to-Agent (A2A) protocol**, without changing any expert.

- A2A protocol specification — https://github.com/a2aproject/A2A (Apache-2.0).

---

## 1. Why

clio-author is already an embeddable subagent: a host calls one method,
`ClioAuthorSubagent.run(action, payload)`, and reads a JSON result. Today two
front doors wrap that surface:

- the **CLI** (`clio-author …`), and
- the **MCP bridge** (`clio_author/integration/mcp_bridge.py`), which exposes
  `capabilities()` + `run(action, payload)` as MCP tools over stdio/HTTP.

A2A adds a third front door aimed at **agent-to-agent** interoperability: instead
of a host embedding clio-author in-process or speaking MCP, any A2A client can
**discover** clio-author's capabilities from a published Agent Card and **invoke**
them as remote tasks over HTTP. This makes clio-author a first-class network
service that an orchestrating agent can delegate paper-processing and
paper-writing work to, regardless of the host's language or framework.

The key point: **the action surface already exists.** A2A is a thin protocol
adapter over the same `run(action, payload)` seam the CLI and MCP bridge use — no
expert, model, or retrieval code changes.

---

## 2. Mapping: A2A concepts → clio-author

| A2A concept | clio-author equivalent |
|---|---|
| **Agent Card** (capability discovery doc) | generated from `integration/manifest.py` (`ACTIONS`, `PHASES`) |
| **Skill** (one advertised capability) | one **action** (29 of them: `ingest`, `plan`, `cite_support`, `compose`, …) |
| Skill **input schema** | the action's `payload_keys` (+ types where known) |
| **Task** (a unit of work with a lifecycle) | one `subagent.run(action, payload)` invocation |
| **Message / Parts** (the request payload) | the action `payload` dict (a `DataPart`); files as `FilePart` |
| **Artifact** (the result) | the `{content, structured, metadata}` result dict |
| Follow-up hints | `metadata.suggested_next` (already attached to every result) |
| Task states (`submitted`→`working`→`completed`/`failed`) | derived from the result (`metadata.error` ⇒ `failed`) |

Because the manifest already records `phase` and `needs_source` per action, the
Agent Card can group skills by lifecycle phase and flag which require a processed
source first — richer discovery than a flat tool list.

---

## 3. Architecture

```
A2A client (any host agent)
        │  HTTP + JSON-RPC 2.0
        ▼
clio_author/integration/a2a_server.py        ← NEW (thin protocol adapter)
        │  subagent.run(action, payload)
        ▼
ClioAuthorSubagent  (integration/clio_adapter.py)   ← unchanged
        │
        ▼
ClioAuthorAgent._route → experts            ← unchanged
```

The A2A server is the only new component of substance. It mirrors `mcp_bridge`:
build a `ClioAuthorSubagent` once, then translate protocol calls into
`run(action, payload)` and translate the result back into A2A artifacts.

### New files

- `clio_author/integration/a2a_card.py` — build the Agent Card from the manifest.
- `clio_author/integration/a2a_server.py` — the ASGI app + JSON-RPC handlers,
  plus a `main()` entry point (mirrors `mcp_bridge.main`), reading `host`/`port`
  from the environment.
- `tests/integration/test_a2a.py` — hermetic round-trip tests (echo model).

### Optional dependency

A2A support ships behind an extra so the core install stays dependency-light:

```
[project.optional-dependencies]
a2a = ["a2a-sdk", "uvicorn", "starlette"]   # or a hand-rolled ASGI app, no SDK
```

Two implementation options:
- **SDK-backed** — use the reference `a2a-sdk` server primitives; least code,
  tracks the spec, adds dependencies.
- **Hand-rolled** — a ~200-line Starlette app implementing the handful of methods
  below; no heavy dependency, full control, more spec surface to maintain.

Recommendation: start **hand-rolled** for the small method set we need (it keeps
the permissive-license footprint clean and mirrors how `mcp_bridge` is thin), and
swap to the SDK later if the spec surface grows.

---

## 4. Protocol surface to implement

A2A is JSON-RPC 2.0 over HTTP(S). The minimum viable set:

| Method / endpoint | Behavior |
|---|---|
| `GET /.well-known/agent-card.json` | serve the generated Agent Card |
| `message/send` | run one action synchronously; return a completed Task + artifact |
| `message/stream` (SSE) | same, but stream `working → completed` for long actions (`compose`, `--deep`) |
| `tasks/get` | look up a task by id (needs a small in-memory/disk task store) |
| `tasks/cancel` | best-effort cancel (most actions are short; return `not-cancelable` where true) |

Push-notification config and `tasks/resubscribe` are **out of scope for v1**.

### Agent Card (shape)

```jsonc
{
  "name": "clio-author",
  "description": "A multi-agent harness for processing, reviewing, and writing scientific papers.",
  "version": "<package version>",
  "url": "https://<host>/",
  "capabilities": { "streaming": true, "pushNotifications": false },
  "defaultInputModes": ["application/json", "text/plain"],
  "defaultOutputModes": ["application/json", "text/plain"],
  "skills": [
    {
      "id": "cite_support",
      "name": "Citation faithfulness check",
      "description": "Does each cited source actually support the claim it is attached to?",
      "tags": ["strengthen", "grounding"],
      "examples": ["Check whether paper.md's citations support its claims."]
    }
    // … one per action, generated from ACTIONS (id, description, phase→tags, payload_keys)
  ]
}
```

### Request → result translation

1. Client sends `message/send` with a `DataPart` payload
   `{ "action": "cite_support", "payload": { … } }` (or the action encoded as the
   skill id + a `DataPart` of payload keys).
2. Server validates `action ∈ ACTIONS`, then calls `subagent.run(action, payload)`.
3. The result `{content, structured, metadata}` becomes the Task's artifact:
   - `content` → a `TextPart`,
   - `structured` → a `DataPart`,
   - `metadata` (incl. `suggested_next`) → the artifact/Task metadata.
4. Task state: `completed` normally; `failed` when `metadata.error` (or a
   top-level `error`) is present. Experts never raise, so the server never 500s on
   a domain error — it returns a clean `failed` task.

---

## 5. Cross-cutting concerns

- **No expert changes.** Everything routes through the existing adapter; the
  contract ("experts never raise; errors are flagged in metadata") makes protocol
  error-mapping trivial and total.
- **Guided pipelines for free.** `metadata.suggested_next` rides along in every
  artifact, so an A2A orchestrator can chain `plan → plan_check → compose →
  ground → export` without hard-coding the lifecycle.
- **Files.** Actions that take large inputs (a `paper.md`, a `blocks.json`) accept
  them as A2A `FilePart`s (inline bytes or a URI the server fetches into the
  payload), mirroring the CLI's `--*-file` flags.
- **Auth.** v1: none / bearer token via a reverse proxy (the server reads an
  optional shared secret from the environment, like the MCP bridge reads host/port).
  The Agent Card advertises the scheme. No secrets are ever embedded in the card.
- **Long-running work.** `compose`, `kg --full`, and `cite_support --deep` can take
  minutes; expose them over `message/stream` with periodic `working` updates. Short
  deterministic actions (`check_refs`, `audit`, `plan_check`) complete in one
  `message/send`.
- **Concurrency.** The adapter is stateless per call; the server can handle
  requests concurrently. A small task store (in-memory dict, optionally a JSON file
  under a work dir) backs `tasks/get`.

---

## 6. Testing (hermetic)

- **Card ↔ manifest parity** — every `ACTIONS` entry appears as a skill; no extra
  or missing skills; skill ids are valid action names.
- **Round-trip** — a `message/send` for `cite_support` (echo model) returns a
  `completed` task whose artifact carries `structured` + `suggested_next`.
- **Error mapping** — a missing-input action returns a `failed` task (not an
  exception, not a 500).
- **Streaming** — a `message/stream` for a multi-step action emits at least one
  `working` event then `completed`.

All run under `EchoLLMClient`, no network — consistent with the existing
integration tests.

---

## 7. Sequencing

1. `a2a_card.py` + card-parity test (pure function over the manifest).
2. `a2a_server.py` with `message/send` + `GET agent-card` + round-trip/error tests.
3. `message/stream` (SSE) for the long actions.
4. `tasks/get` + the small task store.
5. Docs: a "Hosting clio-author over A2A" section in the RUNBOOK + a one-line
   pointer in the README's integration list; the `a2a` extra in `pyproject.toml`.

Each step is independently shippable; v1 can stop after step 2 (synchronous
`message/send`) and still be useful to a host agent.

---

## 8. Open decisions (resolve before building)

1. **SDK vs hand-rolled** server (recommend hand-rolled for v1).
2. **Skill granularity** — one skill per action (29 skills; precise discovery) vs a
   single `run` skill with an `action` argument (1 skill; opaque). Recommend
   one-per-action so hosts can discover the real capability surface.
3. **Action encoding** — action as the A2A `skill id`, vs action inside a `DataPart`.
   Recommend skill id, with the payload as a `DataPart`.
4. **Transport profile** — JSON-RPC/HTTP only for v1 (defer gRPC / HTTP+JSON).
5. **Auth model** — proxy-terminated bearer vs built-in. Recommend proxy for v1.

None of these touch the experts; all are localized to the two new integration
files.

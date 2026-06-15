---
name: new-expert
description: Scaffold a new expert subagent for the clio-parser harness. Use when adding an expert (e.g. ingestor, reviewer, writer, citation, figure) to clio_parser/experts/. Creates the expert module conforming to AgentProtocol/BaseAgent plus a matching pytest test, and registers it where experts are wired.
---

# Scaffold a clio-parser expert

Create a new expert subagent that conforms to the harness contract. Follow these steps; adapt names
to the requested expert.

## 1. Confirm the contract
Read `artifact/notes/DESIGN.md` (§1–§2) and the existing harness code:
- `clio_parser/harness/base.py` (`BaseAgent`), `harness/protocol.py` (`AgentProtocol`),
  `harness/types.py` (`Message`, `AgentOutput`, `Document`, `Block`).
- An existing expert under `clio_parser/experts/` as a template (if one exists).
If the harness modules don't exist yet, stop and report that the M0 skeleton must be built first
(use the `planner` then `coder` agents).

## 2. Create the expert module
`clio_parser/experts/<name>.py`:
- A class `class <Name>Expert(BaseAgent):` implementing the `AgentProtocol` (typically an async
  `run`/`process` returning an `AgentOutput`).
- Declare its `role`, default `system_prompt`, allowed `tools`, and any typed inputs/outputs
  (Pydantic v2).
- Pick the capability track it belongs to (processing vs writing) and reuse existing
  `ingest/`, `retrieval/`, or `tools/files.py` helpers — do not duplicate them.
- License discipline: re-implement, never copy `protoneo` (AGPL) source.

## 3. Wire it in
Register the expert where the `MainAgent`/engine discovers experts (see `clio_parser/agent.py`).
Keep registration declarative and consistent with the other experts.

## 4. Add a test
`tests/experts/test_<name>.py`:
- A hermetic unit test that mocks the LLM/IO boundary and asserts on **structure/schema** (not exact
  LLM text). Gate any live test behind `@pytest.mark.live`.

## 5. Verify
Run `uv run ruff check`, `uv run ruff format`, and `uv run pytest tests/experts/test_<name>.py -q`.
Report files created, how it was wired, and test results.

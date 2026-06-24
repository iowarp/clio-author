"""The kg expert: extract a content knowledge graph from a paper's blocks.

:class:`KGExpert` reads a paper's :class:`~clio_author.ingest.blocks.MemoryBlocks`
and builds a :class:`~clio_author.retrieval.kg.KnowledgeGraph` of its content
(claims / methods / datasets / results / metrics / concepts / tasks and their
relations) via :func:`~clio_author.retrieval.kg.build_kg_from_llm`. This is the
*content* graph -- distinct from any citation / literature graph.

The graph-extraction concept is re-implemented from scratch from protoneo's
knowledge-graph design (AGPL-3.0; no code copied). Like the other experts, this
one never raises: missing inputs or any failure produce an error-flagged
:class:`AgentOutput` (appended once), and an unparseable LLM response yields a
``parse_error``-flagged output with an empty graph. It defaults to
:class:`~clio_author.llm.client.EchoLLMClient` so the harness runs offline (the
echo path naturally exercises the ``parse_error`` branch).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.ingest.blocks import MemoryBlocks
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.retrieval.kg import KnowledgeGraph, build_kg_from_llm
from clio_author.retrieval.kg_pipeline import run_kg_pipeline
from clio_author.tools.files import FileToolError, SafeFiles

KG_SYSTEM_PROMPT = (
    "You are the kg expert. You extract a content knowledge graph of a paper -- "
    "its claims, methods, datasets, results, metrics, concepts and tasks and the "
    "relations between them -- from the paper's memory blocks. This is the paper's "
    "content, not a graph of cited papers. You never invent entities not grounded "
    "in the text."
)

# Node types treated as concrete content entities (everything except 'concept').
_ENTITY_TYPES = {"claim", "method", "dataset", "result", "metric", "task"}


class KGExpert(BaseAgent):
    """Expert that extracts a content knowledge graph from memory blocks."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        files: SafeFiles | None = None,
    ) -> None:
        """Build a kg expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            files: Optional :class:`SafeFiles` used to persist ``kg.json`` /
                ``kg.mmd`` when ``payload["out_dir"]`` is provided.
        """
        super().__init__(
            role="kg",
            system_prompt=KG_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._files = files

    @staticmethod
    def _coerce_blocks(raw: Any) -> MemoryBlocks:
        """Accept a :class:`MemoryBlocks` or its ``model_dump()`` dict."""
        if isinstance(raw, MemoryBlocks):
            return raw
        return MemoryBlocks.model_validate(raw)

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Extract a content knowledge graph from ``task.payload["blocks"]``.

        Reads the blocks (a :class:`MemoryBlocks` or its ``model_dump()`` dict),
        calls :func:`~clio_author.retrieval.kg.build_kg_from_llm`, and returns an
        :class:`AgentOutput` whose ``structured`` is the graph's ``to_dict()``
        and whose ``metadata`` carries ``num_nodes`` / ``num_entities`` /
        ``num_edges``. With ``payload["format"] == "prose"`` ``content`` is the
        Mermaid rendering; otherwise it is a one-line human summary. On a parse
        failure ``metadata["parse_error"]`` is set and ``structured`` is an empty
        graph. When ``files`` and ``payload["out_dir"]`` are both present, writes
        ``<out_dir>/kg.json`` + ``<out_dir>/kg.mmd`` + ``<out_dir>/kg.html`` (an
        interactive viewer; recorded in ``metadata["wrote"]``). Never raises:
        missing inputs or any failure
        produce an error-flagged output (appended once).
        """
        if "blocks" not in task.payload:
            return self._error(session, "no 'blocks' provided in task.payload")

        full = bool(task.payload.get("full")) or task.payload.get("stages") is not None
        try:
            blocks = self._coerce_blocks(task.payload["blocks"])
            error: str | None = None
            pipeline: dict[str, Any] | None = None
            ckpts: dict[str, Any] | None = None
            if full:
                graph, pipeline, ckpts = self._run_pipeline(task, blocks)
            else:
                max_sections = task.payload.get("max_sections")
                graph, error = build_kg_from_llm(
                    blocks,
                    self.llm,
                    max_sections=int(max_sections) if max_sections is not None else None,
                )
            num_entities = sum(1 for node in graph.nodes if node.type in _ENTITY_TYPES)
            raw_max = task.payload.get("max_edges")
            try:
                max_edges = int(raw_max) if raw_max is not None else 500
            except (TypeError, ValueError):
                max_edges = 500
            mermaid = graph.to_mermaid(max_edges=max_edges)
            html = graph.to_html()
            wrote = self._maybe_write(task, graph, mermaid, html)
        except Exception as exc:  # noqa: BLE001 - experts never raise
            return self._error(session, str(exc))

        summary = (
            f"Extracted knowledge graph with {len(graph.nodes)} nodes "
            f"({num_entities} entities) and {len(graph.edges)} relations."
        )
        fmt = str(task.payload.get("format", "")).lower()
        content = mermaid if fmt == "prose" else summary

        metadata: dict[str, Any] = {
            "num_nodes": len(graph.nodes),
            "num_entities": num_entities,
            "num_edges": len(graph.edges),
            "wrote": wrote,
        }
        if pipeline is not None:
            metadata["pipeline"] = pipeline
        if ckpts is not None:
            metadata["checkpoints"] = ckpts
        if error is not None:
            metadata["parse_error"] = error

        output = AgentOutput(
            agent=self.name,
            content=content,
            structured=graph.to_dict(),
            metadata=metadata,
        )
        session.add(output)
        return output

    def _run_pipeline(
        self, task: Task, blocks: MemoryBlocks
    ) -> tuple[KnowledgeGraph, dict[str, Any], dict[str, Any]]:
        """Run the multi-stage pipeline; return ``(graph, report, checkpoints)``.

        ``payload["stages"]`` (a comma-separated string or a list) restricts the
        stages run; ``payload["checkpoints"]`` (a ``{stage: graph.to_dict()}`` map)
        is fed in for resume and the (updated) map is returned for the next call.
        When ``payload["out_dir"]`` is set the pipeline also writes per-stage
        snapshots under ``<out_dir>/kg_pipeline/``.
        """
        raw_stages = task.payload.get("stages")
        stages: list[str] | None
        if isinstance(raw_stages, str):
            stages = [s.strip() for s in raw_stages.split(",") if s.strip()]
        elif isinstance(raw_stages, list):
            stages = [str(s).strip() for s in raw_stages if str(s).strip()]
        else:
            stages = None

        raw_ckpts = task.payload.get("checkpoints")
        checkpoints: dict[str, Any] = dict(raw_ckpts) if isinstance(raw_ckpts, dict) else {}

        out_dir = task.payload.get("out_dir")
        files: SafeFiles | None
        if out_dir and self._files is not None:
            # A constructor-injected sandbox: nest the pipeline under out_dir.
            try:
                (self._files.root / str(out_dir)).mkdir(parents=True, exist_ok=True)
                files = SafeFiles(self._files.root / str(out_dir))
            except OSError:
                files = None
        elif out_dir:
            files = SafeFiles(Path(str(out_dir)))
        else:
            files = None

        graph, report = run_kg_pipeline(
            blocks,
            self.llm,
            stages=stages,
            checkpoints=checkpoints,
            out_dir=files,
        )
        return graph, report, checkpoints

    def _maybe_write(self, task: Task, graph: KnowledgeGraph, mermaid: str, html: str) -> list[str]:
        """Persist ``kg.json`` + ``kg.mmd`` + ``kg.html`` under ``out_dir`` when given.

        ``kg.html`` is the self-contained interactive viewer (the whole graph,
        zoom/pan/search/filter); ``kg.mmd`` is the static color-coded Mermaid
        view; ``kg.json`` is the full machine-readable graph.
        When the expert was constructed with a :class:`SafeFiles`, ``out_dir`` is
        a subdirectory under that sandbox root; otherwise ``out_dir`` is taken as
        the output root directly (the common CLI case — mirrors how
        :mod:`clio_author.experts.compose` / the ingestor derive a ``SafeFiles``
        from ``payload["out_dir"]``). Best-effort/never-raise: ``write_new`` does
        not create parent dirs, so the folder is minted once; a refused or failed
        write is skipped rather than aborting.
        """
        out_dir = task.payload.get("out_dir")
        if not out_dir:
            return []

        # Derive a SafeFiles from out_dir when none was injected (CLI/adapter path).
        if self._files is not None:
            files = self._files
            prefix = f"{out_dir}/"
        else:
            files = SafeFiles(Path(str(out_dir)))
            prefix = ""

        try:
            (files.root / prefix).mkdir(parents=True, exist_ok=True)
        except OSError:
            return []

        wrote: list[str] = []
        for name, text in (
            (f"{prefix}kg.json", json.dumps(graph.to_dict(), indent=2)),
            (f"{prefix}kg.mmd", mermaid),
            (f"{prefix}kg.html", html),
        ):
            try:
                path = files.write_new(name, text)
                wrote.append(str(path))
            except FileToolError:
                continue
        return wrote


__all__ = ["KGExpert", "KG_SYSTEM_PROMPT"]

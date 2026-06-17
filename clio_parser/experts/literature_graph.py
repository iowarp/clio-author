"""The literature graph expert: paper discovery plus visual graph export."""

from __future__ import annotations

from typing import Any

from clio_parser.harness.base import BaseAgent
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Task
from clio_parser.llm.client import EchoLLMClient, LLMClient
from clio_parser.retrieval.literature_graph import (
    LiteratureGraphClient,
    coerce_seeds,
    resolve_literature_graph_client,
    write_graph_artifacts,
)

LITERATURE_GRAPH_SYSTEM_PROMPT = (
    "You are the literature graph expert. You discover related papers around seed papers, "
    "separate prior, derivative, and related works, and emit structured graph data plus "
    "optional visual artifacts. You never invent metadata."
)


class LiteratureGraphExpert(BaseAgent):
    """Expert that builds a browsable paper graph from one or more seeds."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        client: LiteratureGraphClient | None = None,
    ) -> None:
        super().__init__(
            role="literature_graph",
            system_prompt=LITERATURE_GRAPH_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._client = client

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Build a literature graph from ``seed``/``seeds`` and optionally write HTML."""
        try:
            client = (
                resolve_literature_graph_client(str(task.payload["backend"]))
                if task.payload.get("backend") is not None
                else self._client
            )
            if client is None:
                return self._error(session, "no literature graph client configured")
            seeds = coerce_seeds(task.payload.get("seeds", task.payload.get("seed")))
            if not seeds:
                return self._error(session, "no 'seed'/'seeds' provided in task.payload")
            max_nodes = _positive_int(task.payload.get("max_nodes"), default=40, upper=200)
            per_seed = _positive_int(task.payload.get("per_seed"), default=8, upper=50)
            graph = client.build_graph(seeds, max_nodes=max_nodes, per_seed=per_seed)
            wrote: list[str] = []
            out_dir = task.payload.get("out_dir")
            if out_dir:
                wrote = write_graph_artifacts(graph, out_dir)
        except Exception as exc:  # noqa: BLE001 - experts never raise
            return self._error(session, str(exc))

        content = (
            f"Built literature graph with {len(graph.nodes)} papers and {len(graph.edges)} links "
            f"using {graph.backend}."
        )
        output = AgentOutput(
            agent=self.name,
            content=content,
            structured=graph.model_dump(),
            metadata={
                "backend": graph.backend,
                "num_nodes": len(graph.nodes),
                "num_edges": len(graph.edges),
                "prior_count": len(graph.prior_works),
                "derivative_count": len(graph.derivative_works),
                "related_count": len(graph.related_works),
                "wrote": wrote,
            },
        )
        session.add(output)
        return output

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output


def _positive_int(raw: Any, *, default: int, upper: int) -> int:
    """Coerce bounded positive integer payload options."""
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        return default
    return min(value, upper)


__all__ = ["LiteratureGraphExpert", "LITERATURE_GRAPH_SYSTEM_PROMPT"]

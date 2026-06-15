"""The paper_qa expert: grounded question answering over memory blocks.

:class:`PaperQAExpert` retrieves the most relevant
:class:`~clio_parser.ingest.blocks.Block`s for a question, injects them as
context, and asks the LLM to answer using only that grounding. It defaults to
:class:`~clio_parser.llm.client.EchoLLMClient` so the harness runs offline.

Like :class:`~clio_parser.experts.ingestor.IngestorExpert`, this expert never
raises: missing inputs or any failure produce an error-flagged
:class:`AgentOutput` (appended once to the session) so a harness run degrades
gracefully.
"""

from __future__ import annotations

from typing import Any

from clio_parser.harness.base import BaseAgent
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Message, Task
from clio_parser.ingest.blocks import MemoryBlocks
from clio_parser.llm.client import EchoLLMClient, LLMClient
from clio_parser.retrieval.rag import RagRetriever, render_scored

PAPER_QA_SYSTEM_PROMPT = (
    "You are the paper_qa expert. Answer the user's question about a scientific "
    "paper using ONLY the provided context blocks. Each block is identified by a "
    "[block_id]. Cite the block ids you rely on. If the context is insufficient, "
    "say so plainly rather than inventing facts."
)

PAPER_QA_USER_TEMPLATE = (
    "Question:\n{question}\n\n"
    "Context blocks:\n{context}\n\n"
    "Answer the question grounded in the context above."
)


class PaperQAExpert(BaseAgent):
    """Expert that answers questions grounded in retrieved memory blocks."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        retriever: RagRetriever | None = None,
        k: int = 5,
    ) -> None:
        """Build a paper_qa expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient`.
            retriever: Retriever to index/search; a fresh :class:`RagRetriever`
                is built per run when ``None``.
            k: Number of blocks to retrieve and inject.
        """
        super().__init__(
            role="paper_qa",
            system_prompt=PAPER_QA_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._retriever = retriever
        self.k = k

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
        """Answer ``task.payload["question"]`` grounded in ``task.payload["blocks"]``.

        Reads the question (``payload["question"]`` or ``task.description``) and
        the blocks (a :class:`MemoryBlocks` or its ``model_dump()`` dict). It
        indexes the blocks, retrieves the top-``k``, injects them as context,
        and calls the LLM. Returns an :class:`AgentOutput` with the answer as
        ``content``, ``structured={"cited_block_ids", "retrieved"}`` and
        ``metadata={"k", "num_blocks"}``. Never raises: missing inputs or any
        failure produce an error-flagged output (appended once).
        """
        question = task.payload.get("question") or task.description
        if not question:
            return self._error(session, "no 'question' provided in task.payload/description")

        if "blocks" not in task.payload:
            return self._error(session, "no 'blocks' provided in task.payload")

        try:
            blocks = self._coerce_blocks(task.payload["blocks"])
            num_blocks = len(blocks.all_blocks())

            retriever = self._retriever or RagRetriever()
            # An injected shared retriever is re-indexed on every run and so is
            # not safe across *concurrent* runs (fine for the single-threaded
            # Sequential/Engine path; relevant under a Parallel pattern).
            retriever.index(blocks)
            scored = retriever.search(question, k=self.k)
            context, cited_block_ids = render_scored(scored)

            messages = [
                Message(role="system", content=self.system_prompt),
                Message(
                    role="user",
                    content=PAPER_QA_USER_TEMPLATE.format(question=question, context=context),
                ),
            ]
            answer = self.llm.complete(messages)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        output = AgentOutput(
            agent=self.name,
            content=answer,
            structured={
                "cited_block_ids": cited_block_ids,
                "retrieved": [item.to_dict() for item in scored],
            },
            metadata={"k": self.k, "num_blocks": num_blocks},
        )
        session.add(output)
        return output


__all__ = ["PaperQAExpert", "PAPER_QA_SYSTEM_PROMPT", "PAPER_QA_USER_TEMPLATE"]

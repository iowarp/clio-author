"""The paper_qa expert: grounded question answering over memory blocks.

:class:`PaperQAExpert` retrieves the most relevant
:class:`~clio_author.ingest.blocks.Block`s for a question, injects them as
context, and asks the LLM to answer using only that grounding. It defaults to
:class:`~clio_author.llm.client.EchoLLMClient` so the harness runs offline.

Like :class:`~clio_author.experts.ingestor.IngestorExpert`, this expert never
raises: missing inputs or any failure produce an error-flagged
:class:`AgentOutput` (appended once to the session) so a harness run degrades
gracefully.
"""

from __future__ import annotations

from typing import Any

from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.ingest.blocks import Detail, MemoryBlocks, SectionBlock
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.retrieval.rag import RagRetriever, render_scored

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
        indexes the blocks, retrieves the top-``k``, renders them at ``detail``
        (``all`` implies ``full``, so the whole paper really is whole), injects
        them as context,
        and calls the LLM. Returns an :class:`AgentOutput` with the answer as
        ``content``, ``structured={"injected_block_ids", "cited_block_ids",
        "sources", "retrieved"}`` and ``metadata={"k", "num_blocks",
        "whole_paper", "detail", "truncated", ...}``. Never raises: missing inputs or any
        failure produce an error-flagged output (appended once).
        """
        payload = task.payload
        question = payload.get("question") or task.description
        if not question:
            return self._error(session, "no 'question' provided in task.payload/description")

        try:
            blocks = self._resolve_blocks(payload)
            if blocks is None:
                return self._error(
                    session, "no 'blocks'/'markdown'/'text' provided in task.payload"
                )
            num_blocks = len(blocks.all_blocks())
            k = self._resolve_k(payload, num_blocks)
            detail = self._resolve_detail(payload)

            retriever = self._retriever or RagRetriever()
            # An injected shared retriever is re-indexed on every run and so is
            # not safe across *concurrent* runs (fine for the single-threaded
            # Sequential/Engine path; relevant under a Parallel pattern).
            retriever.index(blocks)
            scored = retriever.search(question, k=k)
            context, injected_block_ids = render_scored(scored, detail)

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

        sources = _sources(scored)
        output = AgentOutput(
            agent=self.name,
            content=answer,
            structured={
                # The blocks put *into* the prompt. Named for what it is: these are
                # not parsed back out of the answer, so at k >= num_blocks it is
                # simply every block and carries no per-answer signal.
                "injected_block_ids": injected_block_ids,
                # Legacy alias, same value. Kept so existing callers keep working;
                # "cited" overstates it, prefer ``injected_block_ids``.
                "cited_block_ids": injected_block_ids,
                "sources": sources,
                "retrieved": [item.to_dict() for item in scored],
            },
            metadata={
                "k": k,
                "num_blocks": num_blocks,
                # "every block was injected" -- which is not the same as "the whole
                # text was injected": see ``detail``/``truncated`` below.
                "whole_paper": k >= num_blocks,
                "detail": detail,
                # At any detail below "full" each block is abridged before it enters
                # the prompt ("summary" caps every block at 280 chars), so the model
                # sees section openings rather than section text.
                "truncated": detail != "full",
                "sources": sources,
                "grounded_in": _grounded_in(sources),
            },
        )
        session.add(output)
        return output

    @staticmethod
    def _resolve_blocks(payload: dict[str, Any]) -> MemoryBlocks | None:
        """Resolve memory blocks from ``blocks``, or build them from markdown/text.

        Accepts a :class:`MemoryBlocks` / its dump under ``blocks`` (preferred), or
        a raw ``markdown`` / ``text`` string (e.g. a ``paper.md``) which is split
        into section blocks on the fly -- so ``ask`` works straight from a paper
        file without a separate ``blocks.json``.
        """
        raw = payload.get("blocks")
        if raw is not None:
            return PaperQAExpert._coerce_blocks(raw)
        text = payload.get("markdown") or payload.get("text")
        if isinstance(text, str) and text.strip():
            from clio_author.ingest.blocks import build_section_blocks

            return MemoryBlocks(sections=build_section_blocks(text))
        return None

    def _resolve_k(self, payload: dict[str, Any], num_blocks: int) -> int:
        """How many blocks to inject: payload ``k`` (or ``all``) falls back to ``self.k``.

        ``all`` truthy or ``k <= 0`` means "the whole paper" (inject every block);
        otherwise the value is clamped to the number of available blocks.
        """
        k = self.k
        raw_k = payload.get("k")
        if raw_k is not None:
            try:
                k = int(raw_k)
            except (TypeError, ValueError):
                pass
        if payload.get("all") or k <= 0:
            return max(num_blocks, 1)
        return min(k, num_blocks) if num_blocks else k

    @staticmethod
    def _resolve_detail(payload: dict[str, Any]) -> Detail:
        """Detail level for context rendering: ``ref`` | ``summary`` | ``full``.

        An explicit ``detail`` always wins. Otherwise ``all`` implies ``full``:
        asking for the whole paper and receiving every block truncated to 280
        characters is not what the flag promises. Bare top-k keeps ``summary``,
        which is what makes a wide k affordable.

        Returns the :data:`~clio_author.ingest.blocks.Detail` literal rather than a
        bare ``str`` so a typo in a caller is a type error, not a silent fallback
        to truncated context.
        """
        raw = payload.get("detail")
        if isinstance(raw, str):
            lowered = raw.lower()
            if lowered == "ref":
                return "ref"
            if lowered == "summary":
                return "summary"
            if lowered == "full":
                return "full"
        return "full" if payload.get("all") else "summary"


def _sources(scored: list[Any]) -> list[dict[str, Any]]:
    """Build the provenance list: which block (section + source line) each came from.

    One entry per retrieved block, ordered by relevance: ``block_id``, the
    ``section`` path and ``start_line`` (when it's a section block from Markdown),
    and the retrieval ``score``. This is what tells the reader *where* the answer
    is grounded.
    """
    out: list[dict[str, Any]] = []
    for item in scored:
        block = item.block
        entry: dict[str, Any] = {"block_id": block.block_id, "score": round(item.score, 4)}
        if isinstance(block, SectionBlock):
            entry["section"] = block.section_path
            if block.start_line is not None:
                entry["start_line"] = block.start_line
        out.append(entry)
    return out


def _grounded_in(sources: list[dict[str, Any]]) -> str:
    """A compact one-line provenance string (for the trace), e.g. ``Methods:L42; Results:L88``."""
    parts: list[str] = []
    for s in sources:
        label = s.get("section") or s["block_id"]
        if "start_line" in s:
            label = f"{label}:L{s['start_line']}"
        parts.append(label)
    return "; ".join(parts)


__all__ = ["PaperQAExpert", "PAPER_QA_SYSTEM_PROMPT", "PAPER_QA_USER_TEMPLATE"]

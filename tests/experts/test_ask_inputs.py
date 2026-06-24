"""Tests for `ask`'s flexible inputs: paper.md / text, k, and whole-paper mode."""

from __future__ import annotations

import pytest

from clio_author.experts.paper_qa import PaperQAExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.retrieval.rag import RagRetriever, resolve_rag_retriever

_MD = "# Paper\n\n## Contributions\n\nWe propose X.\n\n## Experiments\n\nWe test on Y with baseline Z.\n"


class _RecordingLLM:
    def __init__(self) -> None:
        self.context = ""

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.context = messages[-1].content
        return "ok"


def _task(**payload: object) -> Task:
    return Task(id="t", description="ask", payload=dict(payload))


def test_ask_builds_blocks_from_markdown() -> None:
    out = PaperQAExpert().run(
        _task(question="what are the contributions?", markdown=_MD), SessionContext(id="s")
    )
    assert "error" not in out.metadata
    assert out.metadata["num_blocks"] >= 2  # split into section blocks


def test_ask_text_input_also_works() -> None:
    out = PaperQAExpert().run(_task(question="q", text=_MD), SessionContext(id="s"))
    assert out.metadata["num_blocks"] >= 2


def test_ask_missing_all_inputs_errors() -> None:
    out = PaperQAExpert().run(_task(question="q"), SessionContext(id="s"))
    assert "error" in out.metadata


def test_all_injects_whole_paper() -> None:
    llm = _RecordingLLM()
    out = PaperQAExpert(llm, k=1).run(
        _task(question="contributions and experiments?", markdown=_MD, all=True),
        SessionContext(id="s"),
    )
    assert out.metadata["whole_paper"] is True
    assert out.metadata["k"] == out.metadata["num_blocks"]
    # the whole paper is in the injected context, not just 1 retrieved block
    assert "Contributions" in llm.context and "Experiments" in llm.context


def test_k_widens_context() -> None:
    out = PaperQAExpert(k=1).run(_task(question="q", markdown=_MD, k=3), SessionContext(id="s"))
    assert out.metadata["k"] == min(3, out.metadata["num_blocks"])


def test_resolve_rag_retriever() -> None:
    assert resolve_rag_retriever(None) is None
    assert resolve_rag_retriever("off") is None
    assert isinstance(resolve_rag_retriever("semantic"), RagRetriever)  # ST-backed; lazy
    with pytest.raises(ValueError, match="unknown CLIO_RAG"):
        resolve_rag_retriever("bogus")

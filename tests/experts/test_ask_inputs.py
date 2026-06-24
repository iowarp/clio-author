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


def test_metadata_reports_source_sections_and_lines() -> None:
    out = PaperQAExpert().run(
        _task(question="what experiments?", markdown=_MD), SessionContext(id="s")
    )
    sources = out.metadata["sources"]
    assert sources, "should report which blocks the answer is grounded in"
    # each source names its section path + the source line of that header
    by_section = {s.get("section"): s for s in sources}
    assert "Paper > Experiments" in by_section
    exp = by_section["Paper > Experiments"]
    assert exp["start_line"] == 7 and "score" in exp  # "## Experiments" is line 7 of _MD
    # the compact trace string names section:Line
    assert "Experiments:L7" in out.metadata["grounded_in"]


def test_build_section_blocks_records_start_line() -> None:
    from clio_author.ingest.blocks import build_section_blocks

    blocks = build_section_blocks("# A\n\nx\n\n## B\n\ny\n")
    assert blocks[0].start_line == 1  # "# A"
    assert blocks[1].start_line == 5  # "## B"


def test_resolve_rag_retriever() -> None:
    assert resolve_rag_retriever(None) is None
    assert resolve_rag_retriever("off") is None
    assert isinstance(resolve_rag_retriever("semantic"), RagRetriever)  # ST-backed; lazy
    with pytest.raises(ValueError, match="unknown CLIO_RAG"):
        resolve_rag_retriever("bogus")

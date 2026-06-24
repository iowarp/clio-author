"""Hermetic tests for :class:`PaperQAExpert`.

Uses the default :class:`EchoLLMClient` (and a small recording fake client) so
no network or heavy deps are touched. Asserts cited block ids, prompt
composition, MemoryBlocks/dict input acceptance, the missing-input error paths,
and an Engine/Sequential run.
"""

from __future__ import annotations

from clio_author.experts.paper_qa import PAPER_QA_SYSTEM_PROMPT, PaperQAExpert
from clio_author.harness.engine import Engine
from clio_author.harness.patterns import Sequential
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.ingest.blocks import FigureInfo, MemoryBlocks, SectionBlock


class RecordingLLMClient:
    """Fake client that records the messages it was called with."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.messages = messages
        return "recorded answer"


def _blocks() -> MemoryBlocks:
    return MemoryBlocks(
        sections=[
            SectionBlock(
                section_path="Methods",
                title="Methods",
                text="We measured photosynthesis efficiency in chloroplasts.",
            ),
            SectionBlock(
                section_path="Results",
                title="Results",
                text="Yield increased by twelve percent.",
            ),
        ],
        figures=[FigureInfo(figure_id=1, caption="Setup diagram.")],
    )


def test_paper_qa_happy_path_cites_blocks() -> None:
    expert = PaperQAExpert()
    session = SessionContext(id="s1")
    task = Task(
        id="t1",
        description="qa",
        payload={"question": "How efficient is photosynthesis?", "blocks": _blocks()},
    )
    output = expert.run(task, session)

    assert output.agent == "paper_qa"
    assert output.content.startswith("[echo]")
    assert output.structured is not None
    cited = output.structured["cited_block_ids"]
    assert cited
    assert "section:methods" in cited
    # retrieved entries are JSON-safe summaries only.
    retrieved = output.structured["retrieved"]
    assert all(set(r) == {"block_id", "kind", "score"} for r in retrieved)
    # k is the *effective* count (clamped to the 3 available blocks = whole paper).
    assert output.metadata["k"] == 3
    assert output.metadata["num_blocks"] == 3
    assert output.metadata["whole_paper"] is True
    assert session.history == [output]


def test_paper_qa_prompt_composition() -> None:
    client = RecordingLLMClient()
    expert = PaperQAExpert(llm=client)
    session = SessionContext(id="s2")
    task = Task(
        id="t2",
        description="qa",
        payload={"question": "What about photosynthesis?", "blocks": _blocks()},
    )
    expert.run(task, session)

    assert len(client.messages) == 2
    assert client.messages[0].role == "system"
    assert client.messages[0].content == PAPER_QA_SYSTEM_PROMPT
    user = client.messages[1]
    assert user.role == "user"
    # Question and injected context both present in the user prompt.
    assert "What about photosynthesis?" in user.content
    assert "photosynthesis" in user.content.lower()
    assert "[section:methods]" not in user.content  # summary detail, not ref
    assert "Methods" in user.content


def test_paper_qa_accepts_model_dump_dict() -> None:
    expert = PaperQAExpert()
    session = SessionContext(id="s3")
    task = Task(
        id="t3",
        description="qa",
        payload={"question": "yield?", "blocks": _blocks().model_dump()},
    )
    output = expert.run(task, session)

    assert "error" not in output.metadata
    assert output.structured is not None
    assert output.metadata["num_blocks"] == 3


def test_paper_qa_question_falls_back_to_description() -> None:
    expert = PaperQAExpert()
    session = SessionContext(id="s4")
    task = Task(id="t4", description="What is the yield?", payload={"blocks": _blocks()})
    output = expert.run(task, session)

    assert "error" not in output.metadata
    assert output.content.startswith("[echo]")


def test_paper_qa_missing_question_errors_without_raising() -> None:
    expert = PaperQAExpert()
    session = SessionContext(id="s5")
    task = Task(id="t5", description="", payload={"blocks": _blocks()})
    output = expert.run(task, session)

    assert output.content == ""
    assert "error" in output.metadata
    assert session.history == [output]


def test_paper_qa_missing_blocks_errors_without_raising() -> None:
    expert = PaperQAExpert()
    session = SessionContext(id="s6")
    task = Task(id="t6", description="a question", payload={})
    output = expert.run(task, session)

    assert output.content == ""
    assert "error" in output.metadata
    assert session.history == [output]


def test_paper_qa_runs_through_engine_sequential() -> None:
    expert = PaperQAExpert()
    engine = Engine()
    task = Task(
        id="t7",
        description="qa",
        payload={"question": "photosynthesis?", "blocks": _blocks()},
    )
    outputs = engine.run([expert], Sequential(), task)

    assert len(outputs) == 1
    assert outputs[0].agent == "paper_qa"
    assert outputs[0].structured is not None

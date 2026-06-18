"""Hermetic tests for :class:`WriterExpert` (recording fake client + tmp root)."""

from __future__ import annotations

from pathlib import Path

from clio_author.experts.writer import WriterExpert
from clio_author.harness.engine import Engine
from clio_author.harness.patterns import Sequential
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.ingest.blocks import MemoryBlocks, SectionBlock
from clio_author.tools.files import SafeFiles


class RecordingLLM:
    """Fake client that records the prompt and returns a fixed completion."""

    def __init__(self, response: str = "Drafted prose with \\cite{smith2020}.") -> None:
        self.response = response
        self.messages: list[Message] = []

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.messages = messages
        return self.response

    @property
    def user_prompt(self) -> str:
        return self.messages[-1].content if self.messages else ""


def _outline_payload() -> dict[str, object]:
    return {
        "vision": "Show that X improves Y.",
        "outline": {
            "title": "Methods",
            "section_path": "Methods",
            "goal": "describe the experimental setup",
            "citation_hints": ["\\cite{smith2020}"],
            "figure_refs": ["fig:arch"],
        },
        "source": "We used a transformer trained on dataset Z.",
    }


def test_draft_phase_prompt_contains_goal_source_and_hints() -> None:
    llm = RecordingLLM()
    expert = WriterExpert(llm=llm)
    session = SessionContext(id="s")
    task = Task(id="t", description="write", payload=_outline_payload())

    output = expert.run(task, session)

    prompt = llm.user_prompt
    assert "describe the experimental setup" in prompt
    assert "transformer trained on dataset Z" in prompt
    assert "\\cite{smith2020}" in prompt
    assert "Show that X improves Y." in prompt
    assert output.metadata["phase"] == "draft"
    assert output.structured is not None
    assert output.structured["section_path"] == "Methods"
    assert session.data["draft"] == llm.response


def test_draft_phase_writes_file_under_root(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    llm = RecordingLLM()
    expert = WriterExpert(llm=llm, files=files)
    session = SessionContext(id="s")
    payload = {**_outline_payload(), "out_path": "methods.md"}
    task = Task(id="t", description="write", payload=payload)

    output = expert.run(task, session)

    written = tmp_path / "methods.md"
    assert written.read_text(encoding="utf-8") == llm.response
    assert output.metadata["wrote"] == [str(written)]
    assert output.structured is not None
    assert output.structured["out_path"] == "methods.md"


def test_draft_phase_uses_memory_blocks_scoped_to_section() -> None:
    llm = RecordingLLM()
    expert = WriterExpert(llm=llm)
    blocks = MemoryBlocks(
        sections=[
            SectionBlock(section_path="Methods", title="Methods", text="scoped methods text"),
            SectionBlock(section_path="Intro", title="Intro", text="unrelated intro text"),
        ]
    )
    session = SessionContext(id="s")
    payload = {
        "outline": {"title": "Methods", "section_path": "Methods", "goal": "g"},
        "blocks": blocks.model_dump(),
    }
    task = Task(id="t", description="write", payload=payload)

    expert.run(task, session)

    prompt = llm.user_prompt
    assert "scoped methods text" in prompt
    assert "unrelated intro text" not in prompt


def test_revise_phase_consumes_critic_feedback() -> None:
    llm = RecordingLLM(response="Revised prose.")
    expert = WriterExpert(llm=llm)
    session = SessionContext(id="s")
    session.data["draft"] = "Original prose."
    session.data["critic_feedback"] = "Clarify the evaluation."
    task = Task(id="t", description="write", payload=_outline_payload())

    output = expert.run(task, session)

    prompt = llm.user_prompt
    assert "Original prose." in prompt
    assert "Clarify the evaluation." in prompt
    assert output.metadata["phase"] == "revise"
    assert session.data["draft"] == "Revised prose."


def test_revise_phase_applies_edit_to_file(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    (tmp_path / "methods.md").write_text("Original prose.", encoding="utf-8")
    llm = RecordingLLM(response="Revised prose.")
    expert = WriterExpert(llm=llm, files=files)
    session = SessionContext(id="s")
    session.data["draft"] = "Original prose."
    session.data["critic_feedback"] = "fix it"
    payload = {**_outline_payload(), "out_path": "methods.md"}
    task = Task(id="t", description="write", payload=payload)

    output = expert.run(task, session)

    assert (tmp_path / "methods.md").read_text(encoding="utf-8") == "Revised prose."
    assert output.metadata["wrote"] == [str(tmp_path / "methods.md")]


def test_missing_outline_error() -> None:
    expert = WriterExpert(llm=RecordingLLM())
    session = SessionContext(id="s")
    task = Task(id="t", description="write", payload={"source": "x"})

    output = expert.run(task, session)
    assert "error" in output.metadata
    assert session.history[-1] is output


def test_missing_source_error() -> None:
    expert = WriterExpert(llm=RecordingLLM())
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="",
        payload={"outline": {"title": "Methods", "section_path": "Methods"}},
    )

    output = expert.run(task, session)
    assert "error" in output.metadata


def test_file_refusal_flags_error_not_raise(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    (tmp_path / "methods.md").write_text("existing", encoding="utf-8")
    expert = WriterExpert(llm=RecordingLLM(), files=files)
    session = SessionContext(id="s")
    payload = {**_outline_payload(), "out_path": "methods.md"}
    task = Task(id="t", description="write", payload=payload)

    output = expert.run(task, session)
    assert "error" in output.metadata
    assert (tmp_path / "methods.md").read_text(encoding="utf-8") == "existing"


def test_emits_one_output_via_engine_sequential() -> None:
    expert = WriterExpert(llm=RecordingLLM())
    task = Task(id="t", description="write", payload=_outline_payload())
    session = SessionContext(id="s")

    outputs = Engine().run([expert], Sequential(), task, session)
    assert len(outputs) == 1
    assert len(session.history) == 1
    assert outputs[0].agent == "writer"

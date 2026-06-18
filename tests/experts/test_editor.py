"""Hermetic tests for :class:`EditorExpert`."""

from __future__ import annotations

from pathlib import Path

from clio_author.experts.editor import EditorExpert
from clio_author.experts.review_models import PaperReview
from clio_author.harness.engine import Engine
from clio_author.harness.patterns import Sequential
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.tools.files import SafeFiles


class RecordingLLM:
    def __init__(self, response: str = "Revised text.") -> None:
        self.response = response
        self.messages: list[Message] = []

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.messages = messages
        return self.response

    @property
    def user_prompt(self) -> str:
        return self.messages[-1].content if self.messages else ""


def test_review_weaknesses_rendered_into_prompt() -> None:
    llm = RecordingLLM()
    expert = EditorExpert(llm=llm)
    review = PaperReview(
        summary="Decent but underspecified.",
        weaknesses=["Evaluation is thin", "Missing ablation"],
        questions=["How does it scale?"],
    )
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="edit",
        payload={"draft": "Original prose.", "review": review.model_dump()},
    )

    output = expert.run(task, session)

    prompt = llm.user_prompt
    assert "Original prose." in prompt
    assert "Evaluation is thin" in prompt
    assert "Missing ablation" in prompt
    assert "How does it scale?" in prompt
    assert output.structured is not None
    assert output.structured["revised"] == "Revised text."


def test_edit_applied_via_apply_edit(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    (tmp_path / "sec.md").write_text("Original prose.", encoding="utf-8")
    llm = RecordingLLM(response="Better prose.")
    expert = EditorExpert(llm=llm, files=files)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="edit",
        payload={"target": "sec.md", "critic_notes": "tighten it"},
    )

    output = expert.run(task, session)

    assert (tmp_path / "sec.md").read_text(encoding="utf-8") == "Better prose."
    assert output.metadata["wrote"] == [str(tmp_path / "sec.md")]


def test_reads_draft_from_session_and_feedback_from_session() -> None:
    llm = RecordingLLM()
    expert = EditorExpert(llm=llm)
    session = SessionContext(id="s")
    session.data["draft"] = "Draft from session."
    session.data["critic_feedback"] = "make it concise"
    task = Task(id="t", description="edit", payload={})

    expert.run(task, session)
    assert "Draft from session." in llm.user_prompt
    assert "make it concise" in llm.user_prompt


def test_missing_prose_error() -> None:
    expert = EditorExpert(llm=RecordingLLM())
    session = SessionContext(id="s")
    task = Task(id="t", description="edit", payload={"critic_notes": "x"})

    output = expert.run(task, session)
    assert "error" in output.metadata


def test_missing_feedback_error() -> None:
    expert = EditorExpert(llm=RecordingLLM())
    session = SessionContext(id="s")
    task = Task(id="t", description="edit", payload={"draft": "prose"})

    output = expert.run(task, session)
    assert "error" in output.metadata


def test_file_refusal_flags_error(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    # target file does not exist -> read raises -> flagged, not raised.
    expert = EditorExpert(llm=RecordingLLM(), files=files)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="edit",
        payload={"target": "missing.md", "critic_notes": "x"},
    )

    output = expert.run(task, session)
    assert "error" in output.metadata


def test_emits_one_output_via_engine_sequential() -> None:
    expert = EditorExpert(llm=RecordingLLM())
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="edit",
        payload={"draft": "prose", "critic_notes": "fix"},
    )

    outputs = Engine().run([expert], Sequential(), task, session)
    assert len(outputs) == 1
    assert len(session.history) == 1
    assert outputs[0].agent == "editor"

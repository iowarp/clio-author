"""Hermetic tests for :class:`PolishExpert`."""

from __future__ import annotations

from pathlib import Path

from clio_parser.experts.polish import PolishExpert
from clio_parser.harness.engine import Engine
from clio_parser.harness.patterns import Sequential
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import Message, Task
from clio_parser.integration import ClioParserSubagent
from clio_parser.tools.files import SafeFiles


class RecordingLLM:
    def __init__(self, response: str = "Polished prose with \\cite{a} and Figure 1.") -> None:
        self.response = response
        self.messages: list[Message] = []

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.messages = messages
        return self.response

    @property
    def user_prompt(self) -> str:
        return self.messages[-1].content if self.messages else ""


def test_polish_returns_model_text() -> None:
    llm = RecordingLLM(response="Clear, tight prose.")
    expert = PolishExpert(llm=llm)
    session = SessionContext(id="s")
    task = Task(id="t", description="polish", payload={"text": "rough draft here"})

    output = expert.run(task, session)

    assert output.content == "Clear, tight prose."
    assert output.structured is not None
    assert output.structured["polished"] == "Clear, tight prose."
    assert output.structured["voice"] is None
    assert "rough draft here" in llm.user_prompt


def test_polish_reads_draft_fallback_and_voice_in_prompt() -> None:
    llm = RecordingLLM()
    expert = PolishExpert(llm=llm)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="polish",
        payload={"draft": "the draft body", "voice": "concise"},
    )

    output = expert.run(task, session)

    assert "the draft body" in llm.user_prompt
    assert "concise" in llm.user_prompt
    assert output.structured is not None
    assert output.structured["voice"] == "concise"


def test_polish_reads_from_session_draft() -> None:
    llm = RecordingLLM()
    expert = PolishExpert(llm=llm)
    session = SessionContext(id="s")
    session.data["draft"] = "session draft body"
    task = Task(id="t", description="polish", payload={})

    expert.run(task, session)
    assert "session draft body" in llm.user_prompt


def test_polish_applies_target_via_safefiles(tmp_path: Path) -> None:
    files = SafeFiles(tmp_path)
    (tmp_path / "sec.md").write_text("Original prose.", encoding="utf-8")
    llm = RecordingLLM(response="Polished prose.")
    expert = PolishExpert(llm=llm, files=files)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="polish",
        payload={"text": "Original prose.", "target": "sec.md"},
    )

    output = expert.run(task, session)

    assert (tmp_path / "sec.md").read_text(encoding="utf-8") == "Polished prose."
    assert output.metadata["wrote"] == [str(tmp_path / "sec.md")]


def test_polish_missing_text_error() -> None:
    expert = PolishExpert(llm=RecordingLLM())
    session = SessionContext(id="s")
    task = Task(id="t", description="", payload={})

    output = expert.run(task, session)
    assert "error" in output.metadata


def test_polish_prose_format_keeps_structured() -> None:
    llm = RecordingLLM(response="Polished prose.")
    expert = PolishExpert(llm=llm)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="polish",
        payload={"text": "rough", "format": "prose"},
    )

    output = expert.run(task, session)
    assert output.content == "Polished prose."
    assert output.structured is not None
    assert output.structured["polished"] == "Polished prose."


def test_polish_via_engine_sequential() -> None:
    expert = PolishExpert(llm=RecordingLLM())
    session = SessionContext(id="s")
    task = Task(id="t", description="polish", payload={"text": "rough"})

    outputs = Engine().run([expert], Sequential(), task, session)
    assert len(outputs) == 1
    assert outputs[0].agent == "polish"


def test_polish_via_adapter_is_json_serializable() -> None:
    result = ClioParserSubagent().run("polish", {"text": "rough draft"})
    assert result["action"] == "polish"
    assert set(result) == {"action", "content", "structured", "metadata"}

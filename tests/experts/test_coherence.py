"""Hermetic tests for :class:`CoherenceExpert`."""

from __future__ import annotations

from clio_author.experts.coherence import CoherenceExpert
from clio_author.harness.engine import Engine
from clio_author.harness.patterns import Sequential
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.integration import ClioAuthorSubagent

_TWO_ISSUE_JSON = """THOUGHT: comparing the sections.

```json
{"issues": [
  {"kind": "terminology", "sections": ["Intro", "Methods"], "detail": "calls it X then Y"},
  {"kind": "contradiction", "sections": ["Methods", "Results"], "detail": "10 vs 12 trials"}
], "summary": "two issues found"}
```
"""


class CannedLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[Message] = []

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.messages = messages
        return self.response

    @property
    def user_prompt(self) -> str:
        return self.messages[-1].content if self.messages else ""


def test_coherence_parses_two_issues() -> None:
    expert = CoherenceExpert(llm=CannedLLM(_TWO_ISSUE_JSON))
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="coherence",
        payload={
            "sections": [
                {"title": "Intro", "draft": "uses X"},
                {"title": "Methods", "draft": "uses Y"},
            ]
        },
    )

    output = expert.run(task, session)

    assert output.structured is not None
    assert len(output.structured["issues"]) == 2
    assert output.metadata["num_issues"] == 2
    assert output.metadata["num_sections"] == 2
    assert "two issues found" in output.content


def test_coherence_splits_markdown_into_sections() -> None:
    llm = CannedLLM(_TWO_ISSUE_JSON)
    expert = CoherenceExpert(llm=llm)
    session = SessionContext(id="s")
    markdown = "# Title\n\n## Introduction\n\nBody one.\n\n## Methods\n\nBody two.\n"
    task = Task(id="t", description="coherence", payload={"markdown": markdown})

    output = expert.run(task, session)

    assert output.metadata["num_sections"] == 2
    assert "### Introduction" in llm.user_prompt
    assert "### Methods" in llm.user_prompt


def test_coherence_echo_parse_error_no_raise() -> None:
    # Default EchoLLMClient returns non-JSON -> parse_error path, no raise.
    expert = CoherenceExpert()
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="coherence",
        payload={"sections": [{"title": "A", "draft": "x"}]},
    )

    output = expert.run(task, session)
    assert output.structured is None
    assert "parse_error" in output.metadata
    assert output.metadata["num_sections"] == 1


def test_coherence_prose_format_renders_issues() -> None:
    expert = CoherenceExpert(llm=CannedLLM(_TWO_ISSUE_JSON))
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="coherence",
        payload={
            "sections": [{"title": "Intro", "draft": "a"}, {"title": "Methods", "draft": "b"}],
            "format": "prose",
        },
    )

    output = expert.run(task, session)

    assert output.structured is None
    assert output.metadata["num_issues"] == 2
    assert "[terminology]" in output.content
    assert "[contradiction]" in output.content


def test_coherence_text_fallback() -> None:
    expert = CoherenceExpert(llm=CannedLLM(_TWO_ISSUE_JSON))
    session = SessionContext(id="s")
    task = Task(id="t", description="coherence", payload={"text": "a single passage"})

    output = expert.run(task, session)
    assert output.metadata["num_sections"] == 1


def test_coherence_missing_sections_error() -> None:
    expert = CoherenceExpert(llm=CannedLLM(_TWO_ISSUE_JSON))
    session = SessionContext(id="s")
    task = Task(id="t", description="", payload={})

    output = expert.run(task, session)
    assert "error" in output.metadata


def test_coherence_via_engine_sequential() -> None:
    expert = CoherenceExpert(llm=CannedLLM(_TWO_ISSUE_JSON))
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="coherence",
        payload={"sections": [{"title": "A", "draft": "x"}]},
    )

    outputs = Engine().run([expert], Sequential(), task, session)
    assert len(outputs) == 1
    assert outputs[0].agent == "coherence"


def test_coherence_via_adapter_is_json_serializable() -> None:
    result = ClioAuthorSubagent().run("coherence", {"sections": [{"title": "A", "draft": "x"}]})
    assert result["action"] == "coherence"
    assert set(result) == {"action", "content", "structured", "metadata"}

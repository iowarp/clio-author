"""Hermetic tests for :class:`ReviewerExpert`.

A small ``CannedJSONLLMClient`` returns a THOUGHT + fenced JSON review so the
happy path is exercised offline; the default :class:`EchoLLMClient` exercises the
graceful ``parse_error`` branch. Also covers markdown/MemoryBlocks/dict paper
inputs, score clamping, the missing-paper error, and an Engine/Sequential run.
"""

from __future__ import annotations

import json

from clio_parser.experts.review_models import PaperReview, PersonaSpec
from clio_parser.experts.reviewer import ReviewerExpert, build_reviewer_system_prompt
from clio_parser.harness.engine import Engine
from clio_parser.harness.patterns import Sequential
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import Message, Task
from clio_parser.ingest.blocks import MemoryBlocks, SectionBlock

# Out-of-range scores deliberately included to test clamping.
_REVIEW_JSON = {
    "Summary": "A clear method for X.",
    "Strengths": ["Novel", "Well written"],
    "Weaknesses": "Limited evaluation",
    "Questions": ["Why Y?"],
    "Limitations": ["Small dataset"],
    "Ethical Concerns": False,
    "Originality": 9,  # > 4 -> clamp to 4
    "Quality": 0,  # < 1 -> clamp to 1
    "Clarity": 3,
    "Significance": 2,
    "Soundness": 3,
    "Presentation": 3,
    "Contribution": 2,
    "Overall": 99,  # > 10 -> clamp to 10
    "Confidence": 4,
    "Decision": "Accept",
}


class CannedJSONLLMClient:
    """Fake client that returns a fixed THOUGHT + fenced JSON review."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.messages: list[Message] = []

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.messages = messages
        return (
            "THOUGHT:\nlooks solid.\n\nREVIEW JSON:\n```json\n" + json.dumps(self.payload) + "\n```"
        )


def test_reviewer_happy_path_parses_and_clamps() -> None:
    expert = ReviewerExpert(llm=CannedJSONLLMClient(_REVIEW_JSON))
    session = SessionContext(id="s")
    task = Task(id="t", description="review", payload={"paper": "# Paper\nbody"})

    output = expert.run(task, session)

    assert output.agent == "reviewer"
    assert "error" not in output.metadata
    assert "parse_error" not in output.metadata
    assert output.structured is not None
    structured = output.structured
    assert structured["originality"] == 4  # clamped down
    assert structured["quality"] == 1  # clamped up
    assert structured["overall"] == 10  # clamped down
    assert structured["weaknesses"] == ["Limited evaluation"]  # scalar -> list
    assert structured["decision"] == "Accept"
    assert output.metadata["decision"] == "Accept"
    assert output.metadata["overall"] == 10
    assert session.history == [output]


def test_reviewer_echo_yields_parse_error_without_raising() -> None:
    expert = ReviewerExpert()  # default EchoLLMClient -> non-JSON
    session = SessionContext(id="s")
    task = Task(id="t", description="review", payload={"paper": "# Paper"})

    output = expert.run(task, session)

    assert output.structured is None
    assert "parse_error" in output.metadata
    assert "error" not in output.metadata
    assert output.content.startswith("[echo]")
    assert session.history == [output]


def test_reviewer_accepts_markdown_blocks_and_dict() -> None:
    blocks = MemoryBlocks(
        sections=[SectionBlock(section_path="Intro", title="Intro", text="hello")]
    )
    for paper in (blocks, blocks.model_dump()):
        client = CannedJSONLLMClient(_REVIEW_JSON)
        expert = ReviewerExpert(llm=client)
        session = SessionContext(id="s")
        task = Task(id="t", description="review", payload={"blocks": paper})

        output = expert.run(task, session)

        assert "error" not in output.metadata
        assert output.structured is not None
        # The rendered (full-detail) paper text reaches the user prompt.
        assert "hello" in client.messages[1].content


def test_reviewer_markdown_payload_key() -> None:
    client = CannedJSONLLMClient(_REVIEW_JSON)
    expert = ReviewerExpert(llm=client)
    session = SessionContext(id="s")
    task = Task(id="t", description="review", payload={"markdown": "# Paper\nfull text"})

    expert.run(task, session)

    assert "full text" in client.messages[1].content


def test_reviewer_missing_paper_errors_without_raising() -> None:
    expert = ReviewerExpert(llm=CannedJSONLLMClient(_REVIEW_JSON))
    session = SessionContext(id="s")
    task = Task(id="t", description="", payload={})

    output = expert.run(task, session)

    assert output.content == ""
    assert "error" in output.metadata
    assert session.history == [output]


def test_reviewer_system_prompt_reflects_persona() -> None:
    benign = build_reviewer_system_prompt(PersonaSpec())
    mean = build_reviewer_system_prompt(
        PersonaSpec(knowledgeable=False, responsible=False, benign=False, label="harsh")
    )

    assert "benign reviewer" in benign
    assert "mean reviewer" in mean
    assert "lazy reviewer" in mean


def test_decision_substring_mapping() -> None:
    # Detection is substring-based on "accept": "Weak Accept" -> Accept,
    # anything else (e.g. "Borderline Reject") -> Reject.
    accept = PaperReview.from_loose_dict({"Decision": "Weak Accept"})
    reject = PaperReview.from_loose_dict({"Decision": "Borderline Reject"})

    assert accept.decision == "Accept"
    assert reject.decision == "Reject"


def test_reviewer_runs_via_engine_sequential() -> None:
    expert = ReviewerExpert(llm=CannedJSONLLMClient(_REVIEW_JSON))
    task = Task(id="t", description="review", payload={"paper": "# Paper"})

    outputs = Engine().run([expert], Sequential(), task)

    assert len(outputs) == 1
    assert outputs[0].structured is not None
    assert outputs[0].metadata["decision"] == "Accept"

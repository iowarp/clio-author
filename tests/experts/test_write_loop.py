"""Hermetic tests for the writer<->reviewer CriticRefine loop."""

from __future__ import annotations

import json
from pathlib import Path

from clio_parser.experts.review_models import PersonaSpec
from clio_parser.experts.reviewer import ReviewerExpert
from clio_parser.experts.write_loop import ReviewerAsCritic, run_write_review_loop
from clio_parser.experts.writer import WriterExpert
from clio_parser.harness.patterns import NO_CHANGES_SENTINEL
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import Message, Task
from clio_parser.tools.files import SafeFiles

_REJECT_REVIEW = {
    "Summary": "Needs work.",
    "Weaknesses": ["Evaluation is thin"],
    "Questions": ["How does it scale?"],
    "Decision": "Reject",
    "Overall": 4,
}

_ACCEPT_REVIEW = {
    "Summary": "Solid.",
    "Weaknesses": [],
    "Decision": "Accept",
    "Overall": 8,
}


class ScriptedReviewerLLM:
    """Returns a sequence of fenced JSON reviews, one per call."""

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.calls = 0

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return "THOUGHT:\nx\n\nREVIEW JSON:\n```json\n" + json.dumps(payload) + "\n```"


class WriterLLM:
    """Writer client returning a distinct draft each call."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.calls += 1
        return f"draft v{self.calls}"


def _writer() -> WriterExpert:
    return WriterExpert(llm=WriterLLM())


def _task() -> Task:
    return Task(
        id="t",
        description="write",
        payload={
            "outline": {"title": "Methods", "section_path": "Methods", "goal": "g"},
            "source": "source material",
        },
    )


def test_reviewer_as_critic_emits_sentinel_on_accept() -> None:
    reviewer = ReviewerExpert(llm=ScriptedReviewerLLM([_ACCEPT_REVIEW]))
    critic = ReviewerAsCritic(reviewer)
    session = SessionContext(id="s")
    session.data["draft"] = "some draft"

    output = critic.run(_task(), session)
    assert output.content == NO_CHANGES_SENTINEL


def test_reviewer_as_critic_renders_weaknesses_on_reject() -> None:
    reviewer = ReviewerExpert(llm=ScriptedReviewerLLM([_REJECT_REVIEW]))
    critic = ReviewerAsCritic(reviewer)
    session = SessionContext(id="s")
    session.data["draft"] = "some draft"

    output = critic.run(_task(), session)
    assert output.content != NO_CHANGES_SENTINEL
    assert "Evaluation is thin" in output.content
    assert "How does it scale?" in output.content


def test_loop_draft_review_revise_then_accept_stops() -> None:
    writer = _writer()
    reviewer = ReviewerExpert(llm=ScriptedReviewerLLM([_REJECT_REVIEW, _ACCEPT_REVIEW]))
    session = SessionContext(id="s")

    outputs = run_write_review_loop(
        _task(), writer=writer, reviewer=reviewer, max_rounds=3, session=session
    )

    agents = [o.agent for o in outputs]
    # draft -> review(reject) -> revise -> review(accept/sentinel)
    assert agents == ["writer", "reviewer-critic", "writer", "reviewer-critic"]
    assert outputs[-1].content == NO_CHANGES_SENTINEL
    # The writer revised after the first (rejecting) review.
    assert session.data["draft"] == "draft v2"


def test_loop_max_rounds_exhaustion() -> None:
    writer = _writer()
    # Always reject -> loop runs the full round budget.
    reviewer = ReviewerExpert(llm=ScriptedReviewerLLM([_REJECT_REVIEW]))
    session = SessionContext(id="s")

    outputs = run_write_review_loop(
        _task(), writer=writer, reviewer=reviewer, max_rounds=2, session=session
    )

    # draft + (review + revise) * 2
    agents = [o.agent for o in outputs]
    assert agents == [
        "writer",
        "reviewer-critic",
        "writer",
        "reviewer-critic",
        "writer",
    ]
    assert all(o.content != NO_CHANGES_SENTINEL for o in outputs)


def test_loop_writes_then_edits_file_in_lockstep(tmp_path: Path) -> None:
    # WriterExpert backed by SafeFiles + payload["out_path"]: the draft phase
    # creates the file (write_new) and the revise phase updates it in place
    # (apply_edit whole-body replace). Locks in the draft/file invariant: the
    # in-memory draft and the file on disk stay in lockstep.
    files = SafeFiles(tmp_path)
    writer = WriterExpert(llm=WriterLLM(), files=files)
    reviewer = ReviewerExpert(llm=ScriptedReviewerLLM([_REJECT_REVIEW, _ACCEPT_REVIEW]))
    session = SessionContext(id="s")

    task = Task(
        id="t",
        description="write",
        payload={
            "outline": {"title": "Methods", "section_path": "Methods", "goal": "g"},
            "source": "source material",
            "out_path": "section.md",
        },
    )

    outputs = run_write_review_loop(
        task, writer=writer, reviewer=reviewer, max_rounds=3, session=session
    )

    # draft -> review(reject) -> revise -> review(accept/sentinel)
    agents = [o.agent for o in outputs]
    assert agents == ["writer", "reviewer-critic", "writer", "reviewer-critic"]
    assert outputs[-1].content == NO_CHANGES_SENTINEL

    out_file = tmp_path / "section.md"
    # The draft phase used write_new; the revise phase used apply_edit.
    assert outputs[0].metadata["phase"] == "draft"
    assert outputs[0].metadata["wrote"] == [str(out_file)]
    assert outputs[2].metadata["phase"] == "revise"
    assert outputs[2].metadata["wrote"] == [str(out_file)]

    # Final file content matches the last draft in memory (lockstep invariant).
    assert out_file.read_text(encoding="utf-8") == session.data["draft"] == "draft v2"
    # No temp files left behind by the atomic overwrite.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["section.md"]


def test_loop_error_flagged_review_halts() -> None:
    writer = _writer()
    # EchoLLMClient produces no parseable JSON -> reviewer parse_error, structured
    # is None -> ReviewerAsCritic passes it through -> loop halts after that review.
    reviewer = ReviewerExpert(persona=PersonaSpec())
    session = SessionContext(id="s")

    outputs = run_write_review_loop(
        _task(), writer=writer, reviewer=reviewer, max_rounds=3, session=session
    )

    agents = [o.agent for o in outputs]
    # draft -> critic(error); loop halts on the error-flagged critic output.
    assert agents == ["writer", "reviewer-critic"]
    assert "error" in outputs[-1].metadata

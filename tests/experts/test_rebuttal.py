"""Hermetic tests for :class:`RebuttalExpert`."""

from __future__ import annotations

from clio_author.experts.rebuttal import RebuttalExpert
from clio_author.experts.review_models import PaperReview
from clio_author.harness.engine import Engine
from clio_author.harness.patterns import Sequential
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.integration import ClioAuthorSubagent


class RecordingLLM:
    def __init__(self, response: str = "We thank the reviewer. (1) ...") -> None:
        self.response = response
        self.messages: list[Message] = []

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        self.messages = messages
        return self.response

    @property
    def user_prompt(self) -> str:
        return self.messages[-1].content if self.messages else ""


def test_rebuttal_populates_structured() -> None:
    llm = RecordingLLM(response="Point-by-point rebuttal.")
    expert = RebuttalExpert(llm=llm)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="rebuttal",
        payload={"paper": "# Paper\nbody", "review_text": "Weakness: thin eval."},
    )

    output = expert.run(task, session)

    assert output.agent == "rebuttal"
    assert "error" not in output.metadata
    assert output.structured is not None
    assert output.structured["rebuttal"] == "Point-by-point rebuttal."
    assert output.content == "Point-by-point rebuttal."
    assert session.history == [output]


def test_rebuttal_renders_structured_review_into_prompt() -> None:
    llm = RecordingLLM()
    expert = RebuttalExpert(llm=llm)
    review = PaperReview(
        summary="Decent but underspecified.",
        weaknesses=["Evaluation is thin", "Missing ablation"],
        questions=["How does it scale?"],
    )
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="rebuttal",
        payload={"paper": "# Paper\nbody", "review": review.model_dump()},
    )

    expert.run(task, session)

    prompt = llm.user_prompt
    assert "Evaluation is thin" in prompt
    assert "Missing ablation" in prompt
    assert "How does it scale?" in prompt


def test_rebuttal_missing_inputs_error_without_raising() -> None:
    expert = RebuttalExpert(llm=RecordingLLM())
    session = SessionContext(id="s")

    no_review = expert.run(
        Task(id="t", description="rebuttal", payload={"paper": "# Paper"}),
        session,
    )
    assert no_review.content == ""
    assert "error" in no_review.metadata

    session2 = SessionContext(id="s2")
    no_paper = expert.run(
        Task(id="t", description="rebuttal", payload={"review_text": "Weak eval."}),
        session2,
    )
    assert no_paper.content == ""
    assert "error" in no_paper.metadata


def test_rebuttal_runs_via_engine_sequential() -> None:
    expert = RebuttalExpert(llm=RecordingLLM(response="Rebuttal."))
    task = Task(
        id="t",
        description="rebuttal",
        payload={"paper": "# Paper", "review_text": "Weak."},
    )

    outputs = Engine().run([expert], Sequential(), task)

    assert len(outputs) == 1
    assert outputs[0].structured is not None
    assert outputs[0].structured["rebuttal"] == "Rebuttal."


def test_rebuttal_runs_via_adapter() -> None:
    sub = ClioAuthorSubagent()
    result = sub.run("rebuttal", {"paper": "# Paper\nbody", "review_text": "Weak eval."})
    assert result["action"] == "rebuttal"
    assert result["structured"] is not None
    assert "rebuttal" in result["structured"]
    assert "error" not in result


def test_capabilities_lists_rebuttal() -> None:
    caps = ClioAuthorSubagent().capabilities()
    actions = {entry["action"] for entry in caps["actions"]}
    assert "rebuttal" in actions

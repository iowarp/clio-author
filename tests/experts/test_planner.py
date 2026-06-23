"""Hermetic tests for :class:`PlannerExpert` and its compose integration.

A canned LLM client returning a fenced plan JSON drives the happy path (tasks /
claims / sources coerced, per-section plans, ``num_sections`` / ``num_tasks``
metadata, ``plan.json`` persisted under ``out_dir``); the offline
:class:`EchoLLMClient` exercises the graceful fallback (empty tasks, no raise,
``plan_errors`` > 0); missing inputs flag an error; the adapter / CLI surfaces
stay JSON-serializable and reachable; and compose ``--plan`` feeds the writer a
``section_plan`` while ``plan=false`` is unchanged.
"""

from __future__ import annotations

import json

from clio_author.experts.citation import CitationExpert
from clio_author.experts.compose import run_compose
from clio_author.experts.planner import PlannerExpert
from clio_author.experts.reviewer import ReviewerExpert
from clio_author.experts.writer import WriterExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.integration import ClioAuthorSubagent
from clio_author.llm.client import EchoLLMClient

_PLAN_JSON = """\
Here is the plan:
```json
{
  "tasks": ["state the problem", "summarise prior work", "introduce the approach"],
  "claims": ["the gap is real", "our method closes it"],
  "sources": ["prior survey", "our experiments"],
  "word_budget": 350,
  "citation_hints": ["\\\\cite{smith2020}"]
}
```
"""

_OUTLINE_2 = {
    "title": "A Study",
    "vision": "We study things.",
    "sections": [
        {"title": "Introduction", "goal": "motivate"},
        {"title": "Method", "goal": "describe approach"},
    ],
}


class CannedLLMClient:
    """Returns a fixed string regardless of the prompt."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        return self._response


def _task(**payload: object) -> Task:
    return Task(id="t", description="plan", payload=dict(payload))


def _session() -> SessionContext:
    return SessionContext(id="s")


# --------------------------------------------------------------------------- #
# Happy path                                                                  #
# --------------------------------------------------------------------------- #
def test_canned_plan_populates_tasks_and_claims() -> None:
    expert = PlannerExpert(CannedLLMClient(_PLAN_JSON))
    out = expert.run(_task(outline=_OUTLINE_2), _session())

    assert out.agent == "planner"
    assert "error" not in out.metadata
    assert out.structured is not None
    plans = out.structured["plans"]
    assert len(plans) == 2
    assert plans[0]["tasks"] == [
        "state the problem",
        "summarise prior work",
        "introduce the approach",
    ]
    assert plans[0]["claims"] == ["the gap is real", "our method closes it"]
    assert plans[0]["sources"] == ["prior survey", "our experiments"]
    # Word budget + citation hints merged back into the section outline.
    assert plans[0]["outline"]["word_budget"] == 350
    assert "\\cite{smith2020}" in plans[0]["outline"]["citation_hints"]


def test_metadata_counts_two_sections_and_tasks() -> None:
    expert = PlannerExpert(CannedLLMClient(_PLAN_JSON))
    out = expert.run(_task(outline=_OUTLINE_2), _session())
    assert out.metadata["num_sections"] == 2
    # 3 tasks per section across 2 sections.
    assert out.metadata["num_tasks"] == 6
    assert out.metadata["plan_errors"] == 0
    assert "Planned 2 sections, 6 tasks total." == out.content


def test_generates_outline_from_idea_when_none_given() -> None:
    # Canned client doubles as the outline generator; the JSON has no "sections"
    # so the generated outline has none -> error-flagged (no sections).
    outline_json = json.dumps(
        {"title": "T", "vision": "v", "sections": [{"title": "A", "goal": "g"}]}
    )
    expert = PlannerExpert(CannedLLMClient(f"```json\n{outline_json}\n```"))
    out = expert.run(_task(idea="study things"), _session())
    assert "error" not in out.metadata
    assert out.structured is not None
    assert out.metadata["num_sections"] == 1


# --------------------------------------------------------------------------- #
# Persistence                                                                 #
# --------------------------------------------------------------------------- #
def test_out_dir_writes_plan_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    expert = PlannerExpert(CannedLLMClient(_PLAN_JSON))
    out = expert.run(_task(outline=_OUTLINE_2, out_dir=str(tmp_path)), _session())
    wrote = out.metadata["wrote"]
    assert len(wrote) == 1
    written = wrote[0]
    assert written.endswith("plan.json")
    payload = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    assert len(payload["plans"]) == 2


# --------------------------------------------------------------------------- #
# Graceful fallback / errors                                                  #
# --------------------------------------------------------------------------- #
def test_echo_client_graceful_fallback_no_raise() -> None:
    expert = PlannerExpert(EchoLLMClient())
    out = expert.run(_task(outline=_OUTLINE_2), _session())
    assert "error" not in out.metadata
    assert out.structured is not None
    plans = out.structured["plans"]
    assert len(plans) == 2
    assert all(plan["tasks"] == [] for plan in plans)
    assert out.metadata["plan_errors"] == 2
    assert out.metadata["num_tasks"] == 0


def test_no_idea_no_outline_is_error_flagged() -> None:
    expert = PlannerExpert(CannedLLMClient(_PLAN_JSON))
    out = expert.run(_task(), _session())
    assert "error" in out.metadata
    assert out.structured is None


# --------------------------------------------------------------------------- #
# Adapter / CLI surfaces                                                       #
# --------------------------------------------------------------------------- #
def test_adapter_run_plan_json_serializable() -> None:
    sub = ClioAuthorSubagent(CannedLLMClient(_PLAN_JSON))
    result = sub.run("plan", {"outline": _OUTLINE_2})
    assert result["action"] == "plan"
    assert set(result) == {"action", "content", "structured", "metadata"}
    assert json.loads(json.dumps(result)) == result
    assert result["metadata"]["num_sections"] == 2


def test_capabilities_lists_plan() -> None:
    caps = ClioAuthorSubagent().capabilities()
    actions = {entry["action"] for entry in caps["actions"]}
    assert "plan" in actions
    assert len(caps["actions"]) == 26


# --------------------------------------------------------------------------- #
# Compose integration                                                          #
# --------------------------------------------------------------------------- #
class _RecordingWriter(WriterExpert):
    """A writer that records whether it received a ``section_plan`` payload."""

    def __init__(self, llm) -> None:  # type: ignore[no-untyped-def]
        super().__init__(llm)
        self.saw_section_plan: list[bool] = []

    def run(self, task: Task, session: SessionContext):  # type: ignore[no-untyped-def]
        self.saw_section_plan.append("section_plan" in task.payload)
        return super().run(task, session)


def test_compose_plan_true_feeds_writer_a_section_plan() -> None:
    llm = CannedLLMClient(_PLAN_JSON)
    writer = _RecordingWriter(llm)
    reviewer = ReviewerExpert(llm)
    citation = CitationExpert(llm)
    out = run_compose(
        Task(
            id="t",
            description="compose",
            payload={"idea": "x", "outline": _OUTLINE_2, "plan": True},
        ),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )
    assert "error" not in out.metadata
    assert out.metadata.get("planned") is True
    assert writer.saw_section_plan == [True, True]


def test_compose_plan_false_is_unchanged() -> None:
    llm = EchoLLMClient()
    writer = _RecordingWriter(llm)
    reviewer = ReviewerExpert(llm)
    citation = CitationExpert(llm)
    out = run_compose(
        Task(
            id="t",
            description="compose",
            payload={"idea": "x", "outline": _OUTLINE_2},
        ),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )
    assert "error" not in out.metadata
    assert "planned" not in out.metadata
    assert writer.saw_section_plan == [False, False]

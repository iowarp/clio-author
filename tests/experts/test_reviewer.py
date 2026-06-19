"""Hermetic tests for :class:`ReviewerExpert`.

A small ``CannedJSONLLMClient`` returns a THOUGHT + fenced JSON review so the
happy path is exercised offline; the default :class:`EchoLLMClient` exercises the
graceful ``parse_error`` branch. Also covers markdown/MemoryBlocks/dict paper
inputs, score clamping, the missing-paper error, and an Engine/Sequential run.
"""

from __future__ import annotations

import json

from clio_author.experts.review_models import PaperReview, PersonaSpec
from clio_author.experts.reviewer import ReviewerExpert, build_reviewer_system_prompt
from clio_author.harness.engine import Engine
from clio_author.harness.patterns import Sequential
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.ingest.blocks import MemoryBlocks, SectionBlock
from clio_author.retrieval.scholar import FakeScholarClient, S2Record

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


def test_reviewer_prose_mode_returns_text_not_json() -> None:
    class ProseLLM:
        def complete(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            return "Summary: solid.\nStrengths: clear.\nWeaknesses: small eval.\nDecision: Accept (7/10)"

    out = ReviewerExpert(llm=ProseLLM()).run(
        Task(id="r", description="review", payload={"paper": "# P\n\nbody", "format": "prose"}),
        SessionContext(id="s"),
    )
    assert out.structured is None
    assert out.metadata["format"] == "prose"
    assert "error" not in out.metadata and "parse_error" not in out.metadata
    assert "Decision: Accept" in out.content


# --- retrieval-grounded review ------------------------------------------- #
_RELATED_TITLE = "Attention Is All You Need"


def _related_record() -> S2Record:
    return S2Record(
        paper_id="rw1",
        title=_RELATED_TITLE,
        authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"],
        year=2017,
        abstract="We propose the Transformer, a sequence model based solely on attention.",
        journal="NeurIPS",
    )


class CountingFakeScholar(FakeScholarClient):
    """FakeScholarClient that records how many times it was searched."""

    def __init__(self, records_by_title: dict[str, list[S2Record]]) -> None:
        super().__init__(records_by_title)
        self.calls = 0

    def search_title(self, title, year_hint, cutoff_date):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().search_title(title, year_hint, cutoff_date)


def test_reviewer_grounded_injects_related_work_into_prompt() -> None:
    scholar = CountingFakeScholar({_RELATED_TITLE: [_related_record()]})
    client = CannedJSONLLMClient(_REVIEW_JSON)
    expert = ReviewerExpert(llm=client, scholar_client=scholar)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="review",
        payload={"paper": "# Body", "title": _RELATED_TITLE, "ground": True},
    )

    output = expert.run(task, session)

    assert scholar.calls == 1
    # The related work appears in the user prompt the model saw.
    user_prompt = client.messages[1].content
    assert _RELATED_TITLE in user_prompt
    assert "Related prior work" in user_prompt
    assert "do not invent references" in user_prompt
    # Metadata + structured echo the grounding for the caller.
    assert output.metadata["grounded"] is True
    assert output.metadata["related_work"] == [{"title": _RELATED_TITLE, "year": 2017}]
    assert output.structured is not None
    assert output.structured["related_work"] == [{"title": _RELATED_TITLE, "year": 2017}]
    assert "error" not in output.metadata and "grounding_error" not in output.metadata


def test_reviewer_ground_true_without_scholar_client_is_normal_review() -> None:
    client = CannedJSONLLMClient(_REVIEW_JSON)
    expert = ReviewerExpert(llm=client)  # no scholar client
    session = SessionContext(id="s")
    task = Task(id="t", description="review", payload={"paper": "# Paper\nbody", "ground": True})

    output = expert.run(task, session)

    assert output.metadata["grounded"] is False
    assert "related_work" not in output.metadata
    assert output.structured is not None
    assert "related_work" not in output.structured
    assert "Related prior work" not in client.messages[1].content
    assert "error" not in output.metadata


def test_reviewer_ground_false_never_calls_scholar() -> None:
    scholar = CountingFakeScholar({_RELATED_TITLE: [_related_record()]})
    expert = ReviewerExpert(llm=CannedJSONLLMClient(_REVIEW_JSON), scholar_client=scholar)
    session = SessionContext(id="s")
    task = Task(id="t", description="review", payload={"paper": "# Paper\nbody"})

    output = expert.run(task, session)

    assert scholar.calls == 0
    assert output.metadata["grounded"] is False
    assert output.structured is not None


class RaisingScholar:
    def search_title(self, title, year_hint, cutoff_date):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


def test_reviewer_grounding_error_is_caught_and_review_still_produced() -> None:
    expert = ReviewerExpert(llm=CannedJSONLLMClient(_REVIEW_JSON), scholar_client=RaisingScholar())
    session = SessionContext(id="s")
    task = Task(id="t", description="review", payload={"paper": "# Paper\nbody", "ground": True})

    output = expert.run(task, session)

    assert output.metadata["grounding_error"] == "boom"
    assert output.metadata["grounded"] is False
    assert output.structured is not None  # review still produced
    assert output.metadata["decision"] == "Accept"


# --- multimodal (vision-grounded) review --------------------------------- #
class FakeVision:
    """A fake VisionClient that records calls and returns a fixed description."""

    def __init__(self, description: str = "A bar chart comparing accuracy.") -> None:
        self.description = description
        self.calls: list[tuple[str, str]] = []

    def describe_image(self, image_path: str, prompt: str) -> str:
        self.calls.append((image_path, prompt))
        return self.description

    def generate_image(self, prompt, out_path):  # type: ignore[no-untyped-def]
        raise NotImplementedError


def _write_png(path) -> str:  # type: ignore[no-untyped-def]
    # A minimal 1x1 PNG is enough -- the fake vision never decodes it.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f5d0000000049454e44ae426082"
    )
    path.write_bytes(png)
    return str(path)


def test_reviewer_vision_folds_figure_descriptions_into_prompt(tmp_path) -> None:  # type: ignore[no-untyped-def]
    image = _write_png(tmp_path / "fig1.png")
    vision = FakeVision()
    client = CannedJSONLLMClient(_REVIEW_JSON)
    expert = ReviewerExpert(llm=client, vision=vision)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="review",
        payload={
            "paper": "# Paper\nbody",
            "figures": [{"figure_id": 1, "image_path": image, "caption": "Accuracy by model."}],
        },
    )

    output = expert.run(task, session)

    assert vision.calls and vision.calls[0][0] == image
    user_prompt = client.messages[1].content
    assert "## Figures" in user_prompt
    assert "A bar chart comparing accuracy." in user_prompt
    assert output.metadata["vision_review"] is True
    assert output.metadata["figures_seen"] == 1
    assert output.structured is not None


def test_reviewer_no_vision_is_text_only_unchanged() -> None:
    client = CannedJSONLLMClient(_REVIEW_JSON)
    expert = ReviewerExpert(llm=client)  # no vision
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="review",
        payload={"paper": "# Paper\nbody", "figures": [{"image_path": "/nope.png"}]},
    )

    output = expert.run(task, session)

    assert "vision_review" not in output.metadata
    assert "figures_seen" not in output.metadata
    assert "## Figures" not in client.messages[1].content


def test_reviewer_vision_never_called_when_no_figures(tmp_path) -> None:  # type: ignore[no-untyped-def]
    vision = FakeVision()
    client = CannedJSONLLMClient(_REVIEW_JSON)
    expert = ReviewerExpert(llm=client, vision=vision)
    session = SessionContext(id="s")
    task = Task(id="t", description="review", payload={"paper": "# Paper\nbody"})

    output = expert.run(task, session)

    assert vision.calls == []
    assert "vision_review" not in output.metadata
    assert output.structured is not None


def test_reviewer_vision_skips_unreadable_figure_without_raising() -> None:
    vision = FakeVision()
    client = CannedJSONLLMClient(_REVIEW_JSON)
    expert = ReviewerExpert(llm=client, vision=vision)
    session = SessionContext(id="s")
    task = Task(
        id="t",
        description="review",
        payload={"paper": "# Paper\nbody", "figures": [{"image_path": "/does/not/exist.png"}]},
    )

    output = expert.run(task, session)

    assert vision.calls == []  # unreadable image -> skipped, vision never called
    assert "vision_review" not in output.metadata
    assert output.structured is not None

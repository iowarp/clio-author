"""Hermetic tests for :func:`clio_author.experts.compose.run_compose`.

The orchestration and assembly are deterministic under :class:`EchoLLMClient`;
scripted/canned clients exercise the review and outline-parse paths, and the
citation wiring reuses the :class:`FakeScholarClient` fixture. No network.
"""

from __future__ import annotations

import json

from clio_author.experts.citation import CitationExpert
from clio_author.experts.compose import run_compose
from clio_author.experts.reviewer import ReviewerExpert
from clio_author.experts.writer import WriterExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.integration.clio_adapter import ClioAuthorSubagent
from clio_author.llm.client import EchoLLMClient
from clio_author.retrieval.scholar import FakeScholarClient, S2Record
from clio_author.tools.files import SafeFiles

_OUTLINE_3 = {
    "title": "A Study of Things",
    "vision": "We study things and report results.",
    "sections": [
        {"title": "A", "goal": "introduce A"},
        {"title": "B", "goal": "develop B"},
        {"title": "C", "goal": "conclude C"},
    ],
}

_S2_TITLE = "neural machine translation by jointly learning to align and translate"


def _experts(
    llm=None,
    *,
    scholar_client=None,
):  # type: ignore[no-untyped-def]
    llm = llm or EchoLLMClient()
    return (
        WriterExpert(llm),
        ReviewerExpert(llm),
        CitationExpert(llm, client=scholar_client),
        llm,
    )


def _task(**payload: object) -> Task:
    return Task(id="t", description="compose", payload=dict(payload))


# --------------------------------------------------------------------------- #
# Outline + assembly                                                          #
# --------------------------------------------------------------------------- #
def test_explicit_outline_three_sections_in_order() -> None:
    writer, reviewer, citation, llm = _experts()
    out = run_compose(
        _task(idea="study things", outline=_OUTLINE_3),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )

    assert out.agent == "compose"
    assert "error" not in out.metadata
    assert out.structured is not None
    assert len(out.structured["sections"]) == 3
    assert out.metadata["num_sections"] == 3

    content = out.content
    assert content.startswith("# A Study of Things")
    assert content.index("## A") < content.index("## B") < content.index("## C")


def test_per_section_isolation() -> None:
    # Each section's echoed draft must reflect its OWN goal, not a prior one
    # (proves the per-section fresh SessionContext: no draft leakage).
    writer, reviewer, citation, llm = _experts()
    out = run_compose(
        _task(idea="study things", outline=_OUTLINE_3),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )
    assert out.structured is not None
    sec_a, sec_b = out.structured["sections"][0], out.structured["sections"][1]
    assert "introduce A" in sec_a["draft"]
    assert "develop B" in sec_b["draft"]
    assert "introduce A" not in sec_b["draft"]


class _ReviewScript:
    """Scripted client: writer draft -> reviewer JSON (weak then accept) -> revise.

    The write_review loop calls the LLM alternately for the writer (draft/revise)
    and the reviewer (a JSON review). The reviewer first returns a Reject with a
    weakness (drives a revision), then an Accept (stops the loop).
    """

    def __init__(self) -> None:
        self.reviews = 0

    def complete(self, messages: list[Message], **kwargs: object) -> str:  # noqa: D401
        system = messages[0].content if messages else ""
        if "reviewer" in system.lower():
            self.reviews += 1
            if self.reviews == 1:
                decision, weaknesses = "Reject", ["needs more detail"]
            else:
                decision, weaknesses = "Accept", []
            return json.dumps(
                {
                    "Summary": "ok",
                    "Strengths": ["clear"],
                    "Weaknesses": weaknesses,
                    "Questions": [],
                    "Limitations": [],
                    "Ethical Concerns": False,
                    "Originality": 3,
                    "Quality": 3,
                    "Clarity": 3,
                    "Significance": 3,
                    "Soundness": 3,
                    "Presentation": 3,
                    "Contribution": 3,
                    "Overall": 7,
                    "Confidence": 4,
                    "Decision": decision,
                }
            )
        return "drafted prose"


def test_review_true_runs_loop() -> None:
    client = _ReviewScript()
    writer, reviewer, citation, llm = _experts(client)
    out = run_compose(
        _task(
            idea="x",
            outline={"title": "T", "sections": [{"title": "A", "goal": "g"}]},
            review=True,
        ),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )
    assert "error" not in out.metadata
    assert out.metadata["reviewed"] is True
    assert client.reviews >= 1


def test_review_false_one_draft_per_section() -> None:
    writer, reviewer, citation, llm = _experts()
    out = run_compose(
        _task(idea="x", outline=_OUTLINE_3, review=False),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )
    assert out.metadata["reviewed"] is False
    assert out.structured is not None
    assert len(out.structured["sections"]) == 3


# --------------------------------------------------------------------------- #
# Citation wiring                                                             #
# --------------------------------------------------------------------------- #
def _scholar() -> FakeScholarClient:
    record = S2Record(
        paper_id="p1",
        title=_S2_TITLE,
        authors=["Dzmitry Bahdanau"],
        year=2015,
        abstract="attention",
        journal="ICLR",
    )
    return FakeScholarClient({_S2_TITLE: [record]})


def test_citation_wiring_produces_references_block() -> None:
    writer, reviewer, citation, llm = _experts(scholar_client=_scholar())
    out = run_compose(
        _task(
            idea="x",
            outline={"title": "T", "sections": [{"title": "A", "goal": "g"}]},
            candidates=[{"title": _S2_TITLE, "year": 2015}],
        ),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )
    assert "error" not in out.metadata
    assert out.structured is not None
    assert out.structured["citations"] is not None
    assert out.structured["citations"]["suggested_bibtex"]
    assert "## References" in out.content


def test_citation_no_client_records_error_but_still_produces() -> None:
    writer, reviewer, citation, llm = _experts()  # citation has no client
    out = run_compose(
        _task(
            idea="x",
            outline={"title": "T", "sections": [{"title": "A", "goal": "g"}]},
            candidates=[{"title": _S2_TITLE, "year": 2015}],
        ),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )
    assert "citation_error" in out.metadata
    assert "error" not in out.metadata  # whole compose still succeeded
    assert out.content.startswith("# T")
    assert "## References" not in out.content


# --------------------------------------------------------------------------- #
# Error paths                                                                 #
# --------------------------------------------------------------------------- #
def test_no_idea_no_outline_errors() -> None:
    writer, reviewer, citation, llm = _experts()
    session = SessionContext(id="s")
    out = run_compose(
        _task(),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
        session=session,
    )
    assert out.content == ""
    assert "error" in out.metadata
    assert session.history == [out]


class _RaisingWriter(WriterExpert):
    def run(self, task, session):  # type: ignore[no-untyped-def]
        out = self._error(session, "writer exploded")
        return out


def test_section_writer_error_records_and_continues() -> None:
    llm = EchoLLMClient()
    writer = _RaisingWriter(llm)
    reviewer = ReviewerExpert(llm)
    citation = CitationExpert(llm)
    out = run_compose(
        _task(idea="x", outline={"title": "T", "sections": [{"title": "A", "goal": "g"}]}),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )
    # Only one section, and it failed -> whole compose error-flagged.
    assert "error" in out.metadata


def test_partial_section_failure_keeps_others() -> None:
    # A writer that fails ONLY on section B keeps A and C drafted.
    llm = EchoLLMClient()

    class _FlakyWriter(WriterExpert):
        def run(self, task, session):  # type: ignore[no-untyped-def]
            outline = self._coerce_outline(task.payload)
            if outline is not None and outline.title == "B":
                return self._error(session, "boom on B")
            return super().run(task, session)

    writer = _FlakyWriter(llm)
    out = run_compose(
        _task(idea="x", outline=_OUTLINE_3),
        writer=writer,
        reviewer=ReviewerExpert(llm),
        citation=CitationExpert(llm),
        llm=llm,
    )
    assert "error" not in out.metadata
    assert len(out.metadata["section_errors"]) == 1
    assert out.metadata["section_errors"][0]["section"] == "B"
    assert "section draft unavailable" in out.structured["sections"][1]["draft"]
    assert out.structured["sections"][0]["draft"]  # A drafted
    assert out.structured["sections"][2]["draft"]  # C drafted


class _NoJsonClient:
    """Canned client returning plain prose with no parseable JSON object."""

    def complete(self, messages: list[Message], **kwargs: object) -> str:  # noqa: D401
        return "Sorry, I cannot produce an outline right now."


def test_unparseable_generated_outline_errors() -> None:
    # A generated outline that contains no parseable JSON must error-flag.
    writer, reviewer, citation, llm = _experts(_NoJsonClient())
    out = run_compose(
        _task(idea="just an idea, no outline given"),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
    )
    assert "error" in out.metadata
    assert "could not parse" in out.metadata["error"]


# --------------------------------------------------------------------------- #
# Persistence                                                                 #
# --------------------------------------------------------------------------- #
def test_out_dir_writes_paper_and_sections(tmp_path) -> None:  # type: ignore[no-untyped-def]
    files = SafeFiles(tmp_path)
    writer, reviewer, citation, llm = _experts()
    out = run_compose(
        _task(idea="x", outline=_OUTLINE_3),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
        files=files,
    )
    paper = tmp_path / "paper.md"
    assert paper.exists()
    assert str(paper) in out.metadata["wrote"]
    section_files = sorted((tmp_path / "sections").glob("*.md"))
    assert len(section_files) == 3
    assert all(str(p) in out.metadata["wrote"] for p in section_files)


def test_latex_true_writes_paper_tex(tmp_path) -> None:  # type: ignore[no-untyped-def]
    files = SafeFiles(tmp_path)
    writer, reviewer, citation, llm = _experts()
    out = run_compose(
        _task(idea="x", outline=_OUTLINE_3, latex=True),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
        files=files,
    )
    tex = tmp_path / "paper.tex"
    assert tex.exists()
    assert str(tex) in out.metadata["wrote"]
    assert out.metadata["latex"] is True
    assert "\\documentclass{article}" in tex.read_text(encoding="utf-8")
    # No bibliography emitted without citations.
    assert not (tmp_path / "references.bib").exists()


def test_latex_true_with_citations_writes_bib(tmp_path) -> None:  # type: ignore[no-untyped-def]
    files = SafeFiles(tmp_path)
    writer, reviewer, citation, llm = _experts(scholar_client=_scholar())
    out = run_compose(
        _task(
            idea="x",
            outline={"title": "T", "sections": [{"title": "A", "goal": "g"}]},
            candidates=[{"title": _S2_TITLE, "year": 2015}],
            latex=True,
        ),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
        files=files,
    )
    bib = tmp_path / "references.bib"
    assert (tmp_path / "paper.tex").exists()
    assert bib.exists()
    assert str(bib) in out.metadata["wrote"]
    assert "\\bibliography{references}" in (tmp_path / "paper.tex").read_text(encoding="utf-8")


def test_latex_false_writes_no_tex(tmp_path) -> None:  # type: ignore[no-untyped-def]
    files = SafeFiles(tmp_path)
    writer, reviewer, citation, llm = _experts()
    out = run_compose(
        _task(idea="x", outline=_OUTLINE_3),
        writer=writer,
        reviewer=reviewer,
        citation=citation,
        llm=llm,
        files=files,
    )
    assert not (tmp_path / "paper.tex").exists()
    assert out.metadata["latex"] is False


# --------------------------------------------------------------------------- #
# Adapter + CLI                                                               #
# --------------------------------------------------------------------------- #
def test_adapter_compose_is_json_serializable() -> None:
    sub = ClioAuthorSubagent()
    result = sub.run("compose", {"idea": "x", "outline": _OUTLINE_3})
    json.dumps(result)  # must not raise
    assert result["action"] == "compose"
    assert result["metadata"]["num_sections"] == 3


def test_capabilities_lists_compose() -> None:
    sub = ClioAuthorSubagent()
    actions = {a["action"] for a in sub.capabilities()["actions"]}
    assert "compose" in actions


def test_cli_compose_with_json_outline(capsys) -> None:  # type: ignore[no-untyped-def]
    from clio_author.cli import main

    blob = json.dumps({"outline": _OUTLINE_3})
    code = main(["compose", "--idea", "study things", "--json", blob])
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert code == 0
    assert parsed["action"] == "compose"
    assert parsed["metadata"]["num_sections"] == 3


def test_cli_compose_malformed_json(capsys) -> None:  # type: ignore[no-untyped-def]
    from clio_author.cli import main

    code = main(["compose", "--idea", "x", "--json", "{not json"])
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert code == 1
    assert "error" in parsed


def test_section_body_dedupes_leading_heading() -> None:
    from clio_author.experts.compose import _section_body

    # Writer emitted its own "## Introduction" — must not double up.
    out = _section_body("Introduction", "## Introduction\n\nBody text.")
    assert out == "## Introduction\n\nBody text."
    assert out.count("## Introduction") == 1
    # Numbered variant also dedupes.
    out2 = _section_body("Introduction", "## 1. Introduction\n\nBody.")
    assert out2.count("Introduction") == 1
    # A non-matching leading heading is preserved.
    out3 = _section_body("Method", "## Overview\n\nText.")
    assert "## Method" in out3 and "## Overview" in out3

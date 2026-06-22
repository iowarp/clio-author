"""Hermetic tests for the layered :func:`run_section_review` orchestrator."""

from __future__ import annotations

import json

from clio_author.experts.check_refs import CheckRefsExpert
from clio_author.experts.coherence import CoherenceExpert
from clio_author.experts.reviewer import ReviewerExpert
from clio_author.experts.section_review import run_section_review
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task

# A single JSON object that satisfies BOTH the coherence extractor (issues /
# summary) and the reviewer extractor (Overall / Decision / ...). Both experts
# pull the same balanced {...} object via _extract_json_object.
_COMBINED = {
    "issues": [
        {"kind": "contradiction", "sections": ["Intro"], "detail": "claims conflict"},
    ],
    "summary": "one contradiction",
    "Summary": "A section.",
    "Overall": 3,
    "Decision": "Reject",
    "Weaknesses": ["thin"],
}


class CannedJSONLLMClient:
    """Returns a fixed fenced JSON object usable by coherence and reviewer."""

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        return "```json\n" + json.dumps(_COMBINED) + "\n```"


def _experts(llm: object) -> tuple[CheckRefsExpert, CoherenceExpert, ReviewerExpert]:
    return CheckRefsExpert(llm), CoherenceExpert(llm), ReviewerExpert(llm)  # type: ignore[arg-type]


def test_section_review_aggregates_three_layers() -> None:
    llm = CannedJSONLLMClient()
    check_refs, coherence, reviewer = _experts(llm)
    task = Task(
        id="t",
        description="sr",
        payload={"section": r"## Intro\n\nbody with \cite{missing}.", "bibtex": ""},
    )
    out = run_section_review(
        task,
        check_refs=check_refs,
        coherence=coherence,
        reviewer=reviewer,
        session=SessionContext(id="s"),
    )
    assert out.agent == "section_review"
    s = out.structured
    assert s is not None
    assert "layer1" in s and "layer2" in s and "layer3" in s
    severities = {f["severity"] for f in s["severity_summary"]}
    # L1 missing-in-bib -> critical; L2 contradiction -> major; L3 overall<5 -> major.
    assert "critical" in severities
    assert "major" in severities
    assert out.metadata["max_severity"] == "critical"


def test_section_review_clean_section_no_findings() -> None:
    # Echo client: deterministic L1 finds nothing; L2/L3 do not parse -> no findings.
    check_refs, coherence, reviewer = _experts(None)
    task = Task(id="t", description="sr", payload={"section": "## Intro\n\nClean body."})
    out = run_section_review(
        task,
        check_refs=check_refs,
        coherence=coherence,
        reviewer=reviewer,
        session=SessionContext(id="s"),
    )
    assert out.structured is not None
    assert out.structured["severity_summary"] == []
    assert out.metadata["max_severity"] is None


def test_section_review_missing_text_errors() -> None:
    check_refs, coherence, reviewer = _experts(None)
    out = run_section_review(
        Task(id="t", description="sr", payload={}),
        check_refs=check_refs,
        coherence=coherence,
        reviewer=reviewer,
        session=SessionContext(id="s"),
    )
    assert "error" in out.metadata


def test_section_review_with_persona() -> None:
    check_refs, coherence, reviewer = _experts(CannedJSONLLMClient())
    out = run_section_review(
        Task(
            id="t",
            description="sr",
            payload={
                "section": "## Intro\n\nbody.",
                "persona": {"knowledgeable": False, "label": "novice"},
            },
        ),
        check_refs=check_refs,
        coherence=coherence,
        reviewer=reviewer,
        session=SessionContext(id="s"),
    )
    assert out.agent == "section_review"
    assert out.structured is not None

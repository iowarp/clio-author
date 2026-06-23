"""Hermetic tests for :class:`ResearchExpert`.

A canned client returns a fenced JSON brief for the happy path; the default
:class:`EchoLLMClient` exercises the parse_error / empty-brief degradation; a
:class:`FakeScholarClient` exercises grounding of proposed titles.
"""

from __future__ import annotations

import json

from clio_author.experts.research import ResearchExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.retrieval.scholar import FakeScholarClient, S2Record

_BRIEF_JSON = {
    "topic": "efficient attention",
    "foundational": [
        {"title": "Attention Is All You Need", "note": "the transformer", "year": 2017}
    ],
    "recent": [{"title": "FlashAttention", "note": "io-aware", "year": 2022}],
    "competing": [{"title": "Linear Attention", "note": "kernel trick"}],
    "gaps": ["no long-context eval"],
    "synthesis": {"theme": ["sparsity helps"]},
    "confidence": "MEDIUM",
    "recommendations": ["read FlashAttention"],
}


class CannedJSONLLMClient:
    """Fake client returning a fixed fenced JSON research brief."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        return "THOUGHT:\nok.\n\n```json\n" + json.dumps(self.payload) + "\n```"


def _run(expert: ResearchExpert, **payload: object) -> object:
    return expert.run(Task(id="t", description="research", payload=payload), SessionContext(id="s"))


def test_research_happy_path_parses() -> None:
    out = _run(ResearchExpert(CannedJSONLLMClient(_BRIEF_JSON)), topic="efficient attention")
    assert out.agent == "research"
    assert "error" not in out.metadata
    assert "parse_error" not in out.metadata
    s = out.structured
    assert s is not None
    assert s["topic"] == "efficient attention"
    assert out.metadata["num_sources"] == 3
    assert out.metadata["confidence"] == "MEDIUM"
    assert out.metadata["grounded"] is False  # no scholar client


def test_research_grounds_titles_with_scholar() -> None:
    scholar = FakeScholarClient(
        {
            "Attention Is All You Need": [
                S2Record(
                    paper_id="p1",
                    title="Attention Is All You Need",
                    authors=["A Vaswani"],
                    year=2017,
                    abstract="The dominant sequence transduction models...",
                )
            ]
        }
    )
    expert = ResearchExpert(CannedJSONLLMClient(_BRIEF_JSON), scholar_client=scholar)
    out = _run(expert, topic="efficient attention")
    assert out.metadata["grounded"] is True
    s = out.structured
    assert s is not None
    grounded_titles = [n for n in s["foundational"] if n["grounded"]]
    assert grounded_titles
    assert grounded_titles[0]["verified_title"] == "Attention Is All You Need"


def test_research_discover_seeds_brief_from_real_papers() -> None:
    # A fake client whose search_query returns a real record not already in the
    # LLM brief: with discover=True it is folded into `recent` and pre-grounded.
    scholar = FakeScholarClient(
        {
            "efficient attention": [
                S2Record(
                    paper_id="disc1",
                    title="Discovered Efficient Attention Survey",
                    authors=["R Searcher"],
                    year=2023,
                    abstract="A real survey returned by the index.",
                )
            ]
        }
    )
    expert = ResearchExpert(CannedJSONLLMClient(_BRIEF_JSON), scholar_client=scholar)
    out = _run(expert, topic="efficient attention", discover=True)
    s = out.structured
    assert s is not None
    recent_titles = [n["title"] for n in s["recent"]]
    assert "Discovered Efficient Attention Survey" in recent_titles
    seeded = next(n for n in s["recent"] if n["title"] == "Discovered Efficient Attention Survey")
    assert seeded["grounded"] is True
    assert seeded["verified_title"] == "Discovered Efficient Attention Survey"


def test_research_echo_degrades_to_empty_brief() -> None:
    out = _run(ResearchExpert(), topic="efficient attention")
    assert "parse_error" in out.metadata
    assert out.metadata["num_sources"] == 0
    assert out.structured is not None
    assert out.structured["topic"] == "efficient attention"
    # No fabricated verified citations.
    assert out.metadata["grounded"] is False


def test_research_missing_topic_errors() -> None:
    out = _run(ResearchExpert(CannedJSONLLMClient(_BRIEF_JSON)))
    assert "error" in out.metadata
    assert out.structured is None


def test_research_section_outline_fallback() -> None:
    out = _run(
        ResearchExpert(CannedJSONLLMClient(_BRIEF_JSON)),
        section="Background",
        outline="Methods",
    )
    assert "error" not in out.metadata

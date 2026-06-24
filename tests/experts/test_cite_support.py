"""Hermetic tests for :class:`CiteSupportExpert` and claim-to-source faithfulness.

A canned LLM returns fenced verdict JSON so the abstract path is exercised
deterministically; the offline :class:`EchoLLMClient` exercises the
``unknown``/``None``-integrity degrade without raising; a fake resolver drives
deep (full-text) mode; missing prose/citations flag errors; and the score
aggregation + grounding composition are checked end to end.
"""

from __future__ import annotations

import json

from clio_author.experts.cite_support import (
    CiteSupportExpert,
    extract_claim_citations,
)
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.llm.client import EchoLLMClient


class CannedLLM:
    """Returns a fixed string regardless of the prompt."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        return self._response


_SUPPORTED = '```json\n{"verdict": "supported", "evidence": "see abstract", "rationale": "ok"}\n```'
_CONTRADICTED = (
    '```json\n{"verdict": "contradicted", "evidence": "opposite", "rationale": "no"}\n```'
)

# cite's verified-output shape: {citation_key, record:{title, abstract, external_ids}}
_CITATIONS = [
    {
        "citation_key": "vaswani2017attention",
        "record": {
            "title": "Attention Is All You Need",
            "abstract": "We propose the Transformer, based solely on attention.",
            "external_ids": {"ArXiv": "1706.03762"},
            "paper_id": "arxiv:1706.03762",
        },
    },
    {
        "citation_key": "noabs2020",
        "record": {"title": "No Abstract Here", "abstract": "", "external_ids": {}},
    },
]

_PROSE = (
    "The Transformer relies entirely on attention \\cite{vaswani2017attention}. "
    "It was the first to drop recurrence \\cite{noabs2020}."
)


def _task(**payload: object) -> Task:
    return Task(id="t", description="cite_support", payload={**payload, "action": "cite_support"})


def test_extract_claim_citations_pairs_each_key() -> None:
    pairs = extract_claim_citations(_PROSE)
    keys = [p.key for p in pairs]
    assert keys == ["vaswani2017attention", "noabs2020"]
    # the \cite{} token is stripped from the judged claim text
    assert "\\cite" not in pairs[0].claim
    assert "Transformer" in pairs[0].claim


def test_abstract_mode_scores_supported_and_flags_no_source() -> None:
    expert = CiteSupportExpert(CannedLLM(_SUPPORTED))
    out = expert.run(_task(text=_PROSE, citations=_CITATIONS), SessionContext(id="s"))

    assert out.structured is not None
    counts = out.metadata["counts"]
    # one pair judged "supported" against its abstract; the abstract-less key is no_source.
    assert counts["supported"] == 1
    assert counts["no_source"] == 1
    # integrity excludes the no_source pair -> 1 supported / 1 scored = 1.0
    assert out.metadata["support_integrity"] == 1.0
    assert out.metadata["mode"] == "abstract"
    assert json.loads(json.dumps(out.structured)) == out.structured


def test_contradiction_drags_the_score_down() -> None:
    expert = CiteSupportExpert(CannedLLM(_CONTRADICTED))
    out = expert.run(
        _task(text="A bold claim \\cite{vaswani2017attention}.", citations=_CITATIONS),
        SessionContext(id="s"),
    )
    assert out.metadata["counts"]["contradicted"] == 1
    assert out.metadata["support_integrity"] == 0.0  # contradicted scores 0


def test_deep_mode_uses_injected_full_text_resolver() -> None:
    seen: list[str] = []

    def resolver(key: str, entry: dict) -> str | None:
        seen.append(key)
        return "Full text proving the claim." if key == "vaswani2017attention" else None

    expert = CiteSupportExpert(CannedLLM(_SUPPORTED), full_text_resolver=resolver)
    out = expert.run(
        _task(
            text="Attention suffices \\cite{vaswani2017attention}.",
            citations=_CITATIONS,
            mode="deep",
        ),
        SessionContext(id="s"),
    )
    assert "vaswani2017attention" in seen  # resolver was consulted
    item = out.structured["items"][0]
    assert item["source_kind"] == "full_text"  # judged against full text, not abstract
    assert out.metadata["mode"] == "deep"


def test_echo_degrades_to_unknown_without_fabricating() -> None:
    expert = CiteSupportExpert(EchoLLMClient())
    out = expert.run(_task(text=_PROSE, citations=_CITATIONS), SessionContext(id="s"))
    # echo yields no parseable JSON -> the judged pair is "unknown", never "supported".
    assert out.metadata["counts"]["supported"] == 0
    assert out.metadata["counts"]["unknown"] >= 1
    assert out.metadata["support_integrity"] is None  # nothing scorable


def test_accepts_cite_saved_output_shape() -> None:
    # The full blob `clio-author cite --out cite.json` writes nests verified
    # under structured; cite_support must read it without reshaping by hand.
    saved = {"action": "cite", "structured": {"verified": _CITATIONS}}
    expert = CiteSupportExpert(CannedLLM(_SUPPORTED))
    out = expert.run(_task(text=_PROSE, citations=saved), SessionContext(id="s"))
    assert out.metadata["counts"]["supported"] == 1


def test_missing_inputs_are_error_flagged() -> None:
    expert = CiteSupportExpert(CannedLLM(_SUPPORTED))
    assert "error" in expert.run(_task(citations=_CITATIONS), SessionContext(id="s")).metadata
    assert "error" in expert.run(_task(text=_PROSE), SessionContext(id="s")).metadata


def test_writes_artifacts_under_out_dir(tmp_path) -> None:
    expert = CiteSupportExpert(CannedLLM(_SUPPORTED))
    out = expert.run(
        _task(text=_PROSE, citations=_CITATIONS, out_dir=str(tmp_path)), SessionContext(id="s")
    )
    assert (tmp_path / "cite_support.json").exists()
    assert (tmp_path / "cite_support.md").exists()
    assert any(str(tmp_path) in p for p in out.metadata["wrote"])


def test_ground_folds_in_support_integrity() -> None:
    from clio_author.experts.check_refs import CheckRefsExpert
    from clio_author.experts.grounding import run_grounding
    from clio_author.experts.verify_work import VerifyWorkExpert

    out = run_grounding(
        _task(text=_PROSE, citations=_CITATIONS),
        check_refs=CheckRefsExpert(),
        verify_work=VerifyWorkExpert(),
        cite_support=CiteSupportExpert(CannedLLM(_SUPPORTED)),
    )
    assert out.structured is not None
    # support integrity is computed and contributes to the headline number.
    assert out.structured["support_integrity"] == 1.0
    assert out.structured["support"]["counts"]["supported"] == 1
    assert out.metadata["grounding_integrity"] is not None

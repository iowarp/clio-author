"""Hermetic tests for the grounding-integrity action (`ground`).

Citation integrity is deterministic (offline): of the in-text `\\cite{}` keys,
how many resolve to a bibliography entry. Claim integrity is driven by a canned
LLM through `verify_work`. The headline `grounding_integrity` averages whichever
halves are available.
"""

from __future__ import annotations

import json
from pathlib import Path

from clio_author.agent import ClioAuthorAgent
from clio_author.experts.check_refs import CheckRefsExpert
from clio_author.experts.grounding import run_grounding
from clio_author.experts.verify_work import VerifyWorkExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task

_BIB = "@article{real,\n title={A Real Paper}, year={2020}\n}"


def _task(**payload: object) -> Task:
    return Task(id="t", description="ground", payload=dict(payload))


class _ClaimsLLM:
    """Returns a fixed verify_work JSON: 2 claims, 1 supported."""

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        return (
            '```json\n{"claims": ['
            '{"claim": "x", "made": true, "supported": true}, '
            '{"claim": "y", "made": true, "supported": false}]}\n```'
        )


def test_citation_integrity_offline() -> None:
    out = run_grounding(
        _task(bibtex=_BIB, text="We build on \\cite{real} and also \\cite{ghost}."),
        check_refs=CheckRefsExpert(),
        verify_work=VerifyWorkExpert(),
        session=SessionContext(id="s"),
    )
    assert out.metadata["citation_integrity"] == 0.5  # 1 of 2 cites resolves
    assert out.metadata["claim_integrity"] is None
    assert out.metadata["grounding_integrity"] == 0.5


def test_combines_citation_and_claim_halves() -> None:
    out = run_grounding(
        _task(bibtex=_BIB, text="See \\cite{real}.", claims=["x", "y"]),
        check_refs=CheckRefsExpert(),
        verify_work=VerifyWorkExpert(_ClaimsLLM()),
        session=SessionContext(id="s"),
    )
    assert out.metadata["citation_integrity"] == 1.0  # the one cite resolves
    assert out.metadata["claim_integrity"] == 0.5  # 1 of 2 claims supported
    assert out.metadata["grounding_integrity"] == 0.75  # mean of the two halves


def test_errors_without_bibtex_or_claims() -> None:
    out = run_grounding(
        _task(text="prose only"),
        check_refs=CheckRefsExpert(),
        verify_work=VerifyWorkExpert(),
        session=SessionContext(id="s"),
    )
    assert "error" in out.metadata


def test_persists_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "g"
    run_grounding(
        _task(bibtex=_BIB, text="See \\cite{real}.", out_dir=str(out_dir)),
        check_refs=CheckRefsExpert(),
        verify_work=VerifyWorkExpert(),
        session=SessionContext(id="s"),
    )
    report = json.loads((out_dir / "grounding.json").read_text())
    assert report["citation_integrity"] == 1.0
    assert (out_dir / "grounding.md").exists()


def test_agent_routes_ground() -> None:
    agent = ClioAuthorAgent()
    out = agent._invoke("ground", {"bibtex": _BIB, "text": "On \\cite{real} and \\cite{fake}."})
    assert out.agent == "grounding"
    assert out.metadata["citation_integrity"] == 0.5

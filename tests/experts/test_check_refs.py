"""Hermetic tests for :class:`CheckRefsExpert` (deterministic, no LLM)."""

from __future__ import annotations

from clio_author.experts.check_refs import CheckRefsExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Task

_BIB = """
@article{a, title = {On X}, author = {Y}, year = {2020}}
@article{b, title = {On Z}, year = {2021}}
@article{a, title = {Dup}, year = {2022}}
"""


def _run(payload: dict[str, object]) -> object:
    expert = CheckRefsExpert()  # offline echo, but no LLM call is made
    return expert.run(Task(id="t", description="check", payload=payload), SessionContext(id="s"))


def test_check_refs_deterministic_cross_check() -> None:
    out = _run({"bibtex": _BIB, "text": r"see \cite{a} and \cite{missing}"})
    assert out.agent == "check_refs"
    assert "error" not in out.metadata
    assert "parse_error" not in out.metadata
    s = out.structured
    assert s is not None
    assert s["missing_in_bib"] == ["missing"]
    assert "b" in s["uncited_entries"]  # b is in the bib but never cited
    assert s["duplicates"] == ["a"]
    assert s["counts"]["num_entries"] == 3


def test_check_refs_runs_identically_under_echo() -> None:
    # No LLM -> the result is the same whether or not a model is configured.
    out = _run({"bibtex": "@article{a, title = {X}}", "text": r"\cite{a}"})
    assert out.structured is not None
    assert out.structured["missing_in_bib"] == []
    assert out.structured["uncited_entries"] == []


def test_check_refs_scans_sections() -> None:
    out = _run(
        {
            "bibtex": "@article{a, title = {X}}",
            "sections": [{"title": "Intro", "draft": r"text \cite{a}"}],
        }
    )
    assert out.structured is not None
    assert out.structured["missing_in_bib"] == []


def test_check_refs_empty_payload_errors() -> None:
    out = _run({})
    assert "error" in out.metadata
    assert out.structured is None


def test_check_refs_prose_format() -> None:
    expert = CheckRefsExpert()
    out = expert.run(
        Task(
            id="t",
            description="check",
            payload={
                "bibtex": "@article{a, title={X}}",
                "text": r"\cite{missing}",
                "format": "prose",
            },
        ),
        SessionContext(id="s"),
    )
    # The expert itself returns structured; the prose rendering happens at the
    # agent layer, but the content is already a human summary.
    assert "issue" in out.content.lower()

"""Hermetic tests for :class:`CitationExpert`.

A :class:`FakeScholarClient` is injected so no network or ``thefuzz``/``httpx``
is touched. Covers the verified/suggestions-only output, the ``out_dir`` write,
the bibliography-safety refusals, the error paths (missing candidates, no
client, client raising), single-output discipline, and an Engine/Sequential run.
"""

from __future__ import annotations

import pytest

from clio_parser.experts.citation import CitationExpert
from clio_parser.harness.engine import Engine
from clio_parser.harness.patterns import Sequential
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import Task
from clio_parser.retrieval.scholar import FakeScholarClient, S2Record

_TITLE = "neural machine translation by jointly learning to align and translate"


def _record() -> S2Record:
    return S2Record(
        paper_id="p1",
        title=_TITLE,
        authors=["Dzmitry Bahdanau"],
        year=2015,
        abstract="We propose an attention mechanism for translation.",
        journal="ICLR",
    )


def _client() -> FakeScholarClient:
    return FakeScholarClient({_TITLE: [_record()]})


def _task(**payload: object) -> Task:
    base = {"candidates": [{"title": _TITLE, "year": 2015}]}
    base.update(payload)
    return Task(id="t", description="cite", payload=base)


class RaisingClient:
    def search_title(self, title, year_hint, cutoff_date):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


def test_verified_set_and_suggestions_only_structured() -> None:
    expert = CitationExpert(client=_client())
    session = SessionContext(id="s1")
    output = expert.run(_task(), session)

    assert output.agent == "citation"
    assert "error" not in output.metadata
    assert output.structured is not None
    verified = output.structured["verified"]
    assert len(verified) == 1
    assert verified[0]["record"]["paper_id"] == "p1"
    # Suggestions-only artifacts present.
    assert output.structured["suggested_bibtex"].startswith("@article{")
    assert output.structured["citation_map"] == {"bahdanau2015neuralmachine": _TITLE}
    cov = output.structured["coverage"]
    assert cov["meets_90pct"] is True
    assert output.metadata["num_candidates"] == 1
    assert output.metadata["num_verified"] == 1
    assert output.metadata["wrote"] == []
    assert session.history == [output]


def test_out_dir_writes_suggested_bib(tmp_path) -> None:  # type: ignore[no-untyped-def]
    expert = CitationExpert(client=_client())
    session = SessionContext(id="s2")
    output = expert.run(_task(out_dir=str(tmp_path)), session)

    assert "error" not in output.metadata
    bib = tmp_path / "suggested.bib"
    cmap = tmp_path / "suggested_citation_map.json"
    assert bib.exists()
    assert cmap.exists()
    assert bib.read_text().startswith("@article{")
    assert str(bib) in output.metadata["wrote"]
    assert str(cmap) in output.metadata["wrote"]


def test_refuses_to_touch_existing_references_bib(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A pre-existing user references.bib must be left untouched.
    user_bib = tmp_path / "references.bib"
    original = "@article{user2020, title={User Entry}}"
    user_bib.write_text(original)

    expert = CitationExpert(client=_client())
    session = SessionContext(id="s3")
    # suggested.bib does not collide with references.bib, so writing still
    # succeeds; the guard is verified separately below. Here we assert the
    # user's references.bib is never read/written by the expert.
    expert.run(_task(out_dir=str(tmp_path)), session)
    assert user_bib.read_text() == original


def test_refuses_existing_suggested_bib(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # An existing suggested.bib must not be clobbered.
    existing = tmp_path / "suggested.bib"
    original = "@article{existing, title={Existing}}"
    existing.write_text(original)

    expert = CitationExpert(client=_client())
    session = SessionContext(id="s3b")
    output = expert.run(_task(out_dir=str(tmp_path)), session)

    assert "error" in output.metadata
    assert "overwrite" in output.metadata["error"]
    assert existing.read_text() == original  # untouched
    assert session.history == [output]


def test_refuses_dangling_symlink_suggested_bib(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A dangling symlink suggested.bib -> references.bib must not be followed:
    # path.exists() is False for a broken link, so the old guard let the write
    # go through the link and create references.bib. The hardened guard refuses.
    link = tmp_path / "suggested.bib"
    target = tmp_path / "references.bib"
    link.symlink_to(target.name)  # target does not exist -> dangling link
    assert link.is_symlink()
    assert not target.exists()

    expert = CitationExpert(client=_client())
    session = SessionContext(id="s_symlink")
    output = expert.run(_task(out_dir=str(tmp_path)), session)

    assert "error" in output.metadata
    # The write was refused and references.bib was NOT created through the link.
    assert not target.exists()
    assert link.is_symlink()  # the dangling link itself is left untouched
    assert session.history == [output]


def test_missing_candidates_errors() -> None:
    expert = CitationExpert(client=_client())
    session = SessionContext(id="s4")
    output = expert.run(Task(id="t", description="cite", payload={}), session)

    assert output.content == ""
    assert "error" in output.metadata
    assert session.history == [output]


def test_empty_candidates_errors() -> None:
    expert = CitationExpert(client=_client())
    session = SessionContext(id="s4b")
    output = expert.run(Task(id="t", description="cite", payload={"candidates": []}), session)
    assert "error" in output.metadata


def test_no_client_errors() -> None:
    expert = CitationExpert()  # client defaults to None
    session = SessionContext(id="s5")
    output = expert.run(_task(), session)

    assert output.content == ""
    assert "error" in output.metadata
    assert "no scholar client configured" in output.metadata["error"]
    assert session.history == [output]


def test_client_raising_is_caught() -> None:
    expert = CitationExpert(client=RaisingClient())
    session = SessionContext(id="s6")
    output = expert.run(_task(), session)

    assert output.content == ""
    assert "error" in output.metadata
    assert "boom" in output.metadata["error"]
    assert session.history == [output]


def test_references_payload_key_accepted() -> None:
    expert = CitationExpert(client=_client())
    session = SessionContext(id="s7")
    task = Task(
        id="t",
        description="cite",
        payload={"references": [{"title": _TITLE, "year": 2015}]},
    )
    output = expert.run(task, session)
    assert "error" not in output.metadata
    assert output.metadata["num_verified"] == 1


def test_exactly_one_session_output() -> None:
    expert = CitationExpert(client=_client())
    session = SessionContext(id="s8")
    expert.run(_task(), session)
    assert len(session.history) == 1


def test_runs_through_engine_sequential() -> None:
    expert = CitationExpert(client=_client())
    engine = Engine()
    outputs = engine.run([expert], Sequential(), _task())

    assert len(outputs) == 1
    assert outputs[0].agent == "citation"
    assert outputs[0].structured is not None


def test_coverage_not_met_when_unverifiable() -> None:
    expert = CitationExpert(client=FakeScholarClient({}))  # knows nothing
    session = SessionContext(id="s9")
    task = Task(
        id="t",
        description="cite",
        payload={"candidates": [{"title": "unknown a"}, {"title": "unknown b"}]},
    )
    output = expert.run(task, session)
    assert output.metadata["num_verified"] == 0
    assert output.metadata["meets_90pct"] is False


def test_protected_basename_guard_refuses_references_bib(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # The safety guard refuses any write whose basename is references.bib, even
    # when no such file exists yet, and leaves the directory untouched.
    from clio_parser.experts import citation as citation_mod

    expert = CitationExpert(client=_client())
    # references.bib is in the protected set, so writing it must raise the
    # internal refusal (which run() converts to an error-flagged output).
    assert "references.bib" in citation_mod._PROTECTED_BASENAMES
    with pytest.raises(citation_mod._RefusedWriteError, match="protected"):
        expert._write_suggestions(tmp_path, "x", {}, bib_name="references.bib")
    assert not (tmp_path / "references.bib").exists()

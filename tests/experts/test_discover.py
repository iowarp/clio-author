"""Hermetic tests for the discovery expert and its CLI/adapter wiring.

:class:`DiscoverExpert` is deterministic (no LLM): a fake scholar client supplies
canned records, so the suite touches no network. The error paths (no client, no
query) and the ``out_dir`` persistence are exercised offline.
"""

from __future__ import annotations

import json

from clio_author.experts.discover import DiscoverExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Task
from clio_author.retrieval.scholar import FakeScholarClient, S2Record


def _task(**payload: object) -> Task:
    return Task(id="t", description="discover", payload=dict(payload))


def _client() -> FakeScholarClient:
    return FakeScholarClient(
        {
            "attention": [
                S2Record(
                    paper_id="p1",
                    title="Attention Is All You Need",
                    authors=["Ashish Vaswani"],
                    venue="NeurIPS",
                    year=2017,
                    abstract="Transformers use attention.",
                    external_ids={"ArXiv": "1706.03762"},
                ),
                S2Record(
                    paper_id="crossref:10.1/x",
                    title="BERT",
                    authors=["Jacob Devlin"],
                    year=2019,
                ),
            ]
        }
    )


def test_discover_returns_records() -> None:
    expert = DiscoverExpert(scholar_client=_client())
    out = expert.run(_task(query="attention"), SessionContext(id="s"))
    assert out.agent == "discover"
    assert "error" not in out.metadata
    assert out.structured is not None
    papers = out.structured["papers"]
    assert len(papers) == 2
    assert out.structured["count"] == 2
    assert out.metadata["count"] == 2
    assert papers[0]["title"] == "Attention Is All You Need"
    assert papers[0]["url"] == "https://arxiv.org/abs/1706.03762"


def test_discover_topic_key_also_accepted() -> None:
    expert = DiscoverExpert(scholar_client=_client())
    out = expert.run(_task(topic="attention"), SessionContext(id="s"))
    assert out.metadata["count"] == 2


def test_discover_no_client_is_error_flagged() -> None:
    session = SessionContext(id="s")
    out = DiscoverExpert(scholar_client=None).run(_task(query="x"), session)
    assert out.content == ""
    assert out.metadata["error"] == "no scholar client configured"
    assert session.history == [out]


def test_discover_no_query_is_error_flagged() -> None:
    out = DiscoverExpert(scholar_client=_client()).run(_task(), SessionContext(id="s"))
    assert "error" in out.metadata


def test_discover_respects_limit() -> None:
    expert = DiscoverExpert(scholar_client=_client())
    out = expert.run(_task(query="attention", limit=1), SessionContext(id="s"))
    assert out.metadata["count"] == 1


def test_discover_writes_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    expert = DiscoverExpert(scholar_client=_client())
    out = expert.run(_task(query="attention", out_dir=str(tmp_path)), SessionContext(id="s"))
    json_path = tmp_path / "discovered.json"
    bib_path = tmp_path / "discovered.bib"
    assert json_path.exists()
    assert bib_path.exists()
    assert str(json_path) in out.metadata["wrote"]
    assert str(bib_path) in out.metadata["wrote"]
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["count"] == 2
    assert "@" in bib_path.read_text(encoding="utf-8")


def test_discover_never_raises_on_bad_limit() -> None:
    out = DiscoverExpert(scholar_client=_client()).run(
        _task(query="attention", limit="oops"), SessionContext(id="s")
    )
    assert "error" not in out.metadata
    assert out.metadata["count"] == 2


# --------------------------------------------------------------------------- #
# Routing + prose + CLI                                                        #
# --------------------------------------------------------------------------- #
def test_discover_prose_lists_titles() -> None:
    from clio_author.agent import ClioAuthorAgent

    agent = ClioAuthorAgent(scholar_client=_client())
    out = agent.invoke(_with_action(_task(query="attention", format="prose")))
    assert out.structured is None
    assert out.metadata.get("format") == "prose"
    assert "Attention Is All You Need" in out.content
    assert "BERT" in out.content


def test_discover_runs_under_echo_agent_default_no_client() -> None:
    # The default agent has no scholar client -> discover degrades, never raises.
    from clio_author.agent import ClioAuthorAgent

    out = ClioAuthorAgent().invoke(_with_action(_task(query="x")))
    assert out.agent == "discover"
    assert out.metadata["error"] == "no scholar client configured"


def _with_action(task: Task) -> Task:
    return task.model_copy(update={"payload": {**task.payload, "action": "discover"}})

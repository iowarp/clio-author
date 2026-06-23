"""Hermetic tests for :class:`ClioAuthorAgent` routing.

Every action routes to the expected expert using the offline
:class:`EchoLLMClient` (and a :class:`FakeScholarClient` for citation), unknown
actions fall through to the echo expert, and the M0 ``invoke("hello world")``
back-compat path still returns the echo output. Convenience methods are checked
for building the right task.
"""

from __future__ import annotations

from clio_author.agent import ClioAuthorAgent
from clio_author.harness.types import AgentOutput, Task
from clio_author.retrieval.scholar import FakeScholarClient, S2Record

_CITE_TITLE = "neural machine translation by jointly learning to align and translate"


def _blocks_payload() -> dict[str, object]:
    """A minimal MemoryBlocks dump usable for ask/describe routing."""
    return {
        "metadata": {"title": "T"},
        "sections": [
            {
                "block_id": "s1",
                "section_path": "Introduction",
                "title": "Introduction",
                "text": "Background text about attention mechanisms.",
            }
        ],
        "figures": [{"figure_id": 1, "image_path": "figure1.png", "caption": "A bar chart."}],
    }


def _agent() -> ClioAuthorAgent:
    return ClioAuthorAgent(
        scholar_client=FakeScholarClient({_CITE_TITLE: []}),
    )


def _task(action: str, **payload: object) -> Task:
    return Task(id="t", description=action, payload={**payload, "action": action})


# --- per-action routing ----------------------------------------------------- #
def test_route_ingest() -> None:
    out = _agent().invoke(_task("ingest", source=""))
    assert out.agent == "ingestor"


def test_route_ask() -> None:
    out = _agent().invoke(_task("ask", question="What is attention?", blocks=_blocks_payload()))
    assert out.agent == "paper_qa"


def test_route_review() -> None:
    out = _agent().invoke(_task("review", paper="# Paper\nSome content."))
    assert out.agent == "reviewer"


def test_route_meta_review() -> None:
    out = _agent().invoke(_task("meta_review", reviews=[]))
    assert out.agent == "meta_reviewer"


def test_route_cite() -> None:
    agent = ClioAuthorAgent(
        scholar_client=FakeScholarClient(
            {_CITE_TITLE: [S2Record(paper_id="p1", title=_CITE_TITLE, year=2015)]}
        )
    )
    out = agent.invoke(_task("cite", candidates=[{"title": _CITE_TITLE, "year": 2015}]))
    assert out.agent == "citation"


def test_route_write() -> None:
    out = _agent().invoke(
        _task("write", outline={"title": "Intro", "section_path": "Introduction"}, source="src")
    )
    assert out.agent == "writer"


def test_route_edit() -> None:
    out = _agent().invoke(_task("edit", draft="Some prose.", review={"weaknesses": ["w"]}))
    assert out.agent == "editor"


def test_route_describe_figures() -> None:
    out = _agent().invoke(_task("describe_figures", blocks=_blocks_payload()))
    assert out.agent == "figure"
    assert out.metadata.get("mode") == "describe"


def test_route_plot() -> None:
    out = _agent().invoke(_task("plot", spec={"kind": "line", "intent": "trend"}))
    assert out.agent == "figure"
    assert out.metadata.get("mode") == "plot"


def test_route_kg() -> None:
    out = _agent().invoke(_task("kg", blocks=_blocks_payload()))
    assert out.agent == "kg"
    assert "num_nodes" in out.metadata


def test_route_write_review_loop() -> None:
    out = _agent().invoke(
        _task(
            "write_review",
            outline={"title": "Intro", "section_path": "Introduction"},
            source="src",
            max_rounds=1,
        )
    )
    assert isinstance(out, AgentOutput)
    assert out.agent in {"writer", "reviewer", "reviewer-critic"}


def test_route_figure_refine_loop() -> None:
    out = _agent().invoke(
        _task("figure_refine", spec={"kind": "line", "intent": "trend"}, max_rounds=1)
    )
    assert isinstance(out, AgentOutput)
    assert out.agent == "figure"


def test_route_research() -> None:
    out = _agent().invoke(_task("research", topic="attention mechanisms"))
    assert out.agent == "research"


def test_route_discover() -> None:
    agent = ClioAuthorAgent(
        scholar_client=FakeScholarClient(
            {"attention": [S2Record(paper_id="p1", title="Attention Is All You Need", year=2017)]}
        )
    )
    out = agent.invoke(_task("discover", query="attention"))
    assert out.agent == "discover"
    assert out.metadata["count"] == 1


def test_route_verify_work() -> None:
    out = _agent().invoke(
        _task("verify_work", claims=["X improves Y"], text="We show X improves Y.")
    )
    assert out.agent == "verify_work"


def test_route_check_refs() -> None:
    out = _agent().invoke(_task("check_refs", bibtex="@article{a,title={X}}", text="see \\cite{a}"))
    assert out.agent == "check_refs"
    assert "error" not in out.metadata  # deterministic, runs under echo


def test_route_audit() -> None:
    out = _agent().invoke(
        _task("audit", sections=[{"title": "Intro", "draft": "Some body text here."}])
    )
    assert out.agent == "audit"
    assert "error" not in out.metadata


def test_route_section_review() -> None:
    out = _agent().invoke(_task("section_review", text="## Intro\n\nSome content with \\cite{a}."))
    assert out.agent == "section_review"


# --- fallthrough + back-compat ---------------------------------------------- #
def test_unknown_action_falls_through_to_echo() -> None:
    out = _agent().invoke(_task("nonexistent", foo="bar"))
    assert out.agent == "echo"


def test_none_action_falls_through_to_echo() -> None:
    out = _agent().invoke(Task(id="t", description="hi", payload={}))
    assert out.agent == "echo"


def test_str_task_back_compat_echo() -> None:
    """The M0 contract: a bare str routes to echo and includes the text."""
    out = ClioAuthorAgent().invoke("hello world")
    assert out.agent == "echo"
    assert "hello world" in out.content


def test_invoke_never_raises_on_garbage_payload() -> None:
    # A garbage blocks value must produce an error-flagged output, not a raise.
    out = _agent().invoke(_task("ask", question="q", blocks="not-a-blocks-dump"))
    assert isinstance(out, AgentOutput)
    assert "error" in out.metadata


# --- convenience methods build the right task ------------------------------- #
def test_convenience_ingest() -> None:
    assert _agent().ingest("").agent == "ingestor"


def test_convenience_ask() -> None:
    out = _agent().ask("What is attention?", _blocks_payload())
    assert out.agent == "paper_qa"


def test_convenience_review() -> None:
    assert _agent().review("# Paper\ntext").agent == "reviewer"


def test_convenience_cite() -> None:
    agent = ClioAuthorAgent(scholar_client=FakeScholarClient({_CITE_TITLE: []}))
    assert agent.cite([{"title": _CITE_TITLE}]).agent == "citation"


def test_convenience_write() -> None:
    out = _agent().write(outline={"title": "Intro", "section_path": "Introduction"}, source="src")
    assert out.agent == "writer"


def test_convenience_edit() -> None:
    out = _agent().edit("Some prose.", {"weaknesses": ["w"]})
    assert out.agent == "editor"


def test_convenience_describe_figures() -> None:
    out = _agent().describe_figures(_blocks_payload())
    assert out.agent == "figure"
    assert out.metadata.get("mode") == "describe"


def test_convenience_plot() -> None:
    out = _agent().plot({"kind": "line", "intent": "trend"})
    assert out.agent == "figure"
    assert out.metadata.get("mode") == "plot"


def test_convenience_kg() -> None:
    out = _agent().kg(_blocks_payload())
    assert out.agent == "kg"


def test_prose_format_renders_meta_review_as_text() -> None:
    from clio_author.agent import ClioAuthorAgent
    from clio_author.harness.types import Task
    from uuid import uuid4

    agent = ClioAuthorAgent()  # offline echo; meta_review is deterministic
    out = agent.invoke(
        Task(
            id=uuid4().hex,
            description="meta_review",
            payload={
                "action": "meta_review",
                "format": "prose",
                "reviews": [
                    {"Overall": 7, "Decision": "Accept", "Strengths": ["clear"]},
                    {"Overall": 5, "Decision": "Reject", "Weaknesses": ["no baselines"]},
                ],
            },
        )
    )
    assert out.structured is None
    assert out.metadata.get("format") == "prose"
    assert "Meta-review" in out.content


def test_prose_format_renders_research_as_text() -> None:
    # Echo client yields an empty (parse_error) brief; the prose view still
    # renders the topic and drops the JSON.
    agent = ClioAuthorAgent()
    out = agent.invoke(_task("research", topic="attention", format="prose"))
    assert out.structured is None
    assert out.metadata.get("format") == "prose"


def test_prose_format_renders_check_refs_as_text() -> None:
    agent = ClioAuthorAgent()
    out = agent.invoke(
        _task("check_refs", bibtex="@article{a,title={X}}", text="\\cite{missing}", format="prose")
    )
    assert out.structured is None
    assert out.metadata.get("format") == "prose"
    assert "issue" in out.content.lower()

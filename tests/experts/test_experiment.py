"""Hermetic tests for the experiment expert (design extraction + eval planning).

A prompt-routing canned LLM returns design JSON for the extract phase and plan
JSON for the synthesis phase, so both phases are exercised offline. The
:class:`EchoLLMClient` path checks the graceful fallback (empty designs, no
raise), multi-paper grouping is verified from ``[label]`` section prefixes, and
the agent/CLI wiring is covered.
"""

from __future__ import annotations

import json
from pathlib import Path

from clio_author.agent import ClioAuthorAgent
from clio_author.experts.experiment import ExperimentExpert, render_plan_markdown
from clio_author.experts.experiment_models import EvaluationPlan, PaperDesign
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Message, Task
from clio_author.ingest.blocks import MemoryBlocks, SectionBlock

_DESIGN_JSON = """\
```json
{"research_questions": ["does it cache faster"],
 "architecture": ["LRU with admission filter"],
 "datasets": ["YCSB", "Twitter traces"],
 "baselines": ["ARC", "LRU"],
 "metrics": ["hit-rate", "p99 latency"],
 "ablations": ["remove admission filter"],
 "protocol": ["warm the cache, then replay the trace"],
 "compute": ["32-core server"],
 "limitations": ["single-node only"]}
```
"""

_PLAN_JSON = """\
```json
{"datasets": [{"name": "YCSB", "rationale": "standard KV workload", "source": "FastCache"}],
 "baselines": [{"name": "ARC", "rationale": "strong adaptive baseline", "source": "FastCache"}],
 "metrics": [{"name": "hit-rate", "rationale": "primary effectiveness metric", "source": "FastCache"}],
 "ablations": [{"name": "no-RL policy", "rationale": "isolate the RL contribution", "source": "suggested"}],
 "protocol": ["warm then replay"],
 "risks": ["trace overfitting"],
 "notes": "compare against ARC on YCSB first"}
```
"""


class RoutingLLM:
    """Returns design JSON for the extract phase, plan JSON for synthesis."""

    def complete(self, messages: list[Message], **kwargs: object) -> str:
        system = messages[0].content if messages else ""
        return _PLAN_JSON if "evaluation architect" in system else _DESIGN_JSON


def _task(**payload: object) -> Task:
    return Task(id="t", description="experiment", payload=dict(payload))


def _two_paper_blocks() -> MemoryBlocks:
    """A merged block set with two papers, gather-style `[label]` prefixes."""
    return MemoryBlocks(
        sections=[
            SectionBlock(section_path="[FastCache] Method", title="Method", text="LRU + filter."),
            SectionBlock(
                section_path="[FastCache] Experiments", title="Experiments", text="YCSB, ARC."
            ),
            SectionBlock(
                section_path="[SmartEvict] Architecture", title="Architecture", text="Two-tier."
            ),
        ]
    )


def test_errors_without_input() -> None:
    out = ExperimentExpert().run(_task(), SessionContext(id="s"))
    assert out.metadata["error"] == "no 'blocks'/'markdown'/'text'/'sources' provided"


def test_extract_only_groups_per_paper() -> None:
    expert = ExperimentExpert(RoutingLLM())
    out = expert.run(_task(blocks=_two_paper_blocks().model_dump()), SessionContext(id="s"))
    assert out.metadata["num_papers"] == 2
    assert out.metadata["has_plan"] is False
    labels = [d["paper"] for d in out.structured["designs"]]
    assert labels == ["FastCache", "SmartEvict"]
    # The routing LLM returns the design JSON, so fields are populated.
    assert out.structured["designs"][0]["datasets"] == ["YCSB", "Twitter traces"]
    assert out.structured["evaluation_plan"] is None


def test_recreate_plan_with_idea_and_persist(tmp_path: Path) -> None:
    expert = ExperimentExpert(RoutingLLM())
    out_dir = tmp_path / "exp"
    out = expert.run(
        _task(
            blocks=_two_paper_blocks().model_dump(),
            idea="An RL cache eviction policy",
            out_dir=str(out_dir),
        ),
        SessionContext(id="s"),
    )
    assert out.metadata["has_plan"] is True
    plan = out.structured["evaluation_plan"]
    assert plan["idea"] == "An RL cache eviction policy"
    assert plan["datasets"][0]["name"] == "YCSB"
    assert plan["datasets"][0]["source"] == "FastCache"
    # Rendered prose is the evaluation plan; artifacts persisted.
    assert "Evaluation plan" in out.content
    assert (out_dir / "evaluation_plan.md").exists()
    assert (out_dir / "evaluation_plan.json").exists()
    assert (out_dir / "experiment_designs.json").exists()
    designs = json.loads((out_dir / "experiment_designs.json").read_text())
    assert len(designs) == 2


def test_single_paper_from_markdown() -> None:
    expert = ExperimentExpert(RoutingLLM())
    out = expert.run(_task(markdown="# Paper\n\n## Method\n\nWe do X."), SessionContext(id="s"))
    assert out.metadata["num_papers"] == 1
    assert out.structured["designs"][0]["paper"] == "paper"


def test_echo_fallback_does_not_raise() -> None:
    # The offline echo client is not a real model; the point is that the expert
    # never raises and still returns a well-formed design for the paper.
    out = ExperimentExpert().run(_task(markdown="# P\n\n## Method\n\ntext"), SessionContext(id="s"))
    assert "error" not in out.metadata
    assert out.metadata["num_papers"] == 1
    design = out.structured["designs"][0]
    assert design["paper"] == "paper"
    assert set(PaperDesign(paper="paper").model_dump()) == set(design)


def test_agent_routes_and_auto_chains_sources(tmp_path: Path) -> None:
    (tmp_path / "ref.md").write_text("# Ref\n\n## Experiments\n\nWe test on X.\n", encoding="utf-8")
    agent = ClioAuthorAgent()
    out = agent.experiment(sources=[str(tmp_path / "ref.md")])
    assert out.agent == "experiment"
    # sources auto-gathered into one paper (echo LLM -> empty design, but routed).
    assert out.metadata["num_papers"] == 1


def test_render_plan_markdown_tables() -> None:
    plan = EvaluationPlan.from_loose_dict(
        json.loads(_PLAN_JSON.split("```json")[1].split("```")[0])
    )
    md = render_plan_markdown(plan)
    assert "## Datasets" in md and "| YCSB |" in md
    assert "## Threats to validity / risks" in md

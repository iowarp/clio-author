"""Hermetic tests for the context-gathering expert and its agent/CLI wiring.

:class:`~clio_author.experts.context.ContextExpert` (action ``gather``) is
deterministic and filesystem-only. These tests also cover the agent-level
``sources`` -> ``blocks`` auto-chaining (``_resolve_sources``) and the CLI
``--sources`` plumbing, all offline.
"""

from __future__ import annotations

import json
from pathlib import Path

from clio_author.agent import ClioAuthorAgent
from clio_author.experts.context import ContextExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import Task


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _task(**payload: object) -> Task:
    return Task(id="t", description="gather", payload=dict(payload))


def test_expert_errors_without_sources() -> None:
    out = ContextExpert().run(_task(), SessionContext(id="s"))
    assert out.metadata["error"] == "no 'sources' provided"


def test_expert_gathers_and_persists(tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "# A\n\nalpha\n")
    _write(tmp_path / "b.txt", "beta\n")
    out_dir = tmp_path / "out"
    out = ContextExpert().run(
        _task(sources=[str(tmp_path / "a.md"), str(tmp_path / "b.txt")], out_dir=str(out_dir)),
        SessionContext(id="s"),
    )
    assert out.metadata["error"] is None if "error" in out.metadata else True
    assert out.metadata["ingested"] == 2
    assert out.metadata["sections"] == 2
    # context.json is a pure MemoryBlocks dump -> a drop-in --blocks-file.
    ctx = json.loads((out_dir / "context.json").read_text())
    assert set(ctx) >= {"metadata", "sections", "figures"}
    assert (out_dir / "context.md").exists()
    # The structured payload carries the blocks plus provenance.
    assert out.structured["count"] == 2
    assert out.structured["blocks"]["sections"]


def test_agent_routes_gather(tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "# A\n\nx\n")
    out = ClioAuthorAgent().gather([str(tmp_path / "a.md")])
    assert out.agent == "context"
    assert out.metadata["ingested"] == 1


def test_agent_auto_chains_sources_into_blocks(tmp_path: Path) -> None:
    """A `sources` list on a grounding action is gathered into `blocks`."""
    _write(tmp_path / "a.md", "# Cache\n\nUse LRU eviction.\n")
    agent = ClioAuthorAgent()
    # `ask` with sources (no blocks): the echo answer must include the gathered text.
    result = agent._invoke(
        "ask", {"question": "what eviction?", "sources": [str(tmp_path / "a.md")]}
    )
    assert "LRU eviction" in result.content


def test_explicit_blocks_win_over_sources(tmp_path: Path) -> None:
    """When `blocks` is already supplied, `sources` is ignored (no gather)."""
    _write(tmp_path / "a.md", "# Cache\n\nUse LRU eviction.\n")
    agent = ClioAuthorAgent()
    explicit = {
        "metadata": {},
        "sections": [
            {"kind": "section", "section_path": "X", "title": "X", "text": "explicit-only"}
        ],
        "figures": [],
        "equations": [],
        "code_blocks": [],
    }
    result = agent._invoke(
        "ask",
        {"question": "q", "blocks": explicit, "sources": [str(tmp_path / "a.md")]},
    )
    assert "explicit-only" in result.content
    assert "LRU eviction" not in result.content

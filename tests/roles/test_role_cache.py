"""The result cache wired into role dispatch makes repeated tool calls free."""

from __future__ import annotations

from clio_author.agent import ClioAuthorAgent
from clio_author.integration import ClioAuthorSubagent
from clio_author.memory import ResultCache


def test_cached_dispatch_returns_hit_on_second_call(tmp_path) -> None:
    agent = ClioAuthorAgent()
    cache = ResultCache(tmp_path / "cache")
    dispatch = agent._cached_dispatch(cache, "echo")

    payload = {"markdown": "## Intro\n\nWe do X.", "bibtex": "@article{k,title={T},year={2020}}"}
    first = dispatch("audit", payload)  # runs the tool (deterministic)
    assert not first.metadata.get("cached")
    second = dispatch("audit", payload)  # served from cache
    assert second.metadata.get("cached") is True
    assert second.structured == first.structured  # same result


def test_errors_are_not_cached(tmp_path) -> None:
    agent = ClioAuthorAgent()
    cache = ResultCache(tmp_path / "cache")
    dispatch = agent._cached_dispatch(cache, "echo")

    out = dispatch("audit", {})  # missing inputs -> error, must not be cached
    assert "error" in out.metadata
    again = dispatch("audit", {})
    assert not again.metadata.get("cached")


def test_role_with_out_dir_writes_a_cache(tmp_path) -> None:
    sub = ClioAuthorSubagent()
    sub.run(
        "role",
        {
            "role": "verifier",
            "text": "X \\cite{k}.",
            "bibtex": "@article{k,title={T},year={2020}}",
            "out_dir": str(tmp_path),
        },
    )
    assert list((tmp_path / "cache").glob("*.json")), "no cached tool results written"

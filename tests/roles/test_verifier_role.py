"""Tests for the role framework and the verifier role (hermetic, echo model)."""

from __future__ import annotations

import json

from clio_author.integration import ClioAuthorSubagent


def test_verifier_consolidates_checks() -> None:
    sub = ClioAuthorSubagent()
    r = sub.run(
        "role",
        {
            "role": "verifier",
            "text": "Transformers beat RNNs \\cite{vaswani2017}.",
            "bibtex": "@article{vaswani2017, title={Attention}, author={V}, year={2017}}",
        },
    )
    assert r["action"] == "role"
    assert "error" not in r
    # ran the deterministic + grounding checks and rolled them into one report
    assert set(r["metadata"]["checks_run"]) >= {"audit", "coherence", "grounding"}
    assert r["metadata"]["grounding_integrity"] == 1.0
    assert json.loads(json.dumps(r)) == r  # serializable
    # points to the next role
    nxt = r["metadata"].get("suggested_next")
    assert nxt and nxt[0]["action"] == "role:refiner"


def test_verifier_runs_plan_check_when_plan_given() -> None:
    sub = ClioAuthorSubagent()
    plan = {
        "outline": {"title": "P", "sections": [{"title": "Intro"}]},
        "plans": [
            {
                "outline": {"title": "Intro", "word_budget": 200},
                "tasks": ["write"],
                "claims": ["X"],
                "sources": ["s"],
            }
        ],
    }
    r = sub.run("role", {"role": "verifier", "plan": plan})
    assert "plan_check" in r["metadata"]["checks_run"]
    assert r["metadata"]["plan_ok"] is True


def test_unknown_role_is_error_flagged() -> None:
    r = ClioAuthorSubagent().run("role", {"role": "nope"})
    assert "unknown role" in r["metadata"]["error"]


def test_empty_verifier_is_error_flagged() -> None:
    r = ClioAuthorSubagent().run("role", {"role": "verifier"})
    assert "error" in r["metadata"]


def test_capabilities_lists_roles() -> None:
    caps = ClioAuthorSubagent().capabilities()
    roles = {r["role"] for r in caps["roles"]}
    assert "verifier" in roles


def test_role_writes_report_to_project_memory(tmp_path) -> None:
    from clio_author.memory import ProjectMemory

    sub = ClioAuthorSubagent()
    sub.run(
        "role",
        {
            "role": "verifier",
            "text": "A claim \\cite{k}.",
            "bibtex": "@article{k, title={T}, year={2020}}",
            "out_dir": str(tmp_path),
        },
    )
    mem = ProjectMemory(tmp_path / "memory")
    assert mem.has("reports")
    assert "grounding" in mem.get("reports")

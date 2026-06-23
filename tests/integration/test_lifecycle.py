"""Tests for the author-lifecycle metadata on the capability manifest.

Every routed action must be assigned to at least one valid lifecycle phase and
carry a ``needs_source`` flag; the phase catalog must cover every action; and the
metadata must surface through ``capabilities()`` and the ``lifecycle`` CLI command.
"""

from __future__ import annotations

import json

import pytest

from clio_author.cli import main
from clio_author.integration import ClioAuthorSubagent
from clio_author.integration.manifest import (
    ACTIONS,
    PHASES,
    actions_for_phase,
    lifecycle_overview,
)


def test_every_action_has_valid_phase_and_needs_source() -> None:
    valid = {key for key, _ in PHASES}
    for entry in ACTIONS:
        assert entry["phase"], f"{entry['action']} has no phase"
        assert set(entry["phase"]) <= valid, f"{entry['action']} has an unknown phase"
        assert isinstance(entry["needs_source"], bool)


def test_every_phase_has_at_least_one_action() -> None:
    for key, _title in PHASES:
        assert actions_for_phase(key), f"phase {key} has no actions"


def test_lifecycle_overview_covers_all_actions() -> None:
    covered = {a for phase in lifecycle_overview() for a in phase["actions"]}
    assert covered == {entry["action"] for entry in ACTIONS}


def test_known_multi_phase_actions() -> None:
    by_action = {entry["action"]: set(entry["phase"]) for entry in ACTIONS}
    # `review` self-checks (strengthen) AND referees others.
    assert {"strengthen", "referee"} <= by_action["review"]
    # `revise` polishes the draft AND incorporates rebuttal feedback.
    assert {"strengthen", "respond"} <= by_action["revise"]
    # `experiment` surveys others' designs AND plans the new evaluation.
    assert {"frame", "plan"} <= by_action["experiment"]


def test_needs_source_is_the_minority() -> None:
    # The point of the lifecycle framing: most jobs do NOT require ingest first.
    need = [e["action"] for e in ACTIONS if e["needs_source"]]
    assert set(need) == {"ask", "kg", "experiment", "describe_figures"}


def test_capabilities_exposes_lifecycle() -> None:
    caps = ClioAuthorSubagent().capabilities()
    assert "lifecycle" in caps
    assert {p["phase"] for p in caps["lifecycle"]} == {k for k, _ in PHASES}
    for entry in caps["actions"]:
        assert "phase" in entry and "needs_source" in entry


def test_cli_lifecycle_command(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["lifecycle"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    phases = {p["phase"] for p in out["lifecycle"]}
    assert "strengthen" in phases and "referee" in phases
    strengthen = next(p for p in out["lifecycle"] if p["phase"] == "strengthen")
    assert "verify_work" in strengthen["actions"]

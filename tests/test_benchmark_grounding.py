"""Hermetic tests for the grounding-integrity benchmark harness.

Loads ``scripts/benchmark_grounding.py`` by path (it's a script, not a package
module) and checks the per-paper-error aggregation, the false-confidence count,
and a zero-arg run over the bundled sample (offline, deterministic citation half).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "benchmark_grounding.py"
_spec = importlib.util.spec_from_file_location("benchmark_grounding", _PATH)
assert _spec and _spec.loader
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


class _FakeSubagent:
    """Returns a fixed citation_integrity; claim half comes from the case ground-truth."""

    def __init__(self, citation_integrity: float) -> None:
        self._cit = citation_integrity

    def run(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"metadata": {"citation_integrity": self._cit, "claim_integrity": None}}


def test_run_case_means_citation_and_claim() -> None:
    case = {"name": "c", "markdown": "x", "bibtex": "y", "claim_integrity": 0.4}
    r = bench.run_case(_FakeSubagent(1.0), case)
    assert r["citation_integrity"] == 1.0
    assert r["claim_integrity"] == 0.4
    assert r["unified"] == pytest.approx(0.7)


def test_aggregate_mae_and_false_confidence() -> None:
    results = [
        # citation-only=1.0 but truth=0.7 -> false confidence; cite err 0.3, claim err 0.3
        {"name": "a", "citation_integrity": 1.0, "claim_integrity": 0.4, "unified": 0.7},
        # everything grounded -> no error, no false confidence
        {"name": "b", "citation_integrity": 1.0, "claim_integrity": 1.0, "unified": 1.0},
    ]
    agg = bench.aggregate(results)
    assert agg["n_cases"] == 2
    assert agg["citation_only_mae"] == pytest.approx(0.15)  # mean(|1.0-0.7|, |1.0-1.0|)
    assert agg["claim_only_mae"] == pytest.approx(0.15)  # mean(|0.4-0.7|, |1.0-1.0|)
    assert agg["false_confidence_cases"] == 1


def test_main_runs_on_bundled_sample(capsys: pytest.CaptureFixture[str]) -> None:
    code = bench.main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "AUTHOR" in out and "false-confidence" in out


def test_sample_cases_file_loads() -> None:
    cases = bench.load_cases(str(_PATH.parent.parent / "eval" / "grounding" / "cases.sample.json"))
    assert len(cases) == 4 and all("markdown" in c for c in cases)

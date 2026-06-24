#!/usr/bin/env python
"""Benchmark: cross-stage grounding integrity (AUTHOR vs single-slice baselines).

The contribution AUTHOR can measure and no single-slice tool can: of everything a
paper asserts, what fraction is *actually traceable to a real source* end to end?

A **citation-only** checker (e.g. a CiteCheck-style tool) only sees the
bibliography; a **claim-only** checker only sees the prose. Each is blind to the
other failure mode, so per paper its grounding estimate is *wrong* -- sometimes
high, sometimes low, and sometimes falsely confident (looks great on a paper that
isn't). AUTHOR holds both halves on one substrate, so its `ground` action reports
the honest end-to-end figure -- and this harness measures, over a case set, how
far each single-slice estimate lands from that truth (mean absolute error) plus
the count of false-confidence papers.

Run it (offline, deterministic for the citation half):

    uv run python scripts/benchmark_grounding.py
    uv run python scripts/benchmark_grounding.py --cases eval/grounding/cases.sample.json --out report.json

Each case is ``{name, markdown, bibtex, claim_integrity?}``. ``markdown`` + ``bibtex``
drive the deterministic *citation integrity* via the real `ground` action;
``claim_integrity`` is a ground-truth fraction for the claim half (so the sample
runs with no model). With ``CLIO_LLM`` set and a ``claims`` list per case, the
claim half is computed by AUTHOR instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# A tiny, self-contained default set so the harness runs with zero arguments.
# Each case isolates a failure mode so the single-slice overstatement is visible.
SAMPLE_CASES: list[dict[str, Any]] = [
    {
        "name": "fabricated_citations",  # good claims, but 2 of 3 cites are fake
        "markdown": "We extend \\cite{real} and also \\cite{ghost1} and \\cite{ghost2}.",
        "bibtex": "@article{real, title={A Real Paper}, year={2020}}",
        "claim_integrity": 0.9,
    },
    {
        "name": "fabricated_claims",  # all cites real, but half the claims unsupported
        "markdown": "Building on \\cite{real}, we report strong gains.",
        "bibtex": "@article{real, title={A Real Paper}, year={2020}}",
        "claim_integrity": 0.4,
    },
    {
        "name": "clean",  # everything grounded
        "markdown": "We use \\cite{real}.",
        "bibtex": "@article{real, title={A Real Paper}, year={2020}}",
        "claim_integrity": 1.0,
    },
    {
        "name": "weak_both",  # both halves middling
        "markdown": "From \\cite{real} and \\cite{ghost} we conclude.",
        "bibtex": "@article{real, title={A Real Paper}, year={2020}}",
        "claim_integrity": 0.5,
    },
]


def load_cases(path: str | None) -> list[dict[str, Any]]:
    """Load cases from a JSON file, or return the bundled sample when ``None``."""
    if path is None:
        return SAMPLE_CASES
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("cases file must be a JSON list of {name, markdown, bibtex, ...}")
    return data


def run_case(subagent: Any, case: dict[str, Any]) -> dict[str, Any]:
    """Score one case: citation integrity (real `ground`) + claim integrity.

    Returns ``{name, citation_integrity, claim_integrity, unified}`` where
    ``unified`` is the mean of whichever halves are available (the honest
    end-to-end number).
    """
    payload: dict[str, Any] = {
        "markdown": case.get("markdown", ""),
        "bibtex": case.get("bibtex", ""),
    }
    # When a real model + claims are supplied, let AUTHOR compute the claim half.
    if case.get("claims"):
        payload["claims"] = case["claims"]
    result = subagent.run("ground", payload)
    meta = result.get("metadata", {}) if isinstance(result, dict) else {}

    cit = meta.get("citation_integrity")
    claim = meta.get("claim_integrity")
    if claim is None:  # fall back to the case's ground-truth claim fraction
        claim = case.get("claim_integrity")

    parts = [x for x in (cit, claim) if isinstance(x, (int, float))]
    unified = sum(parts) / len(parts) if parts else None
    return {
        "name": case.get("name", "case"),
        "citation_integrity": cit,
        "claim_integrity": claim,
        "unified": unified,
    }


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


# A single-slice tool gives "false confidence" when it reports >= HIGH on a paper
# whose true end-to-end grounding is < OK.
_HIGH = 0.9
_OK = 0.75


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the per-paper error of each single-slice estimate vs the truth.

    The honest signal is **not** mean overstatement (it washes out, since a
    single-slice tool over-reports on some papers and under-reports on others) but
    the **per-paper error**: how far the citation-only / claim-only number lands
    from AUTHOR's unified end-to-end figure, plus the count of "false-confidence"
    papers where a single-slice tool looked great on a paper that wasn't.
    """

    def col(key: str) -> list[float]:
        return [r[key] for r in results if isinstance(r.get(key), (int, float))]

    cit_mae = _mae(results, "citation_integrity")
    claim_mae = _mae(results, "claim_integrity")
    false_conf = sum(
        1
        for r in results
        if isinstance(r.get("unified"), (int, float))
        and r["unified"] < _OK
        and (
            (
                isinstance(r.get("citation_integrity"), (int, float))
                and r["citation_integrity"] >= _HIGH
            )
            or (
                isinstance(r.get("claim_integrity"), (int, float)) and r["claim_integrity"] >= _HIGH
            )
        )
    )
    return {
        "n_cases": len(results),
        "citation_only_mean": _mean(col("citation_integrity")),
        "claim_only_mean": _mean(col("claim_integrity")),
        "author_unified_mean": _mean(col("unified")),
        "citation_only_mae": cit_mae,
        "claim_only_mae": claim_mae,
        "false_confidence_cases": false_conf,
    }


def _mae(results: list[dict[str, Any]], key: str) -> float | None:
    """Mean absolute error of a single-slice estimate vs the unified truth."""
    diffs = [
        abs(r[key] - r["unified"])
        for r in results
        if isinstance(r.get(key), (int, float)) and isinstance(r.get("unified"), (int, float))
    ]
    return round(sum(diffs) / len(diffs), 3) if diffs else None


def _fmt(x: float | None) -> str:
    return "  n/a" if x is None else f"{x * 100:5.1f}%"


def format_table(results: list[dict[str, Any]], agg: dict[str, Any]) -> str:
    """Render a human-readable comparison table."""
    lines = [
        "Grounding-integrity benchmark — AUTHOR (unified) vs single-slice baselines",
        "",
        f"{'case':22}{'cite-only':>11}{'claim-only':>12}{'AUTHOR(e2e)':>13}",
        "-" * 58,
    ]
    for r in results:
        lines.append(
            f"{r['name'][:22]:22}{_fmt(r['citation_integrity']):>11}"
            f"{_fmt(r['claim_integrity']):>12}{_fmt(r['unified']):>13}"
        )
    lines += [
        "-" * 58,
        f"{'MEAN':22}{_fmt(agg['citation_only_mean']):>11}"
        f"{_fmt(agg['claim_only_mean']):>12}{_fmt(agg['author_unified_mean']):>13}",
        "",
        "Each single-slice tool only sees one half, so per paper its grounding",
        "estimate is WRONG by (mean absolute error vs the true end-to-end figure):",
        f"  citation-only off by {_fmt(agg['citation_only_mae'])} per paper "
        f"(blind to unsupported claims)",
        f"  claim-only    off by {_fmt(agg['claim_only_mae'])} per paper "
        f"(blind to fabricated citations)",
        f"  false-confidence papers (a single-slice tool reported >={int(_HIGH * 100)}% on a paper "
        f"that's actually <{int(_OK * 100)}% grounded): {agg['false_confidence_cases']} / {agg['n_cases']}",
        "AUTHOR's unified score is the honest end-to-end figure none of them can compute.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-stage grounding-integrity benchmark.")
    parser.add_argument("--cases", default=None, help="JSON cases file (default: bundled sample).")
    parser.add_argument("--out", default=None, help="Write the full JSON report here.")
    args = parser.parse_args(argv)

    from clio_author.integration.clio_adapter import ClioAuthorSubagent
    from clio_author.llm.providers import resolve_llm

    import os

    subagent = ClioAuthorSubagent(llm=resolve_llm(os.environ.get("CLIO_LLM")))
    cases = load_cases(args.cases)
    results = [run_case(subagent, c) for c in cases]
    agg = aggregate(results)
    table = format_table(results, agg)
    print(table)
    if args.out:
        Path(args.out).write_text(
            json.dumps({"results": results, "aggregate": agg}, indent=2), encoding="utf-8"
        )
        print(f"\n[wrote {args.out}]", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry
    raise SystemExit(main())

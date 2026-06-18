"""Evaluation utilities: pure, hermetic metrics and report rendering.

This package turns processed scientific Markdown into coarse fidelity metrics
(:func:`compute_md_metrics`) and renders a comparison report across systems
(:func:`build_report`). Both are pure functions over strings/dicts -- no I/O,
no network -- so they belong in the default test suite. The real PDF -> Markdown
run that *feeds* these metrics is gated separately (see
``scripts/run_baseline_report.py`` and ``tests/baselines/``).
"""

from __future__ import annotations

from clio_author.eval.report import build_report, compute_md_metrics

__all__ = ["compute_md_metrics", "build_report"]

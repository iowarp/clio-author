"""Hermetic tests for the pure eval metric/report builders."""

from __future__ import annotations

from clio_author.eval import build_report, compute_md_metrics

# A small processed-Markdown fixture with known structural counts:
#   3 headings, 2 linked citations, 1 embedded figure, 1 table block, 2 refs.
FIXTURE = """\
# Introduction

Prior work [[1]](#ref-1) and [[2]](#ref-2) motivate this.

![Figure 1](./img/figure1.png)

Figure 1: A diagram.

## Results

| Metric | Value |
| --- | --- |
| Accuracy | 0.9 |

## References

<a id="ref-1"></a>[1] A. Author. A paper. 2024.

<a id="ref-2"></a>[2] B. Author. Another. 2023.
"""


def test_compute_md_metrics_known_counts() -> None:
    metrics = compute_md_metrics(FIXTURE)
    assert metrics == {
        "sections": 3,
        "linked_citations": 2,
        "figures": 1,
        "tables": 1,
        "references": 2,
    }


def test_compute_md_metrics_ignores_table_inside_code_fence() -> None:
    md = "```\n| A | B |\n| 1 | 2 |\n```\n\n| Real | Table |\n| --- | --- |\n| x | y |\n"
    metrics = compute_md_metrics(md)
    assert metrics["tables"] == 1


def test_compute_md_metrics_ignores_pipe_in_prose() -> None:
    # Prose / math / list pipes are not genuine tables and must not be counted.
    md = (
        "A paragraph with a | pipe in prose.\n\n"
        r"Set-builder math $\{x \mid x>0\}$ here." + "\n\n"
        "- item a | detail\n- item b | detail\n\n"
        "| Real | Table |\n| --- | --- |\n| x | y |\n"
    )
    metrics = compute_md_metrics(md)
    assert metrics["tables"] == 1


def test_compute_md_metrics_empty() -> None:
    metrics = compute_md_metrics("")
    assert metrics == {
        "sections": 0,
        "linked_citations": 0,
        "figures": 0,
        "tables": 0,
        "references": 0,
    }


def test_build_report_contains_systems_and_metrics() -> None:
    results = {
        "clio-author": {
            "sections": 5,
            "linked_citations": 10,
            "figures": 3,
            "tables": 2,
            "references": 20,
        },
        "reference": {
            "sections": 5,
            "linked_citations": 4,
            "figures": 3,
            "tables": 0,
            "references": 20,
        },
    }
    report = build_report(results)

    # Header row with humanized metric columns.
    assert "| System | Sections | Linked citations | Figures | Tables | References |" in report
    # A separator row and one data row per system.
    assert "| clio-author | 5 | 10 | 3 | 2 | 20 |" in report
    assert "| reference | 5 | 4 | 3 | 0 | 20 |" in report


def test_build_report_missing_metric_defaults_to_zero() -> None:
    report = build_report({"sys": {"sections": 1}})
    # Absent metrics render as 0, in METRIC_KEYS order.
    assert "| sys | 1 | 0 | 0 | 0 | 0 |" in report


def test_build_report_custom_title() -> None:
    report = build_report({}, title="My Title")
    assert report.startswith("# My Title")

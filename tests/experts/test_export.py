"""Hermetic tests for the ``export`` orchestration, adapter, and CLI wiring.

:func:`run_export` is a deterministic string transform plus best-effort
persistence; the adapter and CLI paths assert JSON-serializability and exit
codes. No network, no model.
"""

from __future__ import annotations

import json

from clio_parser.export.latex import run_export
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import Task
from clio_parser.integration.clio_adapter import ClioParserSubagent
from clio_parser.tools.files import SafeFiles

_SECTIONS = [
    {"title": "Intro", "draft": "**Hi** there with 90% and A & B."},
    {"title": "Method", "draft": "## Method\n\n- step one\n- step two"},
]


def _task(**payload: object) -> Task:
    return Task(id="t", description="export", payload=dict(payload))


def test_run_export_from_sections_returns_latex() -> None:
    out = run_export(_task(title="Paper", sections=_SECTIONS))
    assert out.agent == "export"
    assert "error" not in out.metadata
    assert out.structured is not None
    latex = out.structured["latex"]
    assert latex == out.content
    assert latex.startswith("\\documentclass{article}")
    assert "\\title{Paper}" in latex
    assert "\\section{Intro}" in latex
    assert "\\section{Method}" in latex
    assert "\\textbf{Hi}" in latex
    assert "90\\%" in latex
    assert out.metadata["format"] == "latex"


def test_run_export_dedupes_method_heading() -> None:
    out = run_export(_task(title="Paper", sections=_SECTIONS))
    assert out.content.count("\\section{Method}") == 1
    assert "\\item step one" in out.content


def test_run_export_title_defaults_from_outline() -> None:
    out = run_export(
        _task(outline={"title": "From Outline"}, sections=[{"title": "A", "draft": "x"}])
    )
    assert "\\title{From Outline}" in out.content


def test_run_export_title_defaults_untitled() -> None:
    out = run_export(_task(sections=[{"title": "A", "draft": "x"}]))
    assert "\\title{Untitled}" in out.content


def test_run_export_from_markdown_manuscript() -> None:
    md = "# Great Paper\n\n## Intro\n\nBody one.\n\n## Results\n\nBody two."
    out = run_export(_task(markdown=md))
    assert "\\title{Great Paper}" in out.content
    assert "\\section{Intro}" in out.content
    assert "\\section{Results}" in out.content


def test_run_export_with_bibtex() -> None:
    out = run_export(_task(title="T", sections=_SECTIONS, bibtex="@article{a, title={A}}"))
    assert out.structured is not None
    assert out.structured["bibtex"] == "@article{a, title={A}}"
    assert "\\bibliography{references}" in out.content


def test_run_export_suggested_bibtex_key() -> None:
    out = run_export(_task(title="T", sections=_SECTIONS, suggested_bibtex="@book{b}"))
    assert out.structured is not None
    assert out.structured["bibtex"] == "@book{b}"


def test_run_export_writes_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    files = SafeFiles(tmp_path)
    out = run_export(
        _task(title="T", sections=_SECTIONS, bibtex="@article{a}"),
        files=files,
    )
    tex = tmp_path / "paper.tex"
    bib = tmp_path / "references.bib"
    assert tex.exists()
    assert bib.exists()
    assert str(tex) in out.metadata["wrote"]
    assert str(bib) in out.metadata["wrote"]


def test_run_export_out_dir_in_payload(tmp_path) -> None:  # type: ignore[no-untyped-def]
    out = run_export(_task(title="T", sections=_SECTIONS, out_dir=str(tmp_path)))
    assert (tmp_path / "paper.tex").exists()
    assert str(tmp_path / "paper.tex") in out.metadata["wrote"]


def test_run_export_no_input_errors() -> None:
    session = SessionContext(id="s")
    out = run_export(_task(title="T"), session=session)
    assert out.content == ""
    assert "error" in out.metadata
    assert session.history == [out]


def test_run_export_bad_input_never_raises() -> None:
    # A non-list, non-string sections value and odd markdown must degrade, not raise.
    out = run_export(_task(sections=12345, markdown=None))
    assert "error" in out.metadata


# --------------------------------------------------------------------------- #
# Adapter + CLI                                                               #
# --------------------------------------------------------------------------- #
def test_adapter_export_is_json_serializable() -> None:
    sub = ClioParserSubagent()
    result = sub.run("export", {"title": "T", "sections": _SECTIONS})
    json.dumps(result)  # must not raise
    assert result["action"] == "export"
    assert result["metadata"]["format"] == "latex"
    assert "\\documentclass" in result["content"]


def test_capabilities_lists_export() -> None:
    sub = ClioParserSubagent()
    actions = {a["action"] for a in sub.capabilities()["actions"]}
    assert "export" in actions


def test_cli_export(capsys) -> None:  # type: ignore[no-untyped-def]
    from clio_parser.cli import main

    code = main(
        [
            "export",
            "--title",
            "T",
            "--sections-json",
            '[{"title": "Intro", "draft": "**Hi** there."}]',
        ]
    )
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert code == 0
    assert parsed["action"] == "export"
    assert "\\textbf{Hi}" in parsed["content"]
    assert parsed["structured"]["latex"].startswith("\\documentclass")

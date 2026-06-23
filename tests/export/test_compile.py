"""Tests for PDF compilation: hermetic (no-engine) + a gated live compile.

The no-engine path monkeypatches :func:`shutil.which` to ``None`` so the suite
stays hermetic and deterministic. The live compile is gated behind
``@pytest.mark.live`` and skipped unless a LaTeX engine is actually on PATH.
"""

from __future__ import annotations

import pytest

import clio_author.export.latex as latex_mod
from clio_author.export.latex import compile_pdf, find_latex_engine, run_export
from clio_author.harness.types import Task
from clio_author.tools.files import SafeFiles


def _task(**payload: object) -> Task:
    return Task(id="t", description="export", payload=dict(payload))


_SECTIONS = [{"title": "Intro", "draft": "Hello world."}]


def test_find_latex_engine_returns_str_or_none() -> None:
    engine = find_latex_engine()
    assert engine is None or isinstance(engine, str)


def test_compile_pdf_no_engine_returns_reason(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(latex_mod.shutil, "which", lambda _name: None)
    tex = tmp_path / "paper.tex"
    tex.write_text("\\documentclass{article}\\begin{document}hi\\end{document}\n")
    pdf, error = compile_pdf(tex)
    assert pdf is None
    assert error == "no LaTeX engine found"


def test_compile_pdf_missing_tex_returns_reason(tmp_path) -> None:  # type: ignore[no-untyped-def]
    pdf, error = compile_pdf(tmp_path / "absent.tex")
    assert pdf is None
    assert error is not None and "not found" in error


def test_export_pdf_no_engine_sets_pdf_error_without_failing(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(latex_mod.shutil, "which", lambda _name: None)
    files = SafeFiles(tmp_path)
    out = run_export(_task(title="T", sections=_SECTIONS, pdf=True), files=files)
    assert "error" not in out.metadata  # the export itself still succeeds
    assert out.metadata["pdf_error"] == "no LaTeX engine found"
    assert "pdf" not in out.metadata
    assert (tmp_path / "paper.tex").exists()  # .tex left intact


def test_export_pdf_without_out_dir_records_missing_tex(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # With an engine present but no out_dir, no paper.tex is written to compile.
    monkeypatch.setattr(latex_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    out = run_export(_task(title="T", sections=_SECTIONS, pdf=True))
    assert "error" not in out.metadata
    assert "pdf_error" in out.metadata


@pytest.mark.live
def test_compile_pdf_live(tmp_path) -> None:  # type: ignore[no-untyped-def]
    if find_latex_engine() is None:
        pytest.skip("no LaTeX engine on PATH")
    files = SafeFiles(tmp_path)
    out = run_export(_task(title="Live Paper", sections=_SECTIONS, pdf=True), files=files)
    assert out.metadata.get("pdf_error") is None, out.metadata.get("pdf_error")
    pdf = tmp_path / "paper.pdf"
    assert pdf.exists()
    assert pdf.stat().st_size > 0
    assert out.metadata["pdf"] == str(pdf)

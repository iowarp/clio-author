"""Hermetic tests for :class:`IngestorExpert`.

``process_pdf`` is monkeypatched to return a canned :class:`ExtractionResult`,
so no Docling/PyMuPDF/network access occurs. We assert the ``AgentOutput``
content/structured/metadata shape, the missing-deps error path, and that the
expert runs through :class:`Sequential` via :class:`Engine`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clio_parser.experts.ingestor import IngestorExpert
from clio_parser.harness.engine import Engine
from clio_parser.harness.patterns import Sequential
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import Task
from clio_parser.ingest import docling_extract
from clio_parser.ingest.docling_extract import ExtractionDependencyError, ExtractionResult

CANNED_MD = """\
# Sample Paper

Intro paragraph.

## 1. Methods

Method body.

## 2. Results

Result body.
"""


def _canned_result(images: list[Path] | None = None) -> ExtractionResult:
    return ExtractionResult(
        markdown=CANNED_MD,
        images=images or [],
        metadata={"extractor": "docling", "page_count": 7},
        extractor="docling",
        source_url="https://arxiv.org/pdf/2601.23265.pdf",
    )


def test_ingestor_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    img = tmp_path / "img" / "figure1.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\x89PNG")

    captured: dict[str, object] = {}

    def fake_process_pdf(source, out_dir=None, config=None):  # type: ignore[no-untyped-def]
        captured["source"] = source
        return _canned_result(images=[img])

    monkeypatch.setattr(docling_extract, "process_pdf", fake_process_pdf)

    expert = IngestorExpert()
    session = SessionContext(id="s1")
    task = Task(id="t1", description="ingest", payload={"source": "2601.23265"})
    output = expert.run(task, session)

    assert captured["source"] == "2601.23265"
    assert output.agent == "ingestor"
    assert output.content == CANNED_MD
    assert output.metadata["extractor"] == "docling"
    assert output.metadata["source_url"] == "https://arxiv.org/pdf/2601.23265.pdf"
    assert output.metadata["image_dir"] == str(img.parent)

    assert output.structured is not None
    section_paths = [s["section_path"] for s in output.structured["sections"]]
    assert section_paths == [
        "Sample Paper",
        "Sample Paper > Methods",
        "Sample Paper > Results",
    ]
    figures = output.structured["figures"]
    assert len(figures) == 1
    assert figures[0]["figure_id"] == 1
    assert figures[0]["image_path"] == "figure1.png"

    # Appended to the session exactly once.
    assert session.history == [output]


def test_ingestor_no_source(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("process_pdf should not be called without a source")

    monkeypatch.setattr(docling_extract, "process_pdf", fail)

    expert = IngestorExpert()
    session = SessionContext(id="s2")
    output = expert.run(Task(id="t", description="ingest", payload={}), session)

    assert "error" in output.metadata
    assert output.content == ""
    assert session.history == [output]


def test_ingestor_missing_deps_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_dep_error(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise ExtractionDependencyError("Docling is not installed.")

    monkeypatch.setattr(docling_extract, "process_pdf", raise_dep_error)

    expert = IngestorExpert()
    session = SessionContext(id="s3")
    task = Task(id="t", description="ingest", payload={"source": "2601.23265"})
    output = expert.run(task, session)

    assert output.content == ""
    assert "Docling is not installed." in output.metadata["error"]
    assert output.metadata["source"] == "2601.23265"
    assert session.history == [output]


def test_ingestor_unexpected_exception_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare (non-ExtractionError) failure must be caught, not propagated."""

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise Exception("boom")

    monkeypatch.setattr(docling_extract, "process_pdf", boom)

    expert = IngestorExpert()
    session = SessionContext(id="s4")
    task = Task(id="t", description="ingest", payload={"source": "2601.23265"})

    output = expert.run(task, session)  # must not raise

    assert output.content == ""
    assert "boom" in output.metadata["error"]
    assert output.metadata["source"] == "2601.23265"
    assert session.history == [output]


def test_ingestor_runs_through_engine_sequential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        docling_extract,
        "process_pdf",
        lambda source, out_dir=None, config=None: _canned_result(),
    )

    expert = IngestorExpert()
    engine = Engine()
    task = Task(id="t", description="ingest", payload={"source": "2601.23265"})
    outputs = engine.run([expert], Sequential(), task)

    assert len(outputs) == 1
    assert outputs[0].agent == "ingestor"
    assert outputs[0].content == CANNED_MD


def test_ingestor_writes_paper_md_and_blocks_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(docling_extract, "process_pdf", lambda *a, **k: _canned_result())
    out = tmp_path / "out"
    expert = IngestorExpert()
    output = expert.run(
        Task(id="t", description="ingest", payload={"source": "2601.23265", "out_dir": str(out)}),
        SessionContext(id="s"),
    )
    assert (out / "paper.md").read_text().startswith("# Sample Paper")
    import json as _json

    blocks = _json.loads((out / "blocks.json").read_text())
    assert "sections" in blocks
    assert str(out / "paper.md") in output.metadata["wrote"]
    assert output.metadata["out_dir"] == str(out)

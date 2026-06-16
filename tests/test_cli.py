"""Hermetic tests for the ``clio-parser`` CLI.

``capabilities`` prints the manifest and exits 0; an action with the offline
echo client prints a JSON result; malformed input degrades to an ``error`` JSON
dict (never a traceback) with a nonzero exit. Output is parsed back from stdout
to confirm it is valid JSON.
"""

from __future__ import annotations

import json

import pytest

from clio_parser.cli import main


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict]:
    code = main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_capabilities_prints_manifest_and_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, result = _run(capsys, ["capabilities"])
    assert code == 0
    assert result["name"] == "clio-parser"
    assert any(entry["action"] == "ingest" for entry in result["actions"])


def test_review_action_prints_json_result(capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(capsys, ["review", "--paper", "# Paper\nSome content."])
    assert code == 0
    assert result["action"] == "review"
    assert set(result) == {"action", "content", "structured", "metadata"}


def test_ingest_empty_source_is_error_json(capsys: pytest.CaptureFixture[str]) -> None:
    # An empty source makes the ingestor flag an error -> nonzero exit, JSON dict.
    code, result = _run(capsys, ["ingest", ""])
    assert code == 1
    assert "error" in result["metadata"]


def test_bad_json_payload_degrades_to_error_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, result = _run(capsys, ["ask", "--question", "q", "--blocks-json", "{not json"])
    assert code == 1
    assert "error" in result
    assert "invalid JSON" in result["error"]


def test_ask_with_blocks_json_routes(capsys: pytest.CaptureFixture[str]) -> None:
    blocks = json.dumps(
        {
            "metadata": {"title": "T"},
            "sections": [
                {
                    "block_id": "s1",
                    "section_path": "Introduction",
                    "title": "Introduction",
                    "text": "Attention is all you need.",
                }
            ],
            "figures": [],
        }
    )
    code, result = _run(
        capsys, ["ask", "--question", "What is attention?", "--blocks-json", blocks]
    )
    assert code == 0
    assert result["action"] == "ask"


def test_run_dispatches_meta_review(capsys: pytest.CaptureFixture[str]) -> None:
    # The generic `run` escape hatch reaches an action with no dedicated subcommand.
    code, result = _run(capsys, ["run", "meta_review", "--json", '{"reviews": []}'])
    assert result["action"] == "meta_review"
    assert set(result) >= {"action", "content", "structured", "metadata"}
    # Exit code follows the standard error rule (0 unless the result flags an error).
    assert code == (1 if "error" in result or "error" in result["metadata"] else 0)


def test_run_bad_json_degrades_to_error_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(capsys, ["run", "meta_review", "--json", "{not json"])
    assert code == 1
    assert "error" in result
    assert "invalid JSON" in result["error"]
    # No traceback leaked to stderr.
    assert "Traceback" not in capsys.readouterr().err


def test_run_plot_reaches_figure_expert(capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(
        capsys,
        ["run", "plot", "--json", '{"spec": {"kind": "line", "title": "Demo"}}'],
    )
    assert result["action"] == "plot"
    assert set(result) >= {"action", "content", "structured", "metadata"}
    assert code == (1 if "error" in result or "error" in result["metadata"] else 0)


def test_write_accepts_outline_flag(capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(capsys, ["write", "--outline", "1. Intro\n2. Method"])
    assert code == 0
    assert result["action"] == "write"


def test_cli_clio_llm_env_accepted_for_capabilities(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # CLIO_LLM selects a real provider; `capabilities` builds it but never invokes it.
    monkeypatch.setenv("CLIO_LLM", "claude")
    code, result = _run(capsys, ["capabilities"])
    assert code == 0
    assert len(result["actions"]) == 11


def test_cli_invalid_clio_llm_degrades_to_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLIO_LLM", "bogus-model")
    code, result = _run(capsys, ["capabilities"])
    assert code == 1
    assert "error" in result and "CLIO_LLM" in result["error"]


def test_default_out_dir_slug() -> None:
    from clio_parser.cli import _default_out_dir

    assert _default_out_dir("2601.23265") == "clio-out/2601.23265"
    assert _default_out_dir("Attention Is All You Need") == "clio-out/Attention-Is-All-You-Need"


def test_review_prose_format_flag(capsys: pytest.CaptureFixture[str]) -> None:
    # echo client (offline) + prose format: content is returned, no error, exit 0.
    code, result = _run(capsys, ["review", "--paper", "# P\n\nbody", "--format", "prose"])
    assert code == 0
    assert result["structured"] is None
    assert result["metadata"]["format"] == "prose"


def test_ask_prose_format(capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(
        capsys,
        ["ask", "--question", "what?", "--blocks-json", '{"sections": []}', "--format", "prose"],
    )
    assert code == 0
    assert result["structured"] is None
    assert result["metadata"].get("format") == "prose"

"""Hermetic tests for the ``clio-author`` CLI.

``capabilities`` prints the manifest and exits 0; an action with the offline
echo client prints a JSON result; malformed input degrades to an ``error`` JSON
dict (never a traceback) with a nonzero exit. Output is parsed back from stdout
to confirm it is valid JSON.
"""

from __future__ import annotations

import json
import os

import pytest

from clio_author.cli import _load_cli_env, main


@pytest.fixture(autouse=True)
def _disable_local_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep developer .env.local files from affecting hermetic CLI tests."""
    monkeypatch.setenv("CLIO_ENV_FILE", "/__clio_author_test_no_env__")


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict]:
    code = main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_capabilities_prints_manifest_and_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, result = _run(capsys, ["capabilities"])
    assert code == 0
    assert result["name"] == "clio-author"
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


def test_kg_command_routes_with_blocks_json(capsys: pytest.CaptureFixture[str]) -> None:
    blocks = json.dumps(
        {
            "metadata": {"title": "T"},
            "sections": [
                {
                    "section_path": "Methods",
                    "title": "Methods",
                    "text": "We use a transformer evaluated on GLUE.",
                }
            ],
            "figures": [],
        }
    )
    code, result = _run(capsys, ["kg", "--blocks-json", blocks])
    assert code == 0
    assert result["action"] == "kg"
    assert "num_nodes" in result["metadata"]


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
    assert len(result["actions"]) == 16


def test_cli_invalid_clio_llm_degrades_to_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLIO_LLM", "unsupported-provider")
    code, result = _run(capsys, ["capabilities"])
    assert code == 1
    assert "error" in result and "CLIO_LLM" in result["error"]


def test_cli_loads_env_local(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLIO_ENV_FILE", raising=False)
    (tmp_path / ".env.local").write_text("CLIO_LLM=unsupported-provider\n", encoding="utf-8")

    old = os.environ.pop("CLIO_LLM", None)
    try:
        _load_cli_env()
        assert os.environ["CLIO_LLM"] == "unsupported-provider"
    finally:
        os.environ.pop("CLIO_LLM", None)
        if old is not None:
            os.environ["CLIO_LLM"] = old


def test_cli_env_file_does_not_override_real_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLIO_ENV_FILE", raising=False)
    (tmp_path / ".env.local").write_text("CLIO_LLM=unsupported-provider\n", encoding="utf-8")

    old = os.environ.get("CLIO_LLM")
    os.environ["CLIO_LLM"] = "echo"
    try:
        _load_cli_env()
        assert os.environ["CLIO_LLM"] == "echo"
    finally:
        if old is None:
            os.environ.pop("CLIO_LLM", None)
        else:
            os.environ["CLIO_LLM"] = old


def test_cli_loads_explicit_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    env_file = tmp_path / "clio.env"
    env_file.write_text("export CLIO_LLM='unsupported-provider'\n", encoding="utf-8")
    monkeypatch.setenv("CLIO_ENV_FILE", str(env_file))

    old = os.environ.pop("CLIO_LLM", None)
    try:
        _load_cli_env()
        assert os.environ["CLIO_LLM"] == "unsupported-provider"
    finally:
        os.environ.pop("CLIO_LLM", None)
        if old is not None:
            os.environ["CLIO_LLM"] = old


def test_default_out_dir_slug() -> None:
    from clio_author.cli import _default_out_dir

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


def test_ask_reads_blocks_from_file(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    blocks = tmp_path / "blocks.json"
    blocks.write_text(
        '{"metadata": {}, "sections": [{"section_path": "S", "title": "S", "text": "X is a method."}]}'
    )
    code, result = _run(capsys, ["ask", "--question", "what is X?", "--blocks-file", str(blocks)])
    assert code == 0
    assert result["action"] == "ask"


def test_write_accepts_format_flag(capsys: pytest.CaptureFixture[str]) -> None:
    # `--format` must be accepted on write (regression: it was only on ask/review/cite).
    code, result = _run(
        capsys, ["write", "--outline", "Intro", "--source", "facts", "--format", "prose"]
    )
    assert result["action"] == "write"


def test_review_reads_paper_from_file(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    paper = tmp_path / "paper.md"
    paper.write_text("# Title\n\nAbstract and method.")
    code, result = _run(capsys, ["review", "--paper-file", str(paper)])
    assert result["action"] == "review"


def test_bad_blocks_file_degrades_to_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(capsys, ["ask", "--question", "q", "--blocks-file", "/no/such/file.json"])
    assert code == 1
    assert "error" in result

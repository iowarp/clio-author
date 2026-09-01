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


def test_orchestrate_action_prints_json_result(capsys: pytest.CaptureFixture[str]) -> None:
    # The echo planner does not parse -> error-flagged "could not plan" (exit 1),
    # but the command runs cleanly and prints a JSON result dict.
    code, result = _run(capsys, ["orchestrate", "--goal", "ingest then review"])
    assert code == 1
    assert result["action"] == "orchestrate"
    assert result["metadata"]["error"] == "could not plan for goal"


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


def test_out_append_builds_a_running_log(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    log = tmp_path / "log.md"
    for q in ("first question?", "second question?"):
        main(
            [
                "ask",
                "--question",
                q,
                "--text",
                "# P\n\n## S\n\nbody",
                "--all",
                "--format",
                "prose",
                "--out",
                str(log),
                "--append",
            ]
        )
        capsys.readouterr()  # drain stdout between runs
    text = log.read_text(encoding="utf-8")
    assert "## first question?" in text and "## second question?" in text  # both entries, headered
    assert "_trace:" in text and "action=ask" in text  # trace metadata per entry
    assert "\n---\n" in text  # separator between the two entries


def test_out_append_json_is_json_lines(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    log = tmp_path / "log.json"  # .json + --append -> JSON Lines (one object per line)
    for _ in range(2):
        main(["review", "--paper", "# P\nbody", "--out", str(log), "--append"])
        capsys.readouterr()
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2 and all(json.loads(ln)["action"] == "review" for ln in lines)


def test_ground_reachable_via_run(capsys: pytest.CaptureFixture[str]) -> None:
    # `ground` is now internal plumbing for the verifier role; reach it via `run`.
    code, result = _run(
        capsys,
        [
            "run",
            "ground",
            "--json",
            json.dumps(
                {
                    "bibtex": "@article{a,title={X},year={2020}}",
                    "text": "We build on \\cite{a} and also \\cite{ghost}.",
                }
            ),
        ],
    )
    assert code == 0
    assert result["action"] == "ground"
    assert result["metadata"]["citation_integrity"] == 0.5


def test_verifier_role_rolls_up_grounding(capsys: pytest.CaptureFixture[str]) -> None:
    # The user-facing path for grounding is now the verifier role.
    code, result = _run(
        capsys,
        [
            "role",
            "verifier",
            "--text",
            "We build on \\cite{a}.",
            "--json",
            json.dumps({"bibtex": "@article{a,title={X},year={2020}}"}),
        ],
    )
    assert result["action"] == "role"
    assert "grounding" in result["structured"]


def test_revise_command_style_mode(capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(
        capsys, ["revise", "--mode", "style", "--text", "Our system is fast.", "--voice", "concise"]
    )
    assert code == 0
    assert result["action"] == "revise"


def test_revise_command_feedback_mode(capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(
        capsys,
        ["revise", "--text", "We propose X.", "--review-json", '{"weaknesses":["no baseline"]}'],
    )
    assert code == 0
    assert result["action"] == "revise"


def test_cli_clio_llm_env_accepted_for_capabilities(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # CLIO_LLM selects a real provider; `capabilities` builds it but never invokes it.
    monkeypatch.setenv("CLIO_LLM", "claude")
    code, result = _run(capsys, ["capabilities"])
    assert code == 0
    assert len(result["actions"]) == 24


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


def test_out_flag_writes_prose_and_json(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    # .md path -> prose content; .json path -> full JSON. Uses offline echo (no model).
    md = tmp_path / "review.md"
    code, _ = _run(
        capsys, ["review", "--paper", "# T\n\nAbstract.", "--format", "prose", "--out", str(md)]
    )
    assert md.exists() and md.read_text().strip()  # prose written

    js = tmp_path / "review.json"
    _run(capsys, ["review", "--paper", "# T\n\nAbstract.", "--out", str(js)])
    import json as _json

    obj = _json.loads(js.read_text())  # full JSON written + parseable
    assert obj["action"] == "review"


def test_out_flag_available_on_ask(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    p = tmp_path / "ans.md"
    _run(
        capsys,
        [
            "ask",
            "--question",
            "what?",
            "--blocks-json",
            '{"sections":[{"section_path":"S","title":"S","text":"x"}]}',
            "--out",
            str(p),
        ],
    )
    assert p.exists()


def test_gather_command_routes_and_persists(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    doc = tmp_path / "a.md"
    doc.write_text("# Title\n\nbody\n", encoding="utf-8")
    out_dir = tmp_path / "ctx"
    code, result = _run(capsys, ["gather", "--sources", str(doc), "--out-dir", str(out_dir)])
    assert code == 0
    assert result["action"] == "gather"
    assert result["metadata"]["ingested"] == 1
    assert (out_dir / "context.json").exists()


def test_gather_sources_file_newlines(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    listing = tmp_path / "srcs.txt"
    listing.write_text(f"# comment\n{tmp_path / 'a.md'}\n{tmp_path / 'b.md'}\n", encoding="utf-8")
    code, result = _run(capsys, ["gather", "--sources-file", str(listing)])
    assert code == 0
    assert result["metadata"]["ingested"] == 2


def test_plan_sources_auto_chains(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    doc = tmp_path / "ctx.md"
    doc.write_text("# Cache\n\nUse LRU eviction.\n", encoding="utf-8")
    code, result = _run(
        capsys,
        ["plan", "--idea", "a fast cache", "--sources", str(doc)],
    )
    assert code == 0
    assert result["action"] == "plan"
    assert result["structured"]["plans"]


def test_sources_from_args_json_array(tmp_path) -> None:
    from clio_author.cli import _sources_from_args

    listing = tmp_path / "srcs.json"
    listing.write_text('["x.md", "y.md"]', encoding="utf-8")

    class _NS:
        sources = None
        sources_file = str(listing)

    assert _sources_from_args(_NS()) == ["x.md", "y.md"]


def test_experiment_command_routes(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    ref = tmp_path / "ref.md"
    ref.write_text("# Ref\n\n## Experiments\n\nWe test on X with metric Y.\n", encoding="utf-8")
    code, result = _run(
        capsys,
        [
            "experiment",
            "--sources",
            str(ref),
            "--idea",
            "a new method",
            "--out-dir",
            str(tmp_path / "e"),
        ],
    )
    assert code == 0
    assert result["action"] == "experiment"
    assert result["metadata"]["num_papers"] == 1
    assert result["metadata"]["has_plan"] is True


def test_plan_action_with_outline_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(
        capsys,
        [
            "plan",
            "--idea",
            "study things",
            "--outline-json",
            '{"title":"T","sections":[{"title":"A","goal":"g"}]}',
        ],
    )
    assert code == 0
    assert result["action"] == "plan"
    assert result["structured"]["plans"]
    assert result["metadata"]["num_sections"] == 1


def _run_with_stderr(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict, str]:
    """Run the CLI and return ``(exit_code, parsed stdout, stderr)``."""
    code = main(argv)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_stub_model_warning_on_a_model_backed_command(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An echo-stub run exits 0 with a plausible payload; say so on stderr."""
    monkeypatch.delenv("CLIO_LLM", raising=False)
    _, _, err = _run_with_stderr(capsys, ["review", "--paper", "# Paper\nBody."])

    assert "offline 'echo' stub" in err


def test_no_stub_warning_for_deterministic_commands(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`audit` never calls the model, so running it on the stub is correct."""
    monkeypatch.delenv("CLIO_LLM", raising=False)
    _, _, err = _run_with_stderr(capsys, ["audit", "--markdown-file", os.devnull])

    assert "echo" not in err


def test_no_stub_warning_when_a_real_model_is_selected(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLIO_LLM", "ollama")
    _, _, err = _run_with_stderr(capsys, ["review", "--paper", "# Paper\nBody."])

    assert "echo" not in err


def test_write_skipped_is_warned_and_force_overwrites(
    capsys: pytest.CaptureFixture[str], tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-run into a populated out_dir must not look like a successful write."""
    monkeypatch.delenv("CLIO_LLM", raising=False)
    out_dir = str(tmp_path / "ship")
    argv = [
        "export",
        "--title",
        "T",
        "--sections-json",
        '[{"title":"Intro","draft":"v1"}]',
        "--out-dir",
        out_dir,
    ]
    _, first, _ = _run_with_stderr(capsys, argv)
    assert first["metadata"]["wrote"]

    _, second, err = _run_with_stderr(capsys, argv)
    assert second["metadata"]["wrote"] == []
    assert second["metadata"]["write_skipped"] == ["paper.tex: already exists"]
    assert "NOT written" in err

    _, third, _ = _run_with_stderr(capsys, [*argv, "--force"])
    assert third["metadata"]["wrote"]
    assert "write_skipped" not in third["metadata"]

"""Command-line entry point so a host can invoke clio-parser as a subprocess.

Each subcommand builds a payload (from a ``--json`` blob and/or specific flags),
calls :meth:`~clio_parser.integration.clio_adapter.ClioParserSubagent.run` (or
``capabilities``), prints the result as indented JSON, and returns an exit code
(``0`` on success, ``1`` when the result carries an ``error``).

A generic ``run <action>`` subcommand dispatches *any* adapter action by name
(including those without a dedicated subcommand, e.g. ``meta_review``, ``edit``,
``plot``, ``write_review``, ``figure_refine``), seeding the payload from
``--json``, so the full adapter surface is reachable over subprocess.

The CLI degrades to error dicts rather than tracebacks: malformed ``--json`` and
any unexpected failure are printed as ``{"error": ...}`` JSON. Imports of the
adapter are lazy so ``--help`` and argument parsing stay cheap.

The model is selected by the ``CLIO_LLM`` environment variable
(``echo`` (default, offline) | ``claude`` | ``codex`` | ``ollama``); the model
name comes from ``CLIO_LLM_MODEL`` and the Ollama URL from ``CLIO_OLLAMA_URL``.
The default ``echo`` keeps the CLI fully offline unless a real model is requested.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _default_out_dir(source: str) -> str:
    """Default visible output dir for ``ingest`` -> ``clio-out/<slug-of-source>``."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", source.strip()).strip("-")[:64] or "paper"
    return f"clio-out/{slug}"


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with one subcommand per supported action."""
    parser = argparse.ArgumentParser(
        prog="clio-parser",
        description="Invoke clio-parser experts as a standalone subagent.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("capabilities", help="Print the subagent capability manifest.")

    def _add_json(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--json",
            dest="json_payload",
            default=None,
            help="A JSON object merged into the action payload.",
        )

    def _add_format(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--format",
            dest="fmt",
            choices=("structured", "prose"),
            default="structured",
            help="structured = JSON (default, for host agents); prose = plain text (for humans).",
        )

    p_ingest = sub.add_parser(
        "ingest", help="Ingest an arXiv id / URL / PDF / paper title into Markdown."
    )
    p_ingest.add_argument(
        "source", help="arXiv id, URL, local PDF path, or a paper title/topic to ingest."
    )
    _add_json(p_ingest)

    p_ask = sub.add_parser("ask", help="Answer a question grounded in memory blocks.")
    p_ask.add_argument("--question", required=True, help="The question to answer.")
    p_ask.add_argument(
        "--blocks-json",
        dest="blocks_json",
        default=None,
        help="A JSON MemoryBlocks dump (inline) to ground the answer in.",
    )
    p_ask.add_argument(
        "--blocks-file",
        dest="blocks_file",
        default=None,
        help="Path to a JSON MemoryBlocks file (use this for real papers, e.g. "
        "clio-out/<id>/blocks.json — avoids command-line length limits).",
    )
    _add_format(p_ask)
    _add_json(p_ask)

    p_review = sub.add_parser("review", help="Produce a peer review of a paper.")
    p_review.add_argument("--paper", default=None, help="The paper Markdown text (inline).")
    p_review.add_argument(
        "--paper-file",
        dest="paper_file",
        default=None,
        help="Path to a paper Markdown file (e.g. clio-out/<id>/paper.md).",
    )
    _add_format(p_review)
    _add_json(p_review)

    p_cite = sub.add_parser("cite", help="Verify citation candidates (suggestions only).")
    p_cite.add_argument(
        "--candidates-json",
        dest="candidates_json",
        default=None,
        help="A JSON list of citation candidates (inline).",
    )
    p_cite.add_argument(
        "--candidates-file",
        dest="candidates_file",
        default=None,
        help="Path to a JSON file of citation candidates.",
    )
    _add_format(p_cite)
    _add_json(p_cite)

    p_write = sub.add_parser("write", help="Draft a paper section from an outline.")
    p_write.add_argument("--source", default=None, help="Source material for the section (inline).")
    p_write.add_argument(
        "--source-file",
        dest="source_file",
        default=None,
        help="Path to a source-material file (e.g. clio-out/<id>/paper.md).",
    )
    p_write.add_argument(
        "--outline", default=None, help="Outline text (section title) for the section."
    )
    _add_format(p_write)
    _add_json(p_write)

    p_run = sub.add_parser(
        "run",
        help="Dispatch any adapter action by name (generic escape hatch).",
    )
    p_run.add_argument("action", help="The adapter action to dispatch (e.g. meta_review, plot).")
    _add_json(p_run)

    p_describe = sub.add_parser("describe", help="Describe the figures in memory blocks.")
    p_describe.add_argument(
        "--blocks-json",
        dest="blocks_json",
        default=None,
        help="A JSON MemoryBlocks dump (inline) whose figures to describe.",
    )
    p_describe.add_argument(
        "--blocks-file",
        dest="blocks_file",
        default=None,
        help="Path to a JSON MemoryBlocks file whose figures to describe.",
    )
    _add_format(p_describe)
    _add_json(p_describe)

    return parser


def _parse_json(value: str | None, *, field: str) -> Any:
    """Parse a JSON ``value`` (``None`` -> ``None``); raise ValueError on bad input."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid JSON for {field}: {exc}") from exc


def _read_file(path: str, *, field: str) -> str:
    """Read a UTF-8 text file for ``field``; raise ValueError on failure."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"could not read {field} {path!r}: {exc}") from exc


def _json_input(file_path: str | None, raw: str | None, *, field: str) -> Any:
    """Parse JSON from a file (preferred) or an inline string; ``None`` if neither given."""
    if file_path is not None:
        raw = _read_file(file_path, field=field)
    return _parse_json(raw, field=field)


def _payload_for(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    """Map parsed ``args`` to an ``(action, payload)`` pair.

    The ``--json`` blob (when given) seeds the payload; specific flags override
    or extend it. Raises :class:`ValueError` on malformed JSON.
    """
    command: str = args.command
    payload: dict[str, Any] = {}

    base = _parse_json(getattr(args, "json_payload", None), field="--json")
    if base is not None:
        if not isinstance(base, dict):
            raise ValueError("--json must be a JSON object")
        payload.update(base)

    if command == "ingest":
        payload["source"] = args.source
        # Persist to a visible folder by default so output isn't lost in /tmp.
        payload.setdefault("out_dir", _default_out_dir(args.source))
    elif command == "ask":
        payload["question"] = args.question
        blocks = _json_input(
            args.blocks_file, args.blocks_json, field="blocks (--blocks-json/--blocks-file)"
        )
        if blocks is not None:
            payload["blocks"] = blocks
        payload["format"] = args.fmt
    elif command == "review":
        if args.paper_file is not None:
            payload["paper"] = _read_file(args.paper_file, field="--paper-file")
        elif args.paper is not None:
            payload["paper"] = args.paper
        payload["format"] = args.fmt
    elif command == "cite":
        candidates = _json_input(
            args.candidates_file,
            args.candidates_json,
            field="candidates (--candidates-json/--candidates-file)",
        )
        if candidates is not None:
            payload["candidates"] = candidates
        payload["format"] = args.fmt
    elif command == "write":
        if args.source_file is not None:
            payload["source"] = _read_file(args.source_file, field="--source-file")
        elif args.source is not None:
            payload["source"] = args.source
        if args.outline is not None:
            # A typed outline flag carries a section title; richer outlines come
            # through --json. A bare string is wrapped so the writer can coerce it.
            payload["outline"] = {"title": args.outline}
        payload["format"] = args.fmt
    elif command == "run":
        return args.action, payload
    elif command == "describe":
        blocks = _json_input(
            args.blocks_file, args.blocks_json, field="blocks (--blocks-json/--blocks-file)"
        )
        if blocks is not None:
            payload["blocks"] = blocks
        payload["format"] = args.fmt
        return "describe_figures", payload

    return command, payload


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Returns ``0`` on success, ``1`` when the result has an error.

    Never raises a traceback: parse/runtime failures are printed as error JSON.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Lazy import so `--help`/parsing never pays the import cost.
    from clio_parser.integration.clio_adapter import ClioParserSubagent
    from clio_parser.llm.providers import resolve_llm
    from clio_parser.retrieval.scholar import resolve_scholar_client

    try:
        # CLIO_LLM selects the model (default 'echo' = offline); CLIO_SCHOLAR
        # selects the citation backend (default 'auto' = real Semantic Scholar,
        # reading SEMANTIC_SCHOLAR_API_KEY). Invalid values degrade to an error
        # dict below rather than a traceback.
        subagent = ClioParserSubagent(
            llm=resolve_llm(os.environ.get("CLIO_LLM")),
            scholar_client=resolve_scholar_client(os.environ.get("CLIO_SCHOLAR")),
        )
        if args.command == "capabilities":
            result: dict[str, Any] = subagent.capabilities()
        else:
            action, payload = _payload_for(args)
            result = subagent.run(action, payload)
    except Exception as exc:  # noqa: BLE001 - degrade to an error dict, never a traceback
        result = {"error": str(exc)}

    print(json.dumps(result, indent=2))
    return 1 if _has_error(result) else 0


def _has_error(result: dict[str, Any]) -> bool:
    """True when ``result`` carries an adapter-level or expert-level error.

    Adapter/CLI failures surface as a top-level ``"error"`` key; an expert that
    degraded gracefully flags ``metadata["error"]`` instead. Either is a
    non-success exit.
    """
    if "error" in result:
        return True
    metadata = result.get("metadata")
    return isinstance(metadata, dict) and "error" in metadata


if __name__ == "__main__":  # pragma: no cover - module CLI entry
    raise SystemExit(main())

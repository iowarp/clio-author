"""Command-line entry point so a host can invoke clio-author as a subprocess.

Each subcommand builds a payload (from a ``--json`` blob and/or specific flags),
calls :meth:`~clio_author.integration.clio_adapter.ClioAuthorSubagent.run` (or
``capabilities``), prints the result as indented JSON, and returns an exit code
(``0`` on success, ``1`` when the result carries an ``error``). Every subcommand
also accepts ``--out FILE`` to save the result (prose ``content`` for
``.md``/``.txt``, full JSON for ``.json``) in addition to printing it.

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

The figure agent's optional vision path is selected by ``CLIO_VISION``
(``off`` (default, hermetic) | ``gemini``); the describe/generate model names come
from ``CLIO_VISION_MODEL`` / ``CLIO_IMAGE_MODEL`` and the Gemini client reads
``GEMINI_API_KEY`` (or ``GOOGLE_API_KEY``). With ``off`` no image API is ever
called.

Secrets can live in a local ignored env file: ``.env.local`` by default, or the
path named by ``CLIO_ENV_FILE``. Existing environment variables take precedence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _write_out(path: str, result: dict[str, Any]) -> None:
    """Write a CLI result to ``path``.

    A ``.json`` path gets the full indented result; any other extension (e.g.
    ``.md``/``.txt``) gets the human-facing ``content`` when present, falling
    back to the full JSON when there is no prose content.
    """
    if path.lower().endswith(".json"):
        text = json.dumps(result, indent=2)
    else:
        content = result.get("content")
        text = (
            content
            if isinstance(content, str) and content.strip()
            else json.dumps(result, indent=2)
        )
    Path(path).write_text(text, encoding="utf-8")


def _default_out_dir(source: str) -> str:
    """Default visible output dir for ``ingest`` -> ``clio-out/<slug-of-source>``."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", source.strip()).strip("-")[:64] or "paper"
    return f"clio-out/{slug}"


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with one subcommand per supported action."""
    parser = argparse.ArgumentParser(
        prog="clio-author",
        description="Invoke clio-author experts as a standalone subagent.",
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
    p_review.add_argument(
        "--ground",
        action="store_true",
        help="Retrieve related prior work (via CLIO_SCHOLAR) and ground the review in it.",
    )
    p_review.add_argument(
        "--figures-json",
        dest="figures_json",
        default=None,
        help="A JSON list of figures ([{figure_id?, image_path, caption?}], inline) to "
        "look at (needs CLIO_VISION=gemini).",
    )
    p_review.add_argument(
        "--figures-file",
        dest="figures_file",
        default=None,
        help="Path to a JSON file of figures ([{figure_id?, image_path, caption?}]).",
    )
    _add_format(p_review)
    _add_json(p_review)

    p_rebuttal = sub.add_parser(
        "rebuttal", help="Draft an author rebuttal addressing a review point by point."
    )
    p_rebuttal.add_argument("--paper", default=None, help="The paper/draft Markdown text (inline).")
    p_rebuttal.add_argument(
        "--paper-file",
        dest="paper_file",
        default=None,
        help="Path to a paper/draft Markdown file (e.g. clio-out/<id>/paper.md).",
    )
    p_rebuttal.add_argument(
        "--review-json",
        dest="review_json",
        default=None,
        help="A JSON PaperReview dump (inline) to respond to.",
    )
    p_rebuttal.add_argument(
        "--review-file",
        dest="review_file",
        default=None,
        help="Path to a JSON PaperReview file (e.g. a saved review result's structured).",
    )
    _add_format(p_rebuttal)
    _add_json(p_rebuttal)

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

    p_compose = sub.add_parser(
        "compose", help="Draft a whole multi-section manuscript from an idea + log."
    )
    p_compose.add_argument("--idea", default=None, help="The research idea / thesis (inline).")
    p_compose.add_argument(
        "--idea-file", dest="idea_file", default=None, help="Path to a file holding the idea text."
    )
    p_compose.add_argument(
        "--log", default=None, help="The experimental log / results notes (inline)."
    )
    p_compose.add_argument(
        "--log-file",
        dest="log_file",
        default=None,
        help="Path to a file holding the experimental log.",
    )
    p_compose.add_argument(
        "--outline-json",
        dest="outline_json",
        default=None,
        help="A JSON PaperOutline (inline) to use instead of generating one.",
    )
    p_compose.add_argument(
        "--outline-file",
        dest="outline_file",
        default=None,
        help="Path to a JSON PaperOutline file.",
    )
    p_compose.add_argument(
        "--candidates-file",
        dest="candidates_file",
        default=None,
        help="Path to a JSON file of citation candidates to verify and cite.",
    )
    p_compose.add_argument(
        "--review",
        action="store_true",
        help="Run a per-section writer/reviewer refine loop.",
    )
    p_compose.add_argument(
        "--max-rounds",
        dest="max_rounds",
        type=int,
        default=3,
        help="Max writer/reviewer rounds per section when --review is set.",
    )
    p_compose.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="Directory to persist paper.md + per-section files (optional).",
    )
    p_compose.add_argument(
        "--latex",
        action="store_true",
        help="Also export paper.tex (+ references.bib) when --out-dir is reachable.",
    )
    p_compose.add_argument(
        "--pdf",
        action="store_true",
        help="Also compile paper.pdf from the LaTeX (implies --latex; needs a LaTeX engine).",
    )
    p_compose.add_argument(
        "--plan",
        action="store_true",
        help="Plan each section (tasks/claims/sources) before drafting it.",
    )
    _add_format(p_compose)
    _add_json(p_compose)

    p_plan = sub.add_parser("plan", help="Turn an idea or outline into per-section writing plans.")
    p_plan.add_argument("--idea", default=None, help="The research idea / thesis (inline).")
    p_plan.add_argument(
        "--idea-file", dest="idea_file", default=None, help="Path to a file holding the idea text."
    )
    p_plan.add_argument(
        "--log", default=None, help="The experimental log / results notes (inline)."
    )
    p_plan.add_argument(
        "--log-file",
        dest="log_file",
        default=None,
        help="Path to a file holding the experimental log.",
    )
    p_plan.add_argument(
        "--outline-json",
        dest="outline_json",
        default=None,
        help="A JSON PaperOutline (inline) to plan against instead of generating one.",
    )
    p_plan.add_argument(
        "--outline-file",
        dest="outline_file",
        default=None,
        help="Path to a JSON PaperOutline file.",
    )
    p_plan.add_argument(
        "--blocks-file",
        dest="blocks_file",
        default=None,
        help="Path to a JSON MemoryBlocks file for grounding (e.g. clio-out/<id>/blocks.json).",
    )
    p_plan.add_argument(
        "--candidates-file",
        dest="candidates_file",
        default=None,
        help="Path to a JSON file of citation candidates to fold into citation hints.",
    )
    p_plan.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="Directory to persist plan.json (optional).",
    )
    _add_format(p_plan)
    _add_json(p_plan)

    p_research = sub.add_parser(
        "research",
        help="Propose + ground a literature brief for a topic or section.",
    )
    p_research.add_argument("--topic", default=None, help="The topic to research (inline).")
    p_research.add_argument(
        "--topic-file",
        dest="topic_file",
        default=None,
        help="Path to a file holding the topic text.",
    )
    p_research.add_argument(
        "--blocks-file",
        dest="blocks_file",
        default=None,
        help="Path to a JSON MemoryBlocks file for grounding (e.g. clio-out/<id>/blocks.json).",
    )
    p_research.add_argument(
        "--depth",
        choices=("standard", "deep"),
        default="standard",
        help="Research depth (standard = default; deep = more thorough).",
    )
    _add_format(p_research)
    _add_json(p_research)

    p_discover = sub.add_parser(
        "discover",
        help="Find real candidate papers for a topic via scholarly search.",
    )
    p_discover.add_argument("--query", default=None, help="The topic/query to search for (inline).")
    p_discover.add_argument(
        "--query-file",
        dest="query_file",
        default=None,
        help="Path to a file holding the query text.",
    )
    p_discover.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of candidate papers to return (default 10).",
    )
    p_discover.add_argument(
        "--cutoff-date",
        dest="cutoff_date",
        default=None,
        help='Optional "YYYY-MM" recency gate; only papers strictly before it are kept.',
    )
    p_discover.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="Directory to persist discovered.json + discovered.bib (optional).",
    )
    _add_format(p_discover)
    _add_json(p_discover)

    p_verify = sub.add_parser(
        "verify-work",
        help="Goal-backward check of written prose against the claims it should make.",
    )
    p_verify.add_argument("--text", default=None, help="The written prose to verify (inline).")
    p_verify.add_argument(
        "--text-file",
        dest="text_file",
        default=None,
        help="Path to a text/Markdown file holding the written prose.",
    )
    p_verify.add_argument(
        "--section-plan-json",
        dest="section_plan_json",
        default=None,
        help="A JSON SectionPlan (inline) whose claims to verify.",
    )
    p_verify.add_argument(
        "--section-plan-file",
        dest="section_plan_file",
        default=None,
        help="Path to a JSON SectionPlan file whose claims to verify.",
    )
    p_verify.add_argument(
        "--claims-json",
        dest="claims_json",
        default=None,
        help="A JSON list of claim strings (inline) to verify.",
    )
    _add_format(p_verify)
    _add_json(p_verify)

    p_check_refs = sub.add_parser(
        "check-refs",
        help="Lint a BibTeX bibliography and cross-check cited keys (deterministic).",
    )
    p_check_refs.add_argument("--bibtex", default=None, help="The BibTeX bibliography (inline).")
    p_check_refs.add_argument(
        "--bibtex-file",
        dest="bibtex_file",
        default=None,
        help="Path to a BibTeX file (e.g. references.bib).",
    )
    p_check_refs.add_argument(
        "--markdown-file",
        dest="markdown_file",
        default=None,
        help="Path to a Markdown manuscript whose \\cite{} keys to cross-check.",
    )
    p_check_refs.add_argument(
        "--text", default=None, help="Prose to scan for \\cite{} keys (inline)."
    )
    _add_format(p_check_refs)
    _add_json(p_check_refs)

    p_section_review = sub.add_parser(
        "section-review",
        help="Layered (refs -> coherence -> review) check of one section.",
    )
    p_section_review.add_argument("--text", default=None, help="The section text (inline).")
    p_section_review.add_argument(
        "--text-file",
        dest="text_file",
        default=None,
        help="Path to a file holding the section text.",
    )
    p_section_review.add_argument(
        "--bibtex-file",
        dest="bibtex_file",
        default=None,
        help="Path to a BibTeX file for the L1 reference check.",
    )
    p_section_review.add_argument(
        "--persona-json",
        dest="persona_json",
        default=None,
        help="A JSON PersonaSpec (inline) for the L3 reviewer.",
    )
    _add_format(p_section_review)
    _add_json(p_section_review)

    p_audit = sub.add_parser(
        "audit",
        help="Deterministic manuscript completeness audit (sections/budgets/placeholders/cites).",
    )
    p_audit.add_argument(
        "--sections-json",
        dest="sections_json",
        default=None,
        help="A JSON list of sections ([{title, draft, word_budget?}], inline).",
    )
    p_audit.add_argument(
        "--sections-file",
        dest="sections_file",
        default=None,
        help="Path to a JSON file of sections ([{title, draft, word_budget?}]).",
    )
    p_audit.add_argument(
        "--markdown-file",
        dest="markdown_file",
        default=None,
        help="Path to a full Markdown manuscript to split and audit.",
    )
    p_audit.add_argument(
        "--bibtex-file",
        dest="bibtex_file",
        default=None,
        help="Path to a BibTeX file for citation-coverage checking.",
    )
    _add_format(p_audit)
    _add_json(p_audit)

    p_export = sub.add_parser(
        "export", help="Export a composed manuscript to LaTeX (paper.tex + references.bib)."
    )
    p_export.add_argument("--title", default=None, help="The manuscript title (optional).")
    p_export.add_argument(
        "--sections-json",
        dest="sections_json",
        default=None,
        help="A JSON list of compose sections ([{title, draft}], inline).",
    )
    p_export.add_argument(
        "--sections-file",
        dest="sections_file",
        default=None,
        help="Path to a JSON file of compose sections ([{title, draft}]).",
    )
    p_export.add_argument(
        "--markdown-file",
        dest="markdown_file",
        default=None,
        help="Path to a full Markdown manuscript to split and export (e.g. paper.md).",
    )
    p_export.add_argument(
        "--bibtex-file",
        dest="bibtex_file",
        default=None,
        help="Path to a BibTeX file to emit as references.bib.",
    )
    p_export.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="Directory to persist paper.tex (+ references.bib) (optional).",
    )
    p_export.add_argument(
        "--pdf",
        action="store_true",
        help="Also compile paper.pdf from the .tex (needs --out-dir and a LaTeX engine).",
    )
    _add_json(p_export)

    p_polish = sub.add_parser("polish", help="Polish prose for clarity, flow, and academic voice.")
    p_polish.add_argument("--text", default=None, help="The prose to polish (inline).")
    p_polish.add_argument(
        "--text-file",
        dest="text_file",
        default=None,
        help="Path to a text file holding the prose to polish.",
    )
    p_polish.add_argument(
        "--voice", default=None, help="Optional target voice (e.g. concise, formal)."
    )
    p_polish.add_argument(
        "--target",
        default=None,
        help="Optional file (under the harness root) to apply the polished text to.",
    )
    _add_format(p_polish)
    _add_json(p_polish)

    p_coherence = sub.add_parser(
        "coherence", help="Check cross-section consistency across a manuscript."
    )
    p_coherence.add_argument(
        "--sections-json",
        dest="sections_json",
        default=None,
        help="A JSON list of sections ([{title, draft}], inline).",
    )
    p_coherence.add_argument(
        "--sections-file",
        dest="sections_file",
        default=None,
        help="Path to a JSON file of sections ([{title, draft}]).",
    )
    p_coherence.add_argument(
        "--markdown-file",
        dest="markdown_file",
        default=None,
        help="Path to a full Markdown manuscript to split into sections (e.g. paper.md).",
    )
    p_coherence.add_argument(
        "--text", default=None, help="A single passage to check (inline fallback)."
    )
    _add_format(p_coherence)
    _add_json(p_coherence)

    p_kg = sub.add_parser(
        "kg",
        help="Extract a content knowledge graph from a paper's memory blocks.",
    )
    p_kg.add_argument(
        "--blocks-json",
        dest="blocks_json",
        default=None,
        help="A JSON MemoryBlocks dump (inline) to extract the knowledge graph from.",
    )
    p_kg.add_argument(
        "--blocks-file",
        dest="blocks_file",
        default=None,
        help="Path to a JSON MemoryBlocks file (e.g. clio-out/<id>/blocks.json).",
    )
    p_kg.add_argument(
        "--full",
        action="store_true",
        help="Run the multi-stage KG pipeline (metadata/ontology/extraction/coref/verify/summary).",
    )
    p_kg.add_argument(
        "--stages",
        default=None,
        help="Comma-separated subset of pipeline stages to run (implies the pipeline path).",
    )
    p_kg.add_argument(
        "--resume",
        default=None,
        help="Directory holding a prior run's kg_pipeline/*.json checkpoints to resume from.",
    )
    p_kg.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="Directory to persist kg.json/kg.mmd and per-stage pipeline checkpoints.",
    )
    _add_format(p_kg)
    _add_json(p_kg)

    p_orchestrate = sub.add_parser(
        "orchestrate",
        help="Plan and run a sequence of actions to achieve a natural-language goal.",
    )
    p_orchestrate.add_argument("--goal", default=None, help="The goal to achieve (inline).")
    p_orchestrate.add_argument(
        "--goal-file",
        dest="goal_file",
        default=None,
        help="Path to a file holding the goal text.",
    )
    p_orchestrate.add_argument(
        "--inputs-json",
        dest="inputs_json",
        default=None,
        help='A JSON object of named inputs (inline), e.g. {"source": "2601.23265"}.',
    )
    p_orchestrate.add_argument(
        "--inputs-file",
        dest="inputs_file",
        default=None,
        help="Path to a JSON file of named inputs.",
    )
    p_orchestrate.add_argument(
        "--max-steps",
        dest="max_steps",
        type=int,
        default=6,
        help="Maximum number of planned steps to execute (default 6).",
    )
    p_orchestrate.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="Directory to persist orchestrate.json (optional).",
    )
    _add_format(p_orchestrate)
    _add_json(p_orchestrate)

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

    p_gather = sub.add_parser(
        "gather",
        help="Ingest many sources (files/folders/globs/git repos/PDFs) into merged blocks.",
    )
    p_gather.add_argument(
        "--sources",
        nargs="+",
        default=None,
        help="One or more sources: file/folder/glob path, git repo URL, arXiv id, or PDF URL/path.",
    )
    p_gather.add_argument(
        "--sources-file",
        dest="sources_file",
        default=None,
        help="Path to a file listing sources (one per line, or a JSON array of strings).",
    )
    p_gather.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="Directory to persist context.json (a drop-in --blocks-file) + context.md (optional).",
    )
    p_gather.add_argument(
        "--max-files",
        dest="max_files",
        type=int,
        default=None,
        help="Cap on files pulled from folders/globs/repos in total (default 50).",
    )
    p_gather.add_argument(
        "--max-text-chars",
        dest="max_text_chars",
        type=int,
        default=None,
        help="Per-text-file character cap; longer files are truncated (default 200000).",
    )
    _add_format(p_gather)
    _add_json(p_gather)

    p_experiment = sub.add_parser(
        "experiment",
        help="Extract reference papers' design/experiments and recreate an evaluation plan.",
    )
    p_experiment.add_argument(
        "--blocks-json",
        dest="blocks_json",
        default=None,
        help="Inline MemoryBlocks dump of the reference paper(s).",
    )
    p_experiment.add_argument(
        "--blocks-file",
        dest="blocks_file",
        default=None,
        help="Path to a JSON MemoryBlocks file (e.g. a gather context.json for multi-paper).",
    )
    p_experiment.add_argument(
        "--markdown-file",
        dest="markdown_file",
        default=None,
        help="Path to a single paper's Markdown (alternative to blocks).",
    )
    p_experiment.add_argument(
        "--text", default=None, help="A single paper's text inline (alternative to blocks)."
    )
    p_experiment.add_argument(
        "--idea",
        default=None,
        help="The NEW paper's idea/thesis; supplying it recreates an evaluation plan.",
    )
    p_experiment.add_argument(
        "--idea-file", dest="idea_file", default=None, help="Path to a file holding the idea text."
    )
    p_experiment.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="Directory to persist experiment_designs.json/.md + evaluation_plan.json/.md.",
    )
    _add_format(p_experiment)
    _add_json(p_experiment)

    # `--sources` on the grounding subcommands: auto-gather files/folders/globs/
    # git repos/PDFs into `blocks` before the action runs (no pre-ingest needed).
    for _name in ("ask", "review", "write", "compose", "plan", "research", "kg", "experiment"):
        _gp = sub.choices[_name]
        _gp.add_argument(
            "--sources",
            nargs="+",
            default=None,
            help="Auto-gather these sources (files/folders/globs/git repos/PDFs) into grounding "
            "blocks before running.",
        )
        _gp.add_argument(
            "--sources-file",
            dest="sources_file",
            default=None,
            help="Path to a file listing sources (one per line, or a JSON array of strings).",
        )

    # `--out FILE` on every subcommand: also save the result (prose `content`
    # for .md/.txt, full JSON for .json) so callers need not redirect stdout.
    for _p in sub.choices.values():
        _p.add_argument(
            "--out",
            dest="out_file",
            default=None,
            help="Also write the result to this file (prose for .md/.txt, full JSON for .json).",
        )

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


def _sources_from_args(args: argparse.Namespace) -> list[str] | None:
    """Resolve the ``--sources`` / ``--sources-file`` inputs to a list of strings.

    ``--sources`` (a list) wins. ``--sources-file`` is read as either a JSON array
    of strings or a newline-separated list (blank lines and ``#`` comments
    skipped). Returns ``None`` when neither is given.
    """
    sources = getattr(args, "sources", None)
    if sources:
        return [str(s) for s in sources]
    sources_file = getattr(args, "sources_file", None)
    if not sources_file:
        return None
    text = _read_file(sources_file, field="--sources-file")
    stripped = text.strip()
    if stripped.startswith("["):
        parsed = _parse_json(stripped, field="--sources-file")
        if isinstance(parsed, list):
            return [str(s) for s in parsed]
        raise ValueError("--sources-file JSON must be an array of strings")
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def _load_kg_checkpoints(resume_dir: str) -> dict[str, Any]:
    """Best-effort load of ``<resume_dir>/kg_pipeline/<stage>.json`` checkpoints.

    Returns a ``{stage: graph_dict}`` map (empty when the directory or files are
    missing/unreadable). Used by ``kg --resume`` to continue a prior pipeline run.
    """
    base = Path(resume_dir) / "kg_pipeline"
    checkpoints: dict[str, Any] = {}
    if not base.is_dir():
        return checkpoints
    for path in sorted(base.glob("*.json")):
        try:
            checkpoints[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return checkpoints


def _load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines from ``path`` without overriding real env vars."""
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"could not read env file {path!s}: {exc}") from exc
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        os.environ.setdefault(key, _strip_env_quotes(value.strip()))


def _strip_env_quotes(value: str) -> str:
    """Strip one matching shell-style quote pair from an env-file value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _load_cli_env() -> None:
    """Load env configuration for CLI runs.

    ``CLIO_ENV_FILE=/path/to/file`` is explicit. Otherwise, load ``.env.local``
    from the current working directory when present, then ``.env`` for users who
    prefer that conventional name. Both are ignored by this repo's ``.gitignore``.
    """
    explicit = os.environ.get("CLIO_ENV_FILE")
    if explicit:
        _load_env_file(Path(explicit))
        return
    _load_env_file(Path(".env.local"))
    _load_env_file(Path(".env"))


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
    elif command == "gather":
        sources = _sources_from_args(args)
        if sources is not None:
            payload["sources"] = sources
        if args.out_dir is not None:
            payload["out_dir"] = args.out_dir
        if args.max_files is not None:
            payload["max_files"] = args.max_files
        if args.max_text_chars is not None:
            payload["max_text_chars"] = args.max_text_chars
        payload["format"] = args.fmt
        return "gather", payload
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
        if args.ground:
            payload["ground"] = True
        figures = _json_input(
            args.figures_file, args.figures_json, field="figures (--figures-json/--figures-file)"
        )
        if figures is not None:
            payload["figures"] = figures
        payload["format"] = args.fmt
    elif command == "rebuttal":
        if args.paper_file is not None:
            payload["paper"] = _read_file(args.paper_file, field="--paper-file")
        elif args.paper is not None:
            payload["paper"] = args.paper
        review = _json_input(
            args.review_file, args.review_json, field="review (--review-json/--review-file)"
        )
        if review is not None:
            payload["review"] = review
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
    elif command == "compose":
        if args.idea_file is not None:
            payload["idea"] = _read_file(args.idea_file, field="--idea-file")
        elif args.idea is not None:
            payload["idea"] = args.idea
        if args.log_file is not None:
            payload["experimental_log"] = _read_file(args.log_file, field="--log-file")
        elif args.log is not None:
            payload["experimental_log"] = args.log
        outline = _json_input(
            args.outline_file, args.outline_json, field="outline (--outline-json/--outline-file)"
        )
        if outline is not None:
            payload["outline"] = outline
        candidates = _json_input(args.candidates_file, None, field="candidates (--candidates-file)")
        if candidates is not None:
            payload["candidates"] = candidates
        payload["review"] = args.review
        payload["max_rounds"] = args.max_rounds
        if args.out_dir is not None:
            payload["out_dir"] = args.out_dir
        payload["latex"] = args.latex
        if args.pdf:
            payload["pdf"] = True
        payload["plan"] = args.plan
        payload["format"] = args.fmt
    elif command == "plan":
        if args.idea_file is not None:
            payload["idea"] = _read_file(args.idea_file, field="--idea-file")
        elif args.idea is not None:
            payload["idea"] = args.idea
        if args.log_file is not None:
            payload["experimental_log"] = _read_file(args.log_file, field="--log-file")
        elif args.log is not None:
            payload["experimental_log"] = args.log
        outline = _json_input(
            args.outline_file, args.outline_json, field="outline (--outline-json/--outline-file)"
        )
        if outline is not None:
            payload["outline"] = outline
        blocks = _json_input(args.blocks_file, None, field="blocks (--blocks-file)")
        if blocks is not None:
            payload["blocks"] = blocks
        candidates = _json_input(args.candidates_file, None, field="candidates (--candidates-file)")
        if candidates is not None:
            payload["candidates"] = candidates
        if args.out_dir is not None:
            payload["out_dir"] = args.out_dir
        payload["format"] = args.fmt
    elif command == "research":
        if args.topic_file is not None:
            payload["topic"] = _read_file(args.topic_file, field="--topic-file")
        elif args.topic is not None:
            payload["topic"] = args.topic
        blocks = _json_input(args.blocks_file, None, field="blocks (--blocks-file)")
        if blocks is not None:
            payload["blocks"] = blocks
        payload["depth"] = args.depth
        payload["format"] = args.fmt
        return "research", payload
    elif command == "discover":
        if args.query_file is not None:
            payload["query"] = _read_file(args.query_file, field="--query-file")
        elif args.query is not None:
            payload["query"] = args.query
        payload["limit"] = args.limit
        if args.cutoff_date is not None:
            payload["cutoff_date"] = args.cutoff_date
        if args.out_dir is not None:
            payload["out_dir"] = args.out_dir
        payload["format"] = args.fmt
        return "discover", payload
    elif command == "verify-work":
        if args.text_file is not None:
            payload["text"] = _read_file(args.text_file, field="--text-file")
        elif args.text is not None:
            payload["text"] = args.text
        section_plan = _json_input(
            args.section_plan_file,
            args.section_plan_json,
            field="section_plan (--section-plan-json/--section-plan-file)",
        )
        if section_plan is not None:
            payload["section_plan"] = section_plan
        claims = _parse_json(args.claims_json, field="--claims-json")
        if claims is not None:
            payload["claims"] = claims
        payload["format"] = args.fmt
        return "verify_work", payload
    elif command == "check-refs":
        if args.bibtex_file is not None:
            payload["bibtex"] = _read_file(args.bibtex_file, field="--bibtex-file")
        elif args.bibtex is not None:
            payload["bibtex"] = args.bibtex
        if args.markdown_file is not None:
            payload["markdown"] = _read_file(args.markdown_file, field="--markdown-file")
        elif args.text is not None:
            payload["text"] = args.text
        payload["format"] = args.fmt
        return "check_refs", payload
    elif command == "section-review":
        if args.text_file is not None:
            payload["text"] = _read_file(args.text_file, field="--text-file")
        elif args.text is not None:
            payload["text"] = args.text
        if args.bibtex_file is not None:
            payload["bibtex"] = _read_file(args.bibtex_file, field="--bibtex-file")
        persona = _parse_json(args.persona_json, field="--persona-json")
        if persona is not None:
            payload["persona"] = persona
        payload["format"] = args.fmt
        return "section_review", payload
    elif command == "audit":
        sections = _json_input(
            args.sections_file,
            args.sections_json,
            field="sections (--sections-json/--sections-file)",
        )
        if sections is not None:
            payload["sections"] = sections
        if args.markdown_file is not None:
            payload["markdown"] = _read_file(args.markdown_file, field="--markdown-file")
        if args.bibtex_file is not None:
            payload["bibtex"] = _read_file(args.bibtex_file, field="--bibtex-file")
        payload["format"] = args.fmt
        return "audit", payload
    elif command == "export":
        if args.title is not None:
            payload["title"] = args.title
        sections = _json_input(
            args.sections_file,
            args.sections_json,
            field="sections (--sections-json/--sections-file)",
        )
        if sections is not None:
            payload["sections"] = sections
        if args.markdown_file is not None:
            payload["markdown"] = _read_file(args.markdown_file, field="--markdown-file")
        if args.bibtex_file is not None:
            payload["bibtex"] = _read_file(args.bibtex_file, field="--bibtex-file")
        if args.out_dir is not None:
            payload["out_dir"] = args.out_dir
        if args.pdf:
            payload["pdf"] = True
    elif command == "polish":
        if args.text_file is not None:
            payload["text"] = _read_file(args.text_file, field="--text-file")
        elif args.text is not None:
            payload["text"] = args.text
        if args.voice is not None:
            payload["voice"] = args.voice
        if args.target is not None:
            payload["target"] = args.target
        payload["format"] = args.fmt
    elif command == "coherence":
        sections = _json_input(
            args.sections_file,
            args.sections_json,
            field="sections (--sections-json/--sections-file)",
        )
        if sections is not None:
            payload["sections"] = sections
        if args.markdown_file is not None:
            payload["markdown"] = _read_file(args.markdown_file, field="--markdown-file")
        if args.text is not None:
            payload["text"] = args.text
        payload["format"] = args.fmt
    elif command == "kg":
        blocks = _json_input(
            args.blocks_file, args.blocks_json, field="blocks (--blocks-json/--blocks-file)"
        )
        if blocks is not None:
            payload["blocks"] = blocks
        if args.full:
            payload["full"] = True
        if args.stages is not None:
            payload["stages"] = args.stages
        if args.out_dir is not None:
            payload["out_dir"] = args.out_dir
        if args.resume is not None:
            checkpoints = _load_kg_checkpoints(args.resume)
            if checkpoints:
                payload["checkpoints"] = checkpoints
                payload["full"] = True
        payload["format"] = args.fmt
        return "kg", payload
    elif command == "orchestrate":
        if args.goal_file is not None:
            payload["goal"] = _read_file(args.goal_file, field="--goal-file")
        elif args.goal is not None:
            payload["goal"] = args.goal
        inputs = _json_input(
            args.inputs_file, args.inputs_json, field="inputs (--inputs-json/--inputs-file)"
        )
        if inputs is not None:
            payload["inputs"] = inputs
        payload["max_steps"] = args.max_steps
        if args.out_dir is not None:
            payload["out_dir"] = args.out_dir
        payload["format"] = args.fmt
        return "orchestrate", payload
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
    elif command == "experiment":
        blocks = _json_input(
            args.blocks_file, args.blocks_json, field="blocks (--blocks-json/--blocks-file)"
        )
        if blocks is not None:
            payload["blocks"] = blocks
        if args.markdown_file is not None:
            payload["markdown"] = _read_file(args.markdown_file, field="--markdown-file")
        elif args.text is not None:
            payload["text"] = args.text
        if args.idea_file is not None:
            payload["idea"] = _read_file(args.idea_file, field="--idea-file")
        elif args.idea is not None:
            payload["idea"] = args.idea
        if args.out_dir is not None:
            payload["out_dir"] = args.out_dir
        payload["format"] = args.fmt

    # Grounding subcommands accept `--sources`/`--sources-file`: pass the list
    # through so the agent auto-gathers it into `blocks` before dispatch (unless
    # explicit blocks were already supplied).
    if command in ("ask", "review", "write", "compose", "plan", "research", "kg", "experiment"):
        sources = _sources_from_args(args)
        if sources is not None and "blocks" not in payload:
            payload["sources"] = sources

    return command, payload


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Returns ``0`` on success, ``1`` when the result has an error.

    Never raises a traceback: parse/runtime failures are printed as error JSON.
    The result is always printed as JSON on stdout; ``--out FILE`` additionally
    saves it (prose ``content`` for ``.md``/``.txt``, full JSON for ``.json``).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    _load_cli_env()

    # Lazy import so `--help`/parsing never pays the import cost.
    from clio_author.integration.clio_adapter import ClioAuthorSubagent
    from clio_author.llm.providers import resolve_llm
    from clio_author.llm.vision import resolve_vision_client
    from clio_author.retrieval.scholar import resolve_scholar_client

    try:
        # CLIO_LLM selects the model (default 'echo' = offline); CLIO_SCHOLAR
        # selects the citation backend (default 'auto' = real Semantic Scholar,
        # reading SEMANTIC_SCHOLAR_API_KEY); CLIO_VISION selects the figure-agent
        # image route (default off = hermetic, 'gemini' reads GEMINI_API_KEY).
        # Invalid values degrade to an error dict below rather than a traceback.
        subagent = ClioAuthorSubagent(
            llm=resolve_llm(os.environ.get("CLIO_LLM")),
            scholar_client=resolve_scholar_client(os.environ.get("CLIO_SCHOLAR")),
            vision=resolve_vision_client(os.environ.get("CLIO_VISION")),
        )
        if args.command == "capabilities":
            result: dict[str, Any] = subagent.capabilities()
        else:
            action, payload = _payload_for(args)
            result = subagent.run(action, payload)
    except Exception as exc:  # noqa: BLE001 - degrade to an error dict, never a traceback
        result = {"error": str(exc)}

    out_file = getattr(args, "out_file", None)
    if out_file:
        try:
            _write_out(out_file, result)
            print(f"[saved to {out_file}]", file=sys.stderr)
        except OSError as exc:
            print(f"[warning: could not write {out_file}: {exc}]", file=sys.stderr)

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

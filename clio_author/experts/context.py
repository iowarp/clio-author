"""The context expert: gather many sources into one merged memory-block set.

:class:`ContextExpert` (action ``gather``) is the front door for grounding the
writing path in a whole working set. It takes a list of *sources* -- files,
folders, globs, git repos, PDFs/arXiv ids -- and runs
:func:`~clio_author.ingest.gather.gather_context` to ingest each and merge them
into one :class:`~clio_author.ingest.blocks.MemoryBlocks`. The result is written
to ``context.json`` (a drop-in ``--blocks-file`` for ``plan`` / ``write`` /
``compose`` / ``ask`` / ``research`` / ``kg``) and ``context.md``.

It is deterministic (the LLM client is unused, defaulting to
:class:`EchoLLMClient` only to satisfy the base contract) and, like every
expert, never raises: a missing ``sources`` list or any failure produces an
error-flagged :class:`AgentOutput`. Per-source failures do not abort the run --
they are reported in ``structured["skipped"]``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.llm.client import EchoLLMClient, LLMClient

if TYPE_CHECKING:  # pragma: no cover - typing only
    from clio_author.ingest.docling_extract import PdfConfig

CONTEXT_SYSTEM_PROMPT = (
    "You are the context-gathering expert. Given a set of sources (files, "
    "folders, git repositories, PDFs), you ingest each into clean memory blocks "
    "and merge them into one grounding context for the writing path. This work "
    "is deterministic."
)


class ContextExpert(BaseAgent):
    """Expert that gathers many sources into one merged :class:`MemoryBlocks`."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        config: PdfConfig | None = None,
        out_dir: Path | None = None,
    ) -> None:
        """Build a context expert.

        Args:
            llm: Unused for gathering; defaults to :class:`EchoLLMClient`.
            config: Optional PDF extraction config passed through to the PDF path.
            out_dir: Default working/output directory (the payload's ``out_dir``
                wins when provided).
        """
        super().__init__(
            role="context",
            system_prompt=CONTEXT_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._config = config
        self.out_dir = out_dir

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Gather ``task.payload["sources"]`` into merged memory blocks. Never raises.

        Reads ``sources`` (a string or list of file/folder/glob/git/PDF sources),
        ``out_dir`` (optional; ``context.json`` + ``context.md`` are written
        there), ``max_files`` and ``max_text_chars`` (optional bounds). Returns an
        :class:`AgentOutput` whose ``structured`` is
        ``{"blocks", "ingested", "skipped", "count"}`` and whose ``metadata``
        carries the counts and ``wrote`` paths.
        """
        payload = task.payload
        raw_sources = payload.get("sources")
        if not raw_sources:
            return self._error(session, "no 'sources' provided")

        from clio_author.ingest.gather import (
            DEFAULT_MAX_FILES,
            DEFAULT_MAX_TEXT_CHARS,
            gather_context,
            render_context_markdown,
        )

        out_dir = payload.get("out_dir") or self.out_dir
        out_path = Path(out_dir) if out_dir else None
        try:
            max_files = int(payload.get("max_files", DEFAULT_MAX_FILES))
        except (TypeError, ValueError):
            max_files = DEFAULT_MAX_FILES
        try:
            max_text_chars = int(payload.get("max_text_chars", DEFAULT_MAX_TEXT_CHARS))
        except (TypeError, ValueError):
            max_text_chars = DEFAULT_MAX_TEXT_CHARS

        try:
            result = gather_context(
                raw_sources,
                out_dir=out_path,
                config=self._config,
                max_files=max_files,
                max_text_chars=max_text_chars,
            )
            wrote = self._maybe_write(out_path, result, render_context_markdown)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        blocks_dump = result.blocks.model_dump()
        n_sections = len(result.blocks.sections)
        n_figures = len(result.blocks.figures)
        summary = (
            f"Gathered {len(result.ingested)} unit(s) into {n_sections} section block(s) "
            f"and {n_figures} figure block(s)"
            + (f"; skipped {len(result.skipped)}." if result.skipped else ".")
        )
        output = AgentOutput(
            agent=self.name,
            content=summary,
            structured={
                "blocks": blocks_dump,
                "ingested": result.ingested,
                "skipped": result.skipped,
                "count": len(result.ingested),
            },
            metadata={
                "ingested": len(result.ingested),
                "skipped": len(result.skipped),
                "sections": n_sections,
                "figures": n_figures,
                "wrote": wrote,
            },
        )
        session.add(output)
        return output

    @staticmethod
    def _maybe_write(out_path: Path | None, result: Any, render: Any) -> list[str]:
        """Write ``context.json`` + ``context.md`` under ``out_dir`` (best-effort).

        ``context.json`` is the pure ``blocks`` dump so it drops straight into a
        ``--blocks-file`` / ``blocks`` payload. Existing files are not clobbered.
        """
        if out_path is None:
            return []
        wrote: list[str] = []
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except OSError:
            return []
        json_path = out_path / "context.json"
        if not json_path.exists():
            try:
                json_path.write_text(
                    json.dumps(result.blocks.model_dump(), indent=2), encoding="utf-8"
                )
                wrote.append(str(json_path))
            except OSError:
                pass
        md_path = out_path / "context.md"
        if not md_path.exists():
            try:
                md_path.write_text(render(result.blocks), encoding="utf-8")
                wrote.append(str(md_path))
            except OSError:
                pass
        return wrote


__all__ = ["ContextExpert", "CONTEXT_SYSTEM_PROMPT"]

"""The ingestor expert: arXiv/PDF -> clean Markdown + memory blocks.

:class:`IngestorExpert` runs the deterministic processing pipeline (Docling +
post-process) and packages the result as :class:`MemoryBlocks`. It overrides
:meth:`BaseAgent.run` because ingestion is deterministic -- the LLM client is
unused (it defaults to :class:`EchoLLMClient` only to satisfy the base contract).

Heavy PDF dependencies are lazy-imported inside :meth:`run`, so importing this
module is hermetic and works without the ``pdf`` extra installed. On missing
dependencies or extraction failure the expert returns an
:class:`AgentOutput` whose ``metadata["error"]`` describes the failure rather
than raising, so a harness run degrades gracefully.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.llm.client import EchoLLMClient, LLMClient

if TYPE_CHECKING:  # pragma: no cover - typing only
    from clio_author.ingest.docling_extract import PdfConfig

INGESTOR_SYSTEM_PROMPT = (
    "You are the ingestor expert. You convert a PDF or arXiv paper into clean "
    "scientific Markdown and structured memory blocks. This work is deterministic."
)


class IngestorExpert(BaseAgent):
    """Expert that converts a PDF/arXiv source into Markdown + memory blocks."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        config: PdfConfig | None = None,
        out_dir: Path | None = None,
    ) -> None:
        """Build an ingestor expert.

        Args:
            llm: Unused for extraction; defaults to :class:`EchoLLMClient`.
            config: PDF extraction configuration; default :class:`PdfConfig`.
            out_dir: Working directory for downloads and figure images.
        """
        super().__init__(
            role="ingestor",
            system_prompt=INGESTOR_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._config = config
        self.out_dir = out_dir

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Ingest ``task.payload["source"]`` into Markdown + memory blocks.

        Returns an :class:`AgentOutput` with the processed Markdown as
        ``content``, the :class:`MemoryBlocks` dump as ``structured``, and
        extraction provenance in ``metadata``. On missing ``pdf`` dependencies
        or any extraction error it returns an error-flagged output (it does not
        raise), and still appends to the session.
        """
        source = task.payload.get("source")
        if not source:
            output = AgentOutput(
                agent=self.name,
                content="",
                metadata={"error": "no 'source' provided in task.payload"},
            )
            session.add(output)
            return output

        # Lazy-import the heavy/optional path so this module stays hermetic.
        from clio_author.ingest.blocks import FigureInfo, MemoryBlocks, build_section_blocks
        from clio_author.ingest.docling_extract import (
            PdfConfig,
            process_pdf,
        )

        config = self._config or PdfConfig()
        # out_dir may be set per-call (task.payload) or on the expert (constructor);
        # the payload wins. When set, figures, paper.md, and blocks.json land there.
        raw_out = task.payload.get("out_dir") or self.out_dir
        out_path = Path(raw_out) if raw_out is not None else None

        # Guard the whole extraction + block-building region: process_pdf only
        # raises ExtractionError, but build_section_blocks / MemoryBlocks could
        # raise on malformed Markdown. The expert must never propagate -- a
        # harness run degrades gracefully via an error-flagged output.
        try:
            result = process_pdf(source, out_dir=out_path, config=config)

            sections = build_section_blocks(result.markdown)
            # NOTE: figure_id is positionally coupled to "figureN.png" filenames;
            # decoupling figure ids from filenames is deferred to M7 by design.
            figures = [
                FigureInfo(figure_id=i, image_path=path.name)
                for i, path in enumerate(result.images, start=1)
            ]
            image_dir = str(result.images[0].parent) if result.images else None
            blocks = MemoryBlocks(
                metadata=dict(result.metadata),
                sections=sections,
                figures=figures,
            )
            # Persist Markdown + memory blocks so the result is visible on disk.
            written: list[str] = []
            if out_path is not None:
                out_path.mkdir(parents=True, exist_ok=True)
                md_file = out_path / "paper.md"
                blocks_file = out_path / "blocks.json"
                md_file.write_text(result.markdown, encoding="utf-8")
                blocks_file.write_text(json.dumps(blocks.model_dump(), indent=2), encoding="utf-8")
                written = [str(md_file), str(blocks_file)]
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            output = AgentOutput(
                agent=self.name,
                content="",
                metadata={"error": str(exc), "source": str(source)},
            )
            session.add(output)
            return output

        output = AgentOutput(
            agent=self.name,
            content=result.markdown,
            structured=blocks.model_dump(),
            metadata={
                "extractor": result.extractor,
                "source_url": result.source_url,
                "image_dir": image_dir,
                "out_dir": str(out_path) if out_path is not None else None,
                "wrote": written,
            },
        )
        session.add(output)
        return output


__all__ = ["IngestorExpert", "INGESTOR_SYSTEM_PROMPT"]

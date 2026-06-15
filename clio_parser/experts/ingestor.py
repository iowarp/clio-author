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

from pathlib import Path
from typing import TYPE_CHECKING

from clio_parser.harness.base import BaseAgent
from clio_parser.harness.session import SessionContext
from clio_parser.harness.types import AgentOutput, Task
from clio_parser.llm.client import EchoLLMClient, LLMClient

if TYPE_CHECKING:  # pragma: no cover - typing only
    from clio_parser.ingest.docling_extract import PdfConfig

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
        from clio_parser.ingest.blocks import FigureInfo, MemoryBlocks, build_section_blocks
        from clio_parser.ingest.docling_extract import (
            PdfConfig,
            process_pdf,
        )

        config = self._config or PdfConfig()
        # Guard the whole extraction + block-building region: process_pdf only
        # raises ExtractionError, but build_section_blocks / MemoryBlocks could
        # raise on malformed Markdown. The expert must never propagate -- a
        # harness run degrades gracefully via an error-flagged output.
        try:
            result = process_pdf(source, out_dir=self.out_dir, config=config)

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
            },
        )
        session.add(output)
        return output


__all__ = ["IngestorExpert", "INGESTOR_SYSTEM_PROMPT"]

"""Memory-block schemas for processed scientific papers (Pydantic v2).

A processed paper is represented as a :class:`MemoryBlocks` container holding
typed blocks -- sections, figures, equations and code blocks. Each block carries
a stable ``block_id`` and a :meth:`Block.to_context` renderer at three detail
levels, so the harness can inject just the right amount of context.

``MemoryBlocks.model_dump`` reproduces a paper-to-md ``enrichments``-style dict
(``metadata`` / ``code_blocks`` / ``equations`` / ``figures``) plus a ``sections``
array, keeping the on-disk shape compatible with that MIT project's output.

The enrichment block schemas mirror the paper-to-md project (MIT): https://github.com/JaimeCernuda/paper-to-md
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, model_validator

Detail = Literal["ref", "summary", "full"]
"""How much of a block :meth:`Block.to_context` should render."""

BlockKind = Literal["section", "figure", "equation", "code"]
"""The discriminator for selecting blocks in :meth:`MemoryBlocks.select`."""

# Summary rendering truncates long text to keep injected context compact.
_SUMMARY_CHARS = 280


def _truncate(text: str, limit: int = _SUMMARY_CHARS) -> str:
    """Trim ``text`` to ``limit`` characters with an ellipsis when needed."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


class Block(BaseModel):
    """Common interface shared by every memory block."""

    kind: BlockKind

    @property
    def block_id(self) -> str:  # pragma: no cover - overridden by subclasses
        """A stable identifier, unique within a :class:`MemoryBlocks`."""
        raise NotImplementedError

    def to_context(self, detail: Detail = "summary") -> str:  # pragma: no cover - overridden
        """Render this block for context injection at the given ``detail`` level."""
        raise NotImplementedError


class SectionBlock(Block):
    """A document section reconstructed from the post-processed Markdown headers."""

    kind: Literal["section"] = "section"
    section_path: str = Field(description="`>`-joined ancestor titles, e.g. 'Methods > Setup'.")
    title: str
    text: str = ""
    page_range: tuple[int, int] | None = None
    start_line: int | None = Field(
        default=None, description="1-based line of this section's header in the source Markdown."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def block_id(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.section_path.lower()).strip("-")
        return f"section:{slug or 'untitled'}"

    def to_context(self, detail: Detail = "summary") -> str:
        if detail == "ref":
            return f"[{self.block_id}] {self.section_path}"
        if detail == "summary":
            return f"## {self.section_path}\n{_truncate(self.text)}".rstrip()
        return f"## {self.section_path}\n{self.text}".rstrip()


class FigureInfo(Block):
    """Figure metadata; ``description`` is filled later by the figure agent."""

    kind: Literal["figure"] = "figure"
    figure_id: int
    caption: str | None = None
    classification: str | None = None
    description: str | None = None
    page: int | None = None
    image_path: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def block_id(self) -> str:
        return f"figure:{self.figure_id}"

    def to_context(self, detail: Detail = "summary") -> str:
        if detail == "ref":
            return f"[{self.block_id}] Figure {self.figure_id}"
        head = f"Figure {self.figure_id}"
        if self.caption:
            head = f"{head}: {self.caption}"
        if detail == "summary":
            return _truncate(head)
        parts = [head]
        if self.description:
            parts.append(self.description)
        if self.image_path:
            parts.append(f"(image: {self.image_path})")
        return "\n".join(parts)


class Equation(Block):
    """An extracted equation with its LaTeX (and optional text) representation."""

    kind: Literal["equation"] = "equation"
    index: int = 0
    latex: str
    text: str | None = None
    page: int | None = None
    context: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def block_id(self) -> str:
        return f"equation:{self.index}"

    def to_context(self, detail: Detail = "summary") -> str:
        if detail == "ref":
            return f"[{self.block_id}]"
        if detail == "summary":
            return f"$$ {_truncate(self.latex, 120)} $$"
        parts = [f"$$ {self.latex} $$"]
        if self.context:
            parts.append(self.context)
        return "\n".join(parts)


class CodeBlock(Block):
    """An extracted source-code block."""

    kind: Literal["code"] = "code"
    index: int = 0
    text: str
    language: str | None = None
    page: int | None = None
    context: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def block_id(self) -> str:
        return f"code:{self.index}"

    def to_context(self, detail: Detail = "summary") -> str:
        lang = self.language or ""
        if detail == "ref":
            return f"[{self.block_id}] {lang}".rstrip()
        if detail == "summary":
            return f"```{lang}\n{_truncate(self.text)}\n```"
        return f"```{lang}\n{self.text}\n```"


class MemoryBlocks(BaseModel):
    """Container for every memory block extracted from one processed paper."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    sections: list[SectionBlock] = Field(default_factory=list)
    figures: list[FigureInfo] = Field(default_factory=list)
    equations: list[Equation] = Field(default_factory=list)
    code_blocks: list[CodeBlock] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _load_path(cls, data: Any) -> Any:
        """Accept a path to a ``blocks.json`` file in place of the blocks themselves.

        Lets a caller that cannot inline 50KB of JSON — an MCP or A2A host — pass
        ``{"blocks": "paper/blocks.json"}`` and get the same result as the CLI's
        ``--blocks-file``.
        """
        if isinstance(data, (str, Path)):
            return json.loads(Path(data).read_text(encoding="utf-8"))
        return data

    def all_blocks(self) -> list[Block]:
        """Every block across all kinds, in a stable kind-then-order sequence."""
        blocks: list[Block] = []
        blocks.extend(self.sections)
        blocks.extend(self.figures)
        blocks.extend(self.equations)
        blocks.extend(self.code_blocks)
        return blocks

    def select(
        self,
        *,
        kinds: list[BlockKind] | None = None,
        section_path: str | None = None,
        detail: Detail = "summary",
        max_blocks: int | None = None,
    ) -> list[str]:
        """Render a filtered, capped list of block contexts for injection.

        Args:
            kinds: Restrict to these block kinds (all kinds when ``None``).
            section_path: Keep only blocks under this section path prefix
                (section blocks match their own path; other kinds are dropped
                when this filter is set, since they are not path-scoped in M1).
            detail: Detail level passed to :meth:`Block.to_context`.
            max_blocks: Cap on the number of rendered blocks.

        Returns:
            Rendered context strings, one per selected block.
        """
        selected: list[Block] = []
        for block in self.all_blocks():
            if kinds is not None and block.kind not in kinds:
                continue
            if section_path is not None:
                if not isinstance(block, SectionBlock):
                    continue
                if not block.section_path.startswith(section_path):
                    continue
            selected.append(block)

        if max_blocks is not None:
            selected = selected[:max_blocks]
        return [block.to_context(detail) for block in selected]

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize to a paper-to-md ``enrichments`` dict plus a ``sections`` array."""
        return {
            "metadata": self.metadata,
            "sections": [section.model_dump(**kwargs) for section in self.sections],
            "code_blocks": [code.model_dump(**kwargs) for code in self.code_blocks],
            "equations": [equation.model_dump(**kwargs) for equation in self.equations],
            "figures": [figure.model_dump(**kwargs) for figure in self.figures],
        }


def build_section_blocks(markdown: str) -> list[SectionBlock]:
    """Walk post-processed Markdown headers and build :class:`SectionBlock`s.

    ``section_path`` is the ``>``-joined chain of ancestor titles (by header
    depth). Text under a header -- up to the next header of any level -- becomes
    the section body. The header's numbering prefix (e.g. ``3.1``) is dropped
    from the title for readability.
    """
    lines = markdown.split("\n")
    header_re = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
    number_re = re.compile(r"^(?:\d+(?:\.\d+)*|[IVXLCDM]+)\.?\s+")

    sections: list[SectionBlock] = []
    # Stack of (level, title) for ancestor tracking.
    ancestors: list[tuple[int, str]] = []
    current: SectionBlock | None = None
    body: list[str] = []

    def flush() -> None:
        if current is not None:
            current.text = "\n".join(body).strip()

    for line_no, line in enumerate(lines, start=1):
        match = header_re.match(line)
        if not match:
            if current is not None:
                body.append(line)
            continue

        flush()
        level = len(match.group(1))
        title = number_re.sub("", match.group(2)).strip() or match.group(2).strip()

        # Pop ancestors at the same or deeper level.
        while ancestors and ancestors[-1][0] >= level:
            ancestors.pop()
        path_titles = [t for _, t in ancestors] + [title]
        ancestors.append((level, title))

        current = SectionBlock(
            section_path=" > ".join(path_titles), title=title, start_line=line_no
        )
        body = []
        sections.append(current)

    flush()
    return sections


__all__ = [
    "Block",
    "SectionBlock",
    "FigureInfo",
    "Equation",
    "CodeBlock",
    "MemoryBlocks",
    "build_section_blocks",
    "Detail",
    "BlockKind",
]

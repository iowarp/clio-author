"""Hermetic tests for memory-block schemas, section walking and selection."""

from __future__ import annotations

from clio_author.ingest.blocks import (
    Equation,
    FigureInfo,
    MemoryBlocks,
    SectionBlock,
    build_section_blocks,
)

SAMPLE_MD = """\
# Title

Intro text.

## 1. Methods

Methods overview.

### 1.1 Setup

Setup details.

## 2. Results

Results text.
"""


def test_build_section_blocks_paths() -> None:
    sections = build_section_blocks(SAMPLE_MD)
    paths = [s.section_path for s in sections]
    assert paths == [
        "Title",
        "Title > Methods",
        "Title > Methods > Setup",
        "Title > Results",
    ]


def test_section_text_captured() -> None:
    sections = build_section_blocks(SAMPLE_MD)
    setup = next(s for s in sections if s.title == "Setup")
    assert setup.text == "Setup details."
    assert setup.block_id == "section:title-methods-setup"


def test_model_dump_shape() -> None:
    blocks = MemoryBlocks(
        metadata={"title": "Demo"},
        sections=build_section_blocks(SAMPLE_MD),
        figures=[FigureInfo(figure_id=1, caption="A figure", image_path="figure1.png")],
        equations=[Equation(index=0, latex="x = y")],
    )
    dumped = blocks.model_dump()
    # paper-to-md enrichments shape + a sections array.
    assert set(dumped) == {"metadata", "sections", "code_blocks", "equations", "figures"}
    assert dumped["metadata"] == {"title": "Demo"}
    assert isinstance(dumped["sections"], list)
    assert dumped["figures"][0]["figure_id"] == 1
    assert dumped["equations"][0]["latex"] == "x = y"
    assert dumped["code_blocks"] == []


def test_select_filters_by_kind() -> None:
    blocks = MemoryBlocks(
        sections=build_section_blocks(SAMPLE_MD),
        figures=[FigureInfo(figure_id=1, caption="A figure", image_path="f1.png")],
    )
    only_figures = blocks.select(kinds=["figure"])
    assert len(only_figures) == 1
    assert "Figure 1" in only_figures[0]


def test_select_by_section_path_prefix() -> None:
    blocks = MemoryBlocks(sections=build_section_blocks(SAMPLE_MD))
    methods = blocks.select(section_path="Title > Methods", detail="ref")
    # "Methods" and "Methods > Setup" match; "Results" does not.
    assert len(methods) == 2
    assert all("Methods" in m for m in methods)


def test_select_max_blocks_caps_output() -> None:
    blocks = MemoryBlocks(sections=build_section_blocks(SAMPLE_MD))
    assert len(blocks.select(max_blocks=2)) == 2


def test_to_context_detail_levels() -> None:
    section = SectionBlock(section_path="A > B", title="B", text="Body text here.")
    assert section.to_context("ref") == "[section:a-b] A > B"
    assert "Body text here." in section.to_context("full")

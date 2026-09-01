"""MemoryBlocks accepts a path to a blocks.json file, not just inline JSON."""

from __future__ import annotations

import pytest

from clio_author.ingest.blocks import MemoryBlocks, SectionBlock


@pytest.fixture
def blocks_file(tmp_path):
    blocks = MemoryBlocks(sections=[SectionBlock(title="Intro", section_path="Intro", text="hello", start_line=1)])
    path = tmp_path / "blocks.json"
    path.write_text(blocks.model_dump_json(), encoding="utf-8")
    return path


def test_accepts_str_path(blocks_file):
    assert MemoryBlocks.model_validate(str(blocks_file)).sections[0].title == "Intro"


def test_accepts_path_object(blocks_file):
    assert MemoryBlocks.model_validate(blocks_file).sections[0].title == "Intro"


def test_dict_input_still_works(blocks_file):
    raw = MemoryBlocks.model_validate(blocks_file).model_dump()
    assert MemoryBlocks.model_validate(raw).sections[0].title == "Intro"


def test_missing_file_raises(tmp_path):
    with pytest.raises(Exception):
        MemoryBlocks.model_validate(str(tmp_path / "nope.json"))

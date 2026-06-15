"""Live Semantic Scholar tests for :class:`SemanticScholarClient`.

Gated by the ``live`` marker and skipped unless ``httpx`` (the ``scholar``
extra) is installed (``uv sync --extra scholar``). Hits the real S2 graph API,
so it needs network; it skips cleanly otherwise.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


def test_semantic_scholar_search_returns_records() -> None:
    pytest.importorskip("httpx")

    from clio_parser.retrieval.scholar import SemanticScholarClient

    client = SemanticScholarClient()
    records = client.search_title("Attention Is All You Need", year_hint=2017, cutoff_date=None)

    assert isinstance(records, list)
    assert len(records) >= 1
    assert all(r.title for r in records)

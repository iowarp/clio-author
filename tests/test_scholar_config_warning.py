"""A scholar backend that cannot run must say so, not fail silently.

The cascade absorbs every backend failure so a rate-limited or unreachable service
still falls through to the next. That is right for transient faults and wrong for a
missing optional dependency: setting ``SEMANTIC_SCHOLAR_API_KEY`` without the
``scholar`` extra left the key a silent no-op, with results still arriving from
OpenAlex so nothing looked broken.
"""

from __future__ import annotations

import warnings

import pytest

import clio_author.retrieval.scholar as scholar_mod
from clio_author.retrieval.rag import RetrievalDependencyError
from clio_author.retrieval.scholar import (
    CascadeScholarClient,
    S2Record,
    ScholarConfigWarning,
    resolve_scholar_client,
)


@pytest.fixture(autouse=True)
def _reset_warn_cache():
    """The once-per-process cache would otherwise leak between tests."""
    scholar_mod._warned.clear()
    yield
    scholar_mod._warned.clear()


class _MissingDependency:
    """A backend whose extra is not installed."""

    def search_title(self, title, year_hint, cutoff_date):
        raise RetrievalDependencyError("httpx is required. Install with: uv sync --extra scholar")

    def search_query(self, query, *, limit=10, cutoff_date=None):
        raise RetrievalDependencyError("httpx is required. Install with: uv sync --extra scholar")


class _Transient:
    """A backend that is installed but momentarily failing."""

    def search_title(self, title, year_hint, cutoff_date):
        raise TimeoutError("rate limited")

    def search_query(self, query, *, limit=10, cutoff_date=None):
        raise TimeoutError("rate limited")


class _Working:
    def __init__(self, title: str = "A Real Paper") -> None:
        self.title = title

    def search_title(self, title, year_hint, cutoff_date):
        return [S2Record(paper_id="x:1", title=self.title)]

    def search_query(self, query, *, limit=10, cutoff_date=None):
        return [S2Record(paper_id="x:1", title=self.title)]


def test_missing_dependency_warns_but_still_falls_through() -> None:
    """The cascade keeps answering; the operator learns the backend was skipped."""
    cascade = CascadeScholarClient([_MissingDependency(), _Working()])

    with pytest.warns(ScholarConfigWarning, match="uv sync --extra scholar"):
        records = cascade.search_title("A Real Paper", None, None)

    assert [r.title for r in records] == ["A Real Paper"]


def test_transient_failure_stays_quiet() -> None:
    """A rate limit is not a misconfiguration and must not nag."""
    cascade = CascadeScholarClient([_Transient(), _Working()])

    with warnings.catch_warnings():
        warnings.simplefilter("error", ScholarConfigWarning)
        records = cascade.search_title("A Real Paper", None, None)

    assert len(records) == 1


def test_warning_is_emitted_once_not_per_candidate() -> None:
    """`cite` loops over every candidate; one identical warning each would be noise."""
    cascade = CascadeScholarClient([_MissingDependency(), _Working()])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ScholarConfigWarning)
        for _ in range(5):
            cascade.search_title("A Real Paper", None, None)

    assert sum(issubclass(w.category, ScholarConfigWarning) for w in caught) == 1


def test_configured_key_without_the_extra_warns_at_resolution(monkeypatch) -> None:
    """The reported gap: the key is set, the extra is absent, nothing said so."""
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "sk-configured")
    monkeypatch.setattr(scholar_mod, "_httpx_installed", lambda: False)

    with pytest.warns(ScholarConfigWarning, match="has no effect"):
        resolve_scholar_client("auto")


def test_no_warning_when_the_extra_is_present(monkeypatch) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "sk-configured")
    monkeypatch.setattr(scholar_mod, "_httpx_installed", lambda: True)

    with warnings.catch_warnings():
        warnings.simplefilter("error", ScholarConfigWarning)
        assert resolve_scholar_client("auto") is not None


def test_no_warning_when_no_key_is_configured(monkeypatch) -> None:
    """Without a key the operator asked for nothing, so there is nothing to report."""
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.setattr(scholar_mod, "_httpx_installed", lambda: False)

    with warnings.catch_warnings():
        warnings.simplefilter("error", ScholarConfigWarning)
        assert resolve_scholar_client("auto") is not None


def test_pinned_semantic_backend_warns_because_it_cannot_degrade(monkeypatch) -> None:
    """CLIO_SCHOLAR=semantic has no fallback, so say so before the first lookup."""
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.setattr(scholar_mod, "_httpx_installed", lambda: False)

    with pytest.warns(ScholarConfigWarning, match="every lookup will fail"):
        resolve_scholar_client("semantic")

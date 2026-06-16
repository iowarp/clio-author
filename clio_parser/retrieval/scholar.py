# Verification logic adapted from PaperOrchestra `utils/scholar_utils.py`
# (Apache-2.0): https://github.com/google-research/paper-orchestra
#
# The S2 title-search date gate and fuzzy-ratio + year-bonus matching here are a
# re-implementation of that file's `s2_title_search` / `is_date_valid`. No source
# was copied verbatim; the upstream Apache-2.0 attribution is preserved per the
# project licensing rule.
"""Citation grounding via Semantic Scholar retrieval and fuzzy verification.

The verification *logic* is a set of pure, deterministic functions tested fully
offline: :func:`fuzzy_ratio`, :func:`is_date_valid`, :func:`best_match`,
:func:`mint_citation_key`, :func:`dedupe`, :func:`verified_coverage`, and
:func:`to_bibtex`. The :func:`verify` orchestrator threads a
:class:`ScholarClient` (the network seam) through those pure functions.

:func:`fuzzy_ratio` prefers ``thefuzz.fuzz.ratio`` when the ``scholar`` extra is
installed and falls back to a stdlib :class:`difflib.SequenceMatcher` ratio
(scaled 0-100) otherwise, so the default test suite needs no ``thefuzz``.

The real :class:`SemanticScholarClient` lazy-imports ``httpx`` *inside*
:meth:`~SemanticScholarClient.search_title`, so importing this module is always
cheap and hermetic; the hermetic :class:`FakeScholarClient` performs no network.
"""

from __future__ import annotations

import datetime
import difflib
import os
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from clio_parser.retrieval.rag import RetrievalDependencyError

# Semantic Scholar graph API: title-search endpoint, fields, and limits.
_S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_S2_FIELDS = "title,authors,venue,year,abstract,citationCount,journal,publicationDate"
_S2_LIMIT = 3
_S2_TIMEOUT = 5.0


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class Reference(BaseModel):
    """A citation target to look up by title, with an optional year hint."""

    query_title: str
    year_hint: int | None = None
    raw: str | None = None


class Candidate(BaseModel):
    """A proposed citation supplied to the expert (title + optional year/reason)."""

    title: str
    year: int | None = None
    reason: str | None = None


class S2Record(BaseModel):
    """A single Semantic Scholar paper record (the fields we request)."""

    paper_id: str
    title: str
    authors: list[str] = []
    venue: str | None = None
    year: int | None = None
    abstract: str | None = None
    citation_count: int | None = None
    journal: str | None = None
    publication_date: str | None = None


class VerifiedCitation(BaseModel):
    """A reference matched to an :class:`S2Record` with a score and minted key."""

    record: S2Record
    score: float
    citation_key: str
    bibtex: str


# --------------------------------------------------------------------------- #
# Client protocol + implementations
# --------------------------------------------------------------------------- #
@runtime_checkable
class ScholarClient(Protocol):
    """A title-search client returning candidate :class:`S2Record`s."""

    def search_title(
        self, title: str, year_hint: int | None, cutoff_date: str | None
    ) -> list[S2Record]:
        """Return up to a few candidate records for ``title`` (empty on miss)."""
        ...


class SemanticScholarClient:
    """Real Semantic Scholar title-search client (``scholar`` extra).

    Lazy-imports ``httpx`` inside :meth:`search_title` so importing this module
    stays hermetic. Reads an optional ``SEMANTIC_SCHOLAR_API_KEY`` from the
    environment for the ``X-API-KEY`` header. Returns ``[]`` on any non-200
    response, empty result, or network error (never raises for those); raises
    :class:`RetrievalDependencyError` only when ``httpx`` is not installed.
    """

    def __init__(self, *, api_key: str | None = None, timeout: float = _S2_TIMEOUT) -> None:
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        self.timeout = timeout

    def search_title(
        self, title: str, year_hint: int | None, cutoff_date: str | None
    ) -> list[S2Record]:
        """Query the S2 graph search endpoint and parse records (``[]`` on miss)."""
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RetrievalDependencyError(
                "httpx is required for SemanticScholarClient. Install with: uv sync --extra scholar"
            ) from exc

        headers = {"X-API-KEY": self.api_key} if self.api_key else {}
        params: dict[str, str | int] = {
            "query": title,
            "limit": _S2_LIMIT,
            "fields": _S2_FIELDS,
        }
        try:
            response = httpx.get(
                _S2_SEARCH_URL, headers=headers, params=params, timeout=self.timeout
            )
        except Exception:  # noqa: BLE001 - network failures degrade to no results
            return []
        if response.status_code != 200:
            return []
        try:
            data = response.json().get("data", [])
        except Exception:  # noqa: BLE001 - malformed body degrades to no results
            return []
        return [_record_from_s2(item) for item in data if item.get("title")]


def _record_from_s2(item: dict[str, Any]) -> S2Record:
    """Map a raw S2 JSON paper object to an :class:`S2Record`."""
    authors_raw = item.get("authors") or []
    authors = [str(a.get("name")) for a in authors_raw if isinstance(a, dict) and a.get("name")]
    journal_raw = item.get("journal")
    journal = None
    if isinstance(journal_raw, dict):
        name = journal_raw.get("name")
        journal = str(name) if name else None
    return S2Record(
        paper_id=str(item.get("paperId") or ""),
        title=str(item.get("title") or ""),
        authors=authors,
        venue=(str(item["venue"]) if item.get("venue") else None),
        year=(int(item["year"]) if isinstance(item.get("year"), int) else None),
        abstract=(str(item["abstract"]) if item.get("abstract") else None),
        citation_count=(
            int(item["citationCount"]) if isinstance(item.get("citationCount"), int) else None
        ),
        journal=journal,
        publication_date=(str(item["publicationDate"]) if item.get("publicationDate") else None),
    )


class FakeScholarClient:
    """Hermetic test double mapping query titles to canned records.

    Constructed with a ``{title: [S2Record, ...]}`` mapping; pure, no network.
    Lookup is case-insensitive on the query title.
    """

    def __init__(self, records_by_title: dict[str, list[S2Record]]) -> None:
        self._by_title = {key.lower(): value for key, value in records_by_title.items()}

    def search_title(
        self, title: str, year_hint: int | None, cutoff_date: str | None
    ) -> list[S2Record]:
        """Return the canned records for ``title`` (case-insensitive; ``[]`` on miss)."""
        return list(self._by_title.get(title.lower(), []))


# --------------------------------------------------------------------------- #
# Pure verification functions
# --------------------------------------------------------------------------- #
def fuzzy_ratio(a: str, b: str) -> int:
    """Return a 0-100 similarity ratio between ``a`` and ``b``.

    Prefers ``thefuzz.fuzz.ratio`` (the ``scholar`` extra) when importable;
    otherwise falls back to a stdlib :class:`difflib.SequenceMatcher` ratio
    scaled to 0-100 and rounded, so the hermetic path needs no ``thefuzz``.
    """
    try:
        from thefuzz import fuzz
    except ImportError:
        return round(difflib.SequenceMatcher(None, a, b).ratio() * 100)
    return int(fuzz.ratio(a, b))


def is_date_valid(publication_date: str | None, year: int | None, cutoff_date: str | None) -> bool:
    """Whether a record predates ``cutoff_date`` (``"YYYY-MM"``).

    Ported from PaperOrchestra's ``is_date_valid``. With no cutoff, everything
    passes. A parseable ``publication_date`` (``"YYYY-MM-DD"``) must fall strictly
    before the cutoff's first-of-month. Falling back to ``year``: an earlier year
    passes; the cutoff year passes only when the cutoff month is past January; a
    later year fails. Unparseable inputs default to valid.
    """
    if not cutoff_date:
        return True
    try:
        cutoff_year_str, cutoff_month_str = cutoff_date.split("-")
        cutoff_year, cutoff_month = int(cutoff_year_str), int(cutoff_month_str)
        cutoff_dt = datetime.datetime(cutoff_year, cutoff_month, 1)
    except Exception:  # noqa: BLE001 - malformed cutoff defaults to valid
        return True

    if publication_date:
        try:
            pub_dt = datetime.datetime.strptime(publication_date, "%Y-%m-%d")
            return pub_dt < cutoff_dt
        except ValueError:
            pass
    if year is not None:
        if year < cutoff_year:
            return True
        if year == cutoff_year and cutoff_month > 1:
            return True
        return False
    return True


def best_match(
    query: Reference,
    records: list[S2Record],
    *,
    threshold: int = 70,
    year_bonus: int = 10,
    cutoff_date: str | None = None,
) -> VerifiedCitation | None:
    """Pick the best record for ``query`` above ``threshold`` (or ``None``).

    The recency gate is applied *here*: each record is checked with
    :func:`is_date_valid` against ``cutoff_date`` (``"YYYY-MM"``) and any record
    not strictly before the cutoff is skipped; with ``cutoff_date`` ``None`` all
    records pass (no-op). Records lacking a non-empty abstract are also skipped.
    Scores by :func:`fuzzy_ratio` on lowercased titles, adding ``year_bonus`` when
    the record's year matches ``query.year_hint``. The highest-scoring record is
    returned only when its score is strictly greater than ``threshold``.
    """
    best: S2Record | None = None
    best_score = 0
    for record in records:
        if not record.title:
            continue
        if not is_date_valid(record.publication_date, record.year, cutoff_date):
            continue
        if not (record.abstract and record.abstract.strip()):
            continue
        score = fuzzy_ratio(query.query_title.lower(), record.title.lower())
        if query.year_hint is not None and record.year == query.year_hint:
            score += year_bonus
        if score > best_score:
            best_score = score
            best = record
    if best is None or best_score <= threshold:
        return None
    key = mint_citation_key(best)
    return VerifiedCitation(
        record=best,
        score=float(best_score),
        citation_key=key,
        bibtex=_bibtex(best, key),
    )


_STOPWORDS = {"a", "an", "the", "of", "on", "in", "and", "for", "to", "with"}


def mint_citation_key(record: S2Record) -> str:
    """Mint a BibTeX key: first-author lastname + year + two title words.

    Falls back to ``"anon"`` / ``"nd"`` when author or year is missing. Only
    alphanumeric characters survive so the key is BibTeX-safe.
    """
    if record.authors:
        last = record.authors[0].split()[-1] if record.authors[0].split() else "anon"
    else:
        last = "anon"
    last = "".join(ch for ch in last if ch.isalnum()).lower() or "anon"
    year = str(record.year) if record.year is not None else "nd"
    words = [w for w in record.title.lower().split() if w not in _STOPWORDS]
    title_words = "".join("".join(ch for ch in word if ch.isalnum()) for word in words[:2])
    return f"{last}{year}{title_words}"


def dedupe(citations: list[VerifiedCitation]) -> list[VerifiedCitation]:
    """Drop duplicate records (by ``paper_id``) and disambiguate key collisions.

    The first occurrence of each ``paper_id`` is kept (preserving order). Distinct
    records that mint the same key get an ``a``/``b``/``c`` suffix (the first keeps
    the bare key), and the suffix is reflected in both ``citation_key`` and the
    rendered ``bibtex``.
    """
    seen_ids: set[str] = set()
    unique: list[VerifiedCitation] = []
    for citation in citations:
        pid = citation.record.paper_id
        if pid and pid in seen_ids:
            continue
        if pid:
            seen_ids.add(pid)
        unique.append(citation)

    key_counts: dict[str, int] = {}
    for citation in unique:
        key_counts[citation.citation_key] = key_counts.get(citation.citation_key, 0) + 1

    seen_counts: dict[str, int] = {}
    resolved: list[VerifiedCitation] = []
    for citation in unique:
        base = citation.citation_key
        if key_counts[base] > 1:
            index = seen_counts.get(base, 0)
            seen_counts[base] = index + 1
            suffix = chr(ord("a") + index)
            new_key = f"{base}{suffix}"
            resolved.append(
                citation.model_copy(
                    update={
                        "citation_key": new_key,
                        "bibtex": _bibtex(citation.record, new_key),
                    }
                )
            )
        else:
            resolved.append(citation)
    return resolved


def verified_coverage(
    candidates: list[Candidate], verified: list[VerifiedCitation]
) -> tuple[int, float, bool]:
    """Return ``(min_required, ratio, meets)`` coverage against a 90% target.

    ``min_required`` is ``int(len(candidates) * 0.9)``; ``ratio`` is
    ``len(verified) / len(candidates)``; ``meets`` is ``len(verified) >=
    min_required``. With no candidates the result is ``(0, 0.0, True)`` (vacuously
    met).
    """
    total = len(candidates)
    if total == 0:
        return 0, 0.0, True
    min_required = int(total * 0.9)
    ratio = len(verified) / total
    return min_required, ratio, len(verified) >= min_required


def _bibtex(record: S2Record, key: str) -> str:
    """Render a BibTeX entry (``@article`` if a journal is present else ``@inproceedings``)."""
    entry_type = "article" if record.journal else "inproceedings"
    fields: list[tuple[str, str]] = []
    if record.authors:
        fields.append(("author", " and ".join(record.authors)))
    if record.title:
        fields.append(("title", record.title))
    if record.journal:
        fields.append(("journal", record.journal))
    elif record.venue:
        fields.append(("booktitle", record.venue))
    if record.year is not None:
        fields.append(("year", str(record.year)))
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
    return f"@{entry_type}{{{key},\n{body}\n}}"


def to_bibtex(citation: VerifiedCitation) -> str:
    """Return the BibTeX entry for a verified citation."""
    return citation.bibtex


def verify(
    references: list[Reference],
    client: ScholarClient,
    *,
    cutoff_date: str | None = None,
    threshold: int = 70,
) -> list[VerifiedCitation]:
    """Verify ``references`` against ``client``, returning deduped citations.

    For each reference, searches the client, applies :func:`best_match` (which
    enforces the ``cutoff_date`` recency gate), and collects the matches; the
    result is :func:`dedupe`-d so repeated records and colliding keys are
    resolved.
    """
    matched: list[VerifiedCitation] = []
    for reference in references:
        records = client.search_title(reference.query_title, reference.year_hint, cutoff_date)
        match = best_match(reference, records, threshold=threshold, cutoff_date=cutoff_date)
        if match is not None:
            matched.append(match)
    return dedupe(matched)


__all__ = [
    "Reference",
    "Candidate",
    "S2Record",
    "VerifiedCitation",
    "ScholarClient",
    "SemanticScholarClient",
    "FakeScholarClient",
    "RetrievalDependencyError",
    "fuzzy_ratio",
    "is_date_valid",
    "best_match",
    "mint_citation_key",
    "dedupe",
    "verified_coverage",
    "to_bibtex",
    "verify",
    "resolve_scholar_client",
]


def resolve_scholar_client(spec: str | None = None) -> ScholarClient | None:
    """Resolve a scholar client from a spec string (e.g. the ``CLIO_SCHOLAR`` env var).

    ``auto`` (default) / ``s2`` -> a :class:`SemanticScholarClient` (which reads
    ``SEMANTIC_SCHOLAR_API_KEY`` from the environment); ``off`` / ``none`` ->
    ``None`` (the citation expert then reports "no scholar client configured").
    Construction performs no network I/O — the HTTP call is lazy at search time —
    so wiring this by default is safe even without the ``scholar`` extra
    installed (a real call without it surfaces as ``metadata["error"]``).
    """
    name = (spec or "auto").strip().lower()
    if name in ("off", "none", ""):
        return None
    return SemanticScholarClient()

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
import html
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from pydantic import BaseModel, Field

from clio_author.retrieval.rag import RetrievalDependencyError

# Semantic Scholar graph API: title-search endpoint, fields, and limits.
_S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_S2_FIELDS = "title,authors,venue,year,abstract,citationCount,journal,publicationDate"
_S2_LIMIT = 3
_S2_TIMEOUT = 5.0
_OPENALEX_WORKS_URL = "https://api.openalex.org/works"
_CROSSREF_WORKS_URL = "https://api.crossref.org/works"
_ARXIV_QUERY_URL = "https://export.arxiv.org/api/query"
_FALLBACK_TIMEOUT = 8.0
_S2_RATE_STATE = Path(tempfile.gettempdir()) / "clio-author-s2-rate-limit"

try:  # pragma: no cover - fcntl is available on the supported Linux/macOS path.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


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
    external_ids: dict[str, str] = Field(default_factory=dict)


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

    _rate_lock = threading.Lock()
    _last_request_at: float | None = None

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = _S2_TIMEOUT,
        min_interval: float = 1.0,
        rate_state_path: str | Path | None = None,
        _clock: Any = time.monotonic,
        _sleep: Any = time.sleep,
    ) -> None:
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        self.timeout = timeout
        self.min_interval = min_interval
        self.rate_state_path = (
            Path(rate_state_path) if rate_state_path is not None else _S2_RATE_STATE
        )
        self._clock = _clock
        self._sleep = _sleep

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
        for attempt in range(2):
            try:
                self._throttle()
                response = httpx.get(
                    _S2_SEARCH_URL, headers=headers, params=params, timeout=self.timeout
                )
            except Exception:  # noqa: BLE001 - network failures degrade to no results
                return []
            if response.status_code == 200:
                break
            if response.status_code != 429 or attempt == 1:
                return []
        else:  # pragma: no cover - loop always returns or breaks
            return []
        try:
            data = response.json().get("data", [])
        except Exception:  # noqa: BLE001 - malformed body degrades to no results
            return []
        return [_record_from_s2(item) for item in data if item.get("title")]

    def _throttle(self) -> None:
        """Respect S2's 1 request/second limit across CLI processes."""
        if self.min_interval <= 0:
            return
        if fcntl is not None:
            self._throttle_cross_process()
            return
        self._throttle_in_process()

    def _throttle_in_process(self) -> None:
        """Fallback throttle for platforms without ``fcntl`` file locks."""
        with self._rate_lock:
            now = float(self._clock())
            last = self.__class__._last_request_at
            if last is not None:
                wait = self.min_interval - (now - last)
                if wait > 0:
                    self._sleep(wait)
                    now = float(self._clock())
            self.__class__._last_request_at = now

    def _throttle_cross_process(self) -> None:
        """File-lock-backed throttle for repeated ``uv run clio-author`` calls.

        Semantic Scholar keys are rate-limited across all endpoints, while CLI
        invocations run in separate Python processes. A small temp-file state
        record lets those processes share the last request timestamp without
        adding a runtime dependency.
        """
        with self._rate_lock:
            self.rate_state_path.parent.mkdir(parents=True, exist_ok=True)
            with self.rate_state_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    handle.seek(0)
                    last = _parse_rate_timestamp(handle.read())
                    process_last = self.__class__._last_request_at
                    if process_last is not None and (last is None or process_last > last):
                        last = process_last

                    now = float(self._clock())
                    if last is not None and last <= now:
                        wait = self.min_interval - (now - last)
                        if wait > 0:
                            self._sleep(wait)
                            now = float(self._clock())

                    self.__class__._last_request_at = now
                    handle.seek(0)
                    handle.truncate()
                    handle.write(f"{now:.9f}")
                    handle.flush()
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
        external_ids={
            str(key): str(value)
            for key, value in (item.get("externalIds") or {}).items()
            if value is not None
        }
        if isinstance(item.get("externalIds"), dict)
        else {},
    )


def _parse_rate_timestamp(raw: str) -> float | None:
    """Parse the persisted S2 throttle timestamp."""
    try:
        return float(raw.strip())
    except ValueError:
        return None


class OpenAlexClient:
    """No-key title-search client backed by the OpenAlex Works API.

    Uses only the standard library. An optional ``OPENALEX_MAILTO`` environment
    variable is sent as the API etiquette contact parameter when present.
    """

    def __init__(self, *, mailto: str | None = None, timeout: float = _FALLBACK_TIMEOUT) -> None:
        self.mailto = mailto or os.environ.get("OPENALEX_MAILTO")
        self.timeout = timeout

    def search_title(
        self, title: str, year_hint: int | None, cutoff_date: str | None
    ) -> list[S2Record]:
        """Query OpenAlex works by title/search text (``[]`` on miss/failure)."""
        params: dict[str, str | int] = {"search": title, "per-page": _S2_LIMIT}
        if year_hint is not None:
            params["filter"] = f"publication_year:{year_hint}"
        if self.mailto:
            params["mailto"] = self.mailto
        try:
            data = _get_json(_OPENALEX_WORKS_URL, params, timeout=self.timeout)
            results = data.get("results", [])
        except Exception:  # noqa: BLE001 - network failures degrade to no results
            return []
        return [_record_from_openalex(item) for item in results if item.get("display_name")]


def _record_from_openalex(item: dict[str, Any]) -> S2Record:
    """Map a raw OpenAlex work object to an :class:`S2Record`."""
    authorships = item.get("authorships") or []
    authors: list[str] = []
    for authorship in authorships:
        author = authorship.get("author") if isinstance(authorship, dict) else None
        if isinstance(author, dict) and author.get("display_name"):
            authors.append(str(author["display_name"]))
    primary_location = item.get("primary_location") or {}
    source = primary_location.get("source") if isinstance(primary_location, dict) else None
    venue = (
        str(source["display_name"])
        if isinstance(source, dict) and source.get("display_name")
        else None
    )
    return S2Record(
        paper_id=f"openalex:{item.get('id') or ''}",
        title=str(item.get("display_name") or ""),
        authors=authors,
        venue=venue,
        year=(
            int(item["publication_year"]) if isinstance(item.get("publication_year"), int) else None
        ),
        abstract=_openalex_abstract(item.get("abstract_inverted_index")),
        citation_count=(
            int(item["cited_by_count"]) if isinstance(item.get("cited_by_count"), int) else None
        ),
        journal=venue if _openalex_is_journal(source) else None,
        publication_date=(str(item["publication_date"]) if item.get("publication_date") else None),
    )


def _openalex_is_journal(source: Any) -> bool:
    """Best-effort journal/source-type check for OpenAlex source metadata."""
    if not isinstance(source, dict):
        return False
    source_type = str(source.get("type") or "").lower()
    return source_type == "journal"


def _openalex_abstract(index: Any) -> str | None:
    """Reconstruct OpenAlex's inverted-index abstract representation."""
    if not isinstance(index, dict) or not index:
        return None
    positions: list[tuple[int, str]] = []
    for word, raw_locs in index.items():
        if not isinstance(raw_locs, list):
            continue
        for loc in raw_locs:
            if isinstance(loc, int):
                positions.append((loc, str(word)))
    if not positions:
        return None
    return " ".join(word for _, word in sorted(positions))


class CrossrefClient:
    """No-key title-search client backed by the Crossref Works REST API."""

    def __init__(self, *, mailto: str | None = None, timeout: float = _FALLBACK_TIMEOUT) -> None:
        self.mailto = mailto or os.environ.get("CROSSREF_MAILTO")
        self.timeout = timeout

    def search_title(
        self, title: str, year_hint: int | None, cutoff_date: str | None
    ) -> list[S2Record]:
        """Query Crossref works by bibliographic text (``[]`` on miss/failure)."""
        params: dict[str, str | int] = {
            "query.bibliographic": title,
            "rows": _S2_LIMIT,
        }
        if self.mailto:
            params["mailto"] = self.mailto
        try:
            data = _get_json(_CROSSREF_WORKS_URL, params, timeout=self.timeout)
            items = data.get("message", {}).get("items", [])
        except Exception:  # noqa: BLE001 - network failures degrade to no results
            return []
        return [_record_from_crossref(item) for item in items if item.get("title")]


def _record_from_crossref(item: dict[str, Any]) -> S2Record:
    """Map a raw Crossref work object to an :class:`S2Record`."""
    authors = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        given = str(author.get("given") or "").strip()
        family = str(author.get("family") or "").strip()
        name = " ".join(part for part in (given, family) if part)
        if name:
            authors.append(name)
    title = _first_string(item.get("title"))
    container = _first_string(item.get("container-title"))
    year = _crossref_year(item)
    return S2Record(
        paper_id=f"crossref:{item.get('DOI') or item.get('URL') or title}",
        title=title,
        authors=authors,
        venue=container,
        year=year,
        abstract=_clean_crossref_abstract(item.get("abstract")),
        citation_count=(
            int(item["is-referenced-by-count"])
            if isinstance(item.get("is-referenced-by-count"), int)
            else None
        ),
        journal=container if str(item.get("type") or "").lower() == "journal-article" else None,
        publication_date=_crossref_date(item),
    )


class ArxivScholarClient:
    """No-key title-search client backed by the public arXiv Atom API."""

    def __init__(self, *, timeout: float = _FALLBACK_TIMEOUT) -> None:
        self.timeout = timeout

    def search_title(
        self, title: str, year_hint: int | None, cutoff_date: str | None
    ) -> list[S2Record]:
        """Query arXiv by title (``[]`` on miss/failure)."""
        params: dict[str, str | int] = {
            "search_query": f'ti:"{title}"',
            "start": 0,
            "max_results": _S2_LIMIT,
        }
        try:
            raw = _get_text(_ARXIV_QUERY_URL, params, timeout=self.timeout)
            root = ElementTree.fromstring(raw)
        except Exception:  # noqa: BLE001 - network/XML failures degrade to no results
            return []
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        records: list[S2Record] = []
        for entry in root.findall("atom:entry", ns):
            record = _record_from_arxiv(entry, ns)
            if record.title:
                records.append(record)
        return records


def _record_from_arxiv(entry: ElementTree.Element, ns: dict[str, str]) -> S2Record:
    """Map an arXiv Atom entry to an :class:`S2Record`."""
    title = _normalise_space(entry.findtext("atom:title", default="", namespaces=ns))
    abstract = _normalise_space(entry.findtext("atom:summary", default="", namespaces=ns))
    published = entry.findtext("atom:published", default="", namespaces=ns)
    year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None
    authors = [
        _normalise_space(author.findtext("atom:name", default="", namespaces=ns))
        for author in entry.findall("atom:author", ns)
    ]
    authors = [author for author in authors if author]
    arxiv_id = ""
    raw_id = entry.findtext("atom:id", default="", namespaces=ns)
    if raw_id:
        arxiv_id = raw_id.rstrip("/").split("/")[-1]
    return S2Record(
        paper_id=f"arxiv:{arxiv_id}",
        title=title,
        authors=authors,
        venue="arXiv",
        year=year,
        abstract=abstract or None,
        citation_count=None,
        journal=None,
        publication_date=published[:10] if len(published) >= 10 else None,
    )


class CascadeScholarClient:
    """Search several scholar clients and return their combined candidates."""

    def __init__(self, clients: list[ScholarClient]) -> None:
        self.clients = clients

    def search_title(
        self, title: str, year_hint: int | None, cutoff_date: str | None
    ) -> list[S2Record]:
        """Search each configured backend, ignoring backend failures."""
        merged: list[S2Record] = []
        for client in self.clients:
            try:
                records = client.search_title(title, year_hint, cutoff_date)
            except Exception:  # noqa: BLE001 - fallback backends should not abort the cascade
                continue
            if records:
                merged.extend(records)
        return merged


def _get_json(url: str, params: dict[str, str | int], *, timeout: float) -> dict[str, Any]:
    """Fetch a JSON object with stdlib urllib."""
    text = _get_text(url, params, timeout=timeout, accept="application/json")
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def _get_text(
    url: str, params: dict[str, str | int], *, timeout: float, accept: str | None = None
) -> str:
    """Fetch text from ``url`` with encoded query params."""
    full_url = f"{url}?{urlencode(params)}"
    headers = {"User-Agent": "clio-author/0.2 (+https://github.com/SIslamMun/clio-author)"}
    if accept:
        headers["Accept"] = accept
    req = Request(full_url, headers=headers)  # noqa: S310 - public scholarly metadata APIs
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - public scholarly metadata APIs
        return response.read().decode("utf-8", errors="replace")


def _first_string(raw: Any) -> str:
    """Return the first string from a scalar/list-ish API field."""
    if isinstance(raw, list):
        for item in raw:
            if item:
                return str(item)
        return ""
    return str(raw or "")


def _crossref_year(item: dict[str, Any]) -> int | None:
    """Extract the first available year from Crossref date-parts."""
    for key in ("published-print", "published-online", "published", "issued", "created"):
        date = item.get(key)
        year = _year_from_date_parts(date)
        if year is not None:
            return year
    return None


def _crossref_date(item: dict[str, Any]) -> str | None:
    """Extract a YYYY-MM-DD-ish date from Crossref date-parts."""
    for key in ("published-print", "published-online", "published", "issued", "created"):
        date = item.get(key)
        rendered = _date_from_date_parts(date)
        if rendered is not None:
            return rendered
    return None


def _year_from_date_parts(raw: Any) -> int | None:
    """Extract a year from Crossref ``date-parts``."""
    parts = _date_parts(raw)
    if parts and isinstance(parts[0], int):
        return parts[0]
    return None


def _date_from_date_parts(raw: Any) -> str | None:
    """Render Crossref ``date-parts`` as YYYY-MM-DD with missing values filled."""
    parts = _date_parts(raw)
    if not parts or not isinstance(parts[0], int):
        return None
    year = parts[0]
    month = parts[1] if len(parts) > 1 and isinstance(parts[1], int) else 1
    day = parts[2] if len(parts) > 2 and isinstance(parts[2], int) else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _date_parts(raw: Any) -> list[Any] | None:
    """Return the first Crossref date-parts list."""
    if not isinstance(raw, dict):
        return None
    parts = raw.get("date-parts")
    if not isinstance(parts, list) or not parts:
        return None
    first = parts[0]
    return first if isinstance(first, list) else None


def _clean_crossref_abstract(raw: Any) -> str | None:
    """Convert Crossref's often-HTML abstract field to plain text."""
    if not raw:
        return None
    text = re.sub(r"<[^>]+>", " ", str(raw))
    return _normalise_space(html.unescape(text)) or None


def _normalise_space(text: str) -> str:
    """Collapse whitespace in API text fields."""
    return " ".join(text.split())


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

    ``min_required`` is ``ceil(len(candidates) * 0.9)``; ``ratio`` is
    ``len(verified) / len(candidates)``; ``meets`` is ``len(verified) >=
    min_required``. With no candidates the result is ``(0, 0.0, True)`` (vacuously
    met).
    """
    total = len(candidates)
    if total == 0:
        return 0, 0.0, True
    min_required = (total * 9 + 9) // 10
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
    "OpenAlexClient",
    "CrossrefClient",
    "ArxivScholarClient",
    "CascadeScholarClient",
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

    ``auto`` (default) / ``cascade`` tries Semantic Scholar first, then OpenAlex,
    Crossref, and arXiv. ``semantic`` / ``s2`` selects Semantic Scholar only;
    ``openalex``, ``crossref``, and ``arxiv`` select the no-key fallback clients.
    ``off`` / ``none`` returns ``None`` (the citation expert then reports "no
    scholar client configured"). Construction performs no network I/O.
    """
    name = (spec or "auto").strip().lower()
    if name in ("off", "none", "offline", "disabled", ""):
        return None
    if name in ("auto", "cascade", "all"):
        return CascadeScholarClient(
            [SemanticScholarClient(), OpenAlexClient(), CrossrefClient(), ArxivScholarClient()]
        )
    if name in ("semantic", "semanticscholar", "semantic-scholar", "s2"):
        return SemanticScholarClient()
    if name in ("openalex", "oa"):
        return OpenAlexClient()
    if name in ("crossref", "cr"):
        return CrossrefClient()
    if name in ("arxiv", "arxiv.org"):
        return ArxivScholarClient()
    raise ValueError(
        "unknown CLIO_SCHOLAR="
        f"{spec!r} (use one of: auto, semantic, openalex, crossref, arxiv, off)"
    )

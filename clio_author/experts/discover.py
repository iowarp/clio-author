"""The discovery expert: find real candidate papers for a topic via search.

:class:`DiscoverExpert` queries scholarly search endpoints (Semantic Scholar /
OpenAlex / Crossref / arXiv, via a configured
:class:`~clio_author.retrieval.scholar.ScholarClient`) for a free-text topic and
returns the *real* candidate records it finds. It complements two adjacent
experts:

- :class:`~clio_author.experts.citation.CitationExpert` (``cite``) only verifies
  titles the caller already supplies.
- :class:`~clio_author.experts.research.ResearchExpert` (``research``) asks the
  LLM to *propose* plausible titles.

Discovery is pure API search: deterministic (no LLM), dependency-free (the
client uses stdlib ``urllib`` / lazy ``httpx``), and grounded -- it never
fabricates records. Like the other experts it never raises: a missing query, no
configured client, or any failure produces an error-flagged
:class:`AgentOutput` (appended once). With no scholar client configured (the
default hermetic path) it reports "no scholar client configured".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.retrieval.scholar import (
    S2Record,
    ScholarClient,
    discover_papers,
    mint_citation_key,
)
from clio_author.retrieval.scholar import (
    _bibtex as _record_bibtex,  # noqa: PLC2701 - reuse the internal BibTeX renderer
)

DISCOVER_SYSTEM_PROMPT = (
    "You are the paper-discovery expert. Given a topic or query you find real "
    "candidate papers by searching scholarly indexes (Semantic Scholar, "
    "OpenAlex, Crossref, arXiv). You return only records the search actually "
    "returns; you never invent titles, authors, or identifiers."
)


class DiscoverExpert(BaseAgent):
    """Expert that finds real candidate papers for a topic via scholarly search."""

    def __init__(
        self, llm: LLMClient | None = None, *, scholar_client: ScholarClient | None = None
    ) -> None:
        """Build a discovery expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient`. Unused for
                the deterministic search path but accepted for parity with the
                other experts (so the agent can share one client).
            scholar_client: Scholar client (the network seam). When ``None`` a run
                returns an error-flagged output rather than guessing or touching
                the network.
        """
        super().__init__(
            role="discover",
            system_prompt=DISCOVER_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._scholar = scholar_client

    @staticmethod
    def _resolve_query(payload: dict[str, Any]) -> str:
        """Resolve the discovery query from ``query`` / ``topic``."""
        query = str(payload.get("query") or "").strip()
        if query:
            return query
        return str(payload.get("topic") or "").strip()

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Discover candidate papers for the topic in ``task``. Never raises.

        Reads ``query`` (or ``topic``), ``limit`` (int, default 10),
        ``cutoff_date`` (optional ``"YYYY-MM"``), and ``out_dir`` (optional).
        With a configured :class:`ScholarClient` it calls :func:`discover_papers`
        and returns ``structured={"papers": [...], "count": N}``, a one-line
        summary as ``content``, and ``metadata={count, backends_tried,
        backend_outcomes}`` (``backends_tried`` is what was *configured*;
        ``backend_outcomes`` is what each one actually did). When
        ``out_dir`` is set it writes ``discovered.json`` and ``discovered.bib``
        there (best-effort). With no client it reports an error-flagged output.
        """
        payload = task.payload
        query = self._resolve_query(payload)
        if not query:
            return self._error(session, "no 'query'/'topic' provided")
        if self._scholar is None:
            return self._error(session, "no scholar client configured")

        try:
            limit = int(payload.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, limit)
        cutoff_date = payload.get("cutoff_date")
        cutoff = str(cutoff_date).strip() if cutoff_date else None

        try:
            records = discover_papers(query, self._scholar, limit=limit, cutoff_date=cutoff)
            papers = [_record_view(record) for record in records]

            wrote: list[str] = []
            out_dir = payload.get("out_dir")
            if out_dir:
                wrote = _write_discovered(Path(out_dir), records, papers)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        backends_tried = _backends_tried(self._scholar)
        content = (
            f"Discovered {len(papers)} candidate paper(s) for '{query}' "
            f"(searched: {', '.join(backends_tried)})."
            if papers
            else f"No candidate papers found for '{query}' (searched: {', '.join(backends_tried)})."
        )
        output = AgentOutput(
            agent=self.name,
            content=content,
            structured={"papers": papers, "count": len(papers)},
            metadata={
                "count": len(papers),
                "backends_tried": backends_tried,
                "backend_outcomes": _backend_outcomes(self._scholar),
                "wrote": wrote,
            },
        )
        session.add(output)
        return output


def _record_view(record: S2Record) -> dict[str, Any]:
    """Render an :class:`S2Record` as the discovery output's paper view."""
    return {
        "title": record.title,
        "year": record.year,
        "authors": list(record.authors),
        "venue": record.venue,
        "abstract": record.abstract,
        "paper_id": record.paper_id,
        "url": _record_url(record),
    }


def _record_url(record: S2Record) -> str | None:
    """Best-effort canonical URL for a record from its id / external ids."""
    doi = record.external_ids.get("DOI")
    if doi:
        return f"https://doi.org/{doi}"
    arxiv = record.external_ids.get("ArXiv")
    if arxiv:
        return f"https://arxiv.org/abs/{arxiv}"
    pid = record.paper_id
    if pid.startswith("arxiv:"):
        return f"https://arxiv.org/abs/{pid[len('arxiv:') :]}"
    if pid.startswith("crossref:") and "/" in pid[len("crossref:") :]:
        return f"https://doi.org/{pid[len('crossref:') :]}"
    if pid.startswith("openalex:"):
        return pid[len("openalex:") :] or None
    if pid and not pid.startswith(("crossref:",)):
        return f"https://www.semanticscholar.org/paper/{pid}"
    return None


def _record_bib(record: S2Record) -> str:
    """Render a BibTeX entry for a discovered record (unverified)."""
    return _record_bibtex(record, mint_citation_key(record))


def _write_discovered(
    out_dir: Path, records: list[S2Record], papers: list[dict[str, Any]]
) -> list[str]:
    """Write ``discovered.json`` + ``discovered.bib`` under ``out_dir``. Best-effort.

    Mirrors the no-clobber persistence used elsewhere: an existing file is
    skipped rather than overwritten, so a failure degrades to a shorter
    ``wrote`` list instead of an exception.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    wrote: list[str] = []
    json_path = out_dir / "discovered.json"
    if not json_path.exists():
        try:
            json_path.write_text(
                json.dumps({"papers": papers, "count": len(papers)}, indent=2),
                encoding="utf-8",
            )
            wrote.append(str(json_path))
        except OSError:
            pass
    bib_path = out_dir / "discovered.bib"
    if records and not bib_path.exists():
        try:
            bib_path.write_text(
                "\n\n".join(_record_bib(record) for record in records) + "\n",
                encoding="utf-8",
            )
            wrote.append(str(bib_path))
        except OSError:
            pass
    return wrote


def _backends_tried(client: ScholarClient) -> list[str]:
    """Name the backend(s) a (possibly cascading) client is *configured* with.

    Configuration is not availability: a backend whose optional dependency is
    missing is skipped at search time. Use :func:`_backend_outcomes` for what
    actually ran.
    """
    clients = getattr(client, "clients", None)
    if isinstance(clients, list) and clients:
        return [type(sub).__name__ for sub in clients]
    return [type(client).__name__]


def _backend_outcomes(client: ScholarClient) -> dict[str, str]:
    """Per-backend outcome of the search just run (``{}`` when unrecorded).

    Values are ``"ok: <n>"``, ``"unavailable: <reason>"``, ``"error"``, or
    ``"not reached: ..."``. This is what distinguishes "searched and found
    nothing" from "never ran because httpx is not installed" -- the two are
    indistinguishable in ``backends_tried`` alone.
    """
    outcomes = getattr(client, "last_outcomes", None)
    return dict(outcomes) if isinstance(outcomes, dict) else {}


__all__ = ["DiscoverExpert", "DISCOVER_SYSTEM_PROMPT"]

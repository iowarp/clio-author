"""The citation expert: grounded citation discovery, verification, suggestions.

:class:`CitationExpert` takes proposed citation *candidates* (from
``task.payload["candidates"]`` or ``["references"]``), verifies each against a
:class:`~clio_author.retrieval.scholar.ScholarClient`, and emits **suggestions
only**: a ``suggested.bib`` plus a citation map. It never overwrites a user
bibliography -- any write whose basename is ``references.bib``, or that would
clobber an existing file, is refused.

Like :class:`~clio_author.experts.paper_qa.PaperQAExpert`, this expert never
raises: missing inputs, no configured client, or any failure produce an
error-flagged :class:`AgentOutput` (appended once to the session) so a harness
run degrades gracefully. The default :class:`EchoLLMClient` keeps it offline;
discovery via LLM/web is deferred, so candidates must be provided.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.retrieval.scholar import (
    Candidate,
    Reference,
    ScholarClient,
    to_bibtex,
    verified_coverage,
    verify,
)

CITATION_SYSTEM_PROMPT = (
    "You are the citation expert. You verify proposed citations against Semantic "
    "Scholar and emit SUGGESTIONS ONLY. You never overwrite or edit an existing "
    "bibliography: you may write a separate 'suggested.bib' and a citation map, "
    "but you must refuse to touch 'references.bib' or any existing user file. "
    "Report verification coverage honestly; do not invent records."
)

# Basenames the expert refuses to write, to protect a user's bibliography.
_PROTECTED_BASENAMES = {"references.bib"}


class CitationExpert(BaseAgent):
    """Expert that verifies citation candidates and emits suggestions only."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        client: ScholarClient | None = None,
        cutoff_date: str | None = None,
        threshold: int = 70,
    ) -> None:
        """Build a citation expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient`.
            client: Scholar client (the network seam). When ``None``, a run
                returns an error-flagged output rather than guessing or hitting
                the network.
            cutoff_date: Optional ``"YYYY-MM"`` recency gate passed to the client.
            threshold: Minimum fuzzy match score (exclusive) to accept a record.
        """
        super().__init__(
            role="citation",
            system_prompt=CITATION_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._client = client
        self.cutoff_date = cutoff_date
        self.threshold = threshold

    @staticmethod
    def _coerce_candidates(raw: Any) -> list[Candidate]:
        """Validate a list of candidate dicts/objects into :class:`Candidate`s."""
        if not isinstance(raw, list):
            raise ValueError("candidates must be a list")
        return [Candidate.model_validate(item) for item in raw]

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Verify ``payload["candidates"]`` (or ``["references"]``) and suggest citations.

        Coerces candidates via :class:`Candidate`, then (with a configured
        :class:`ScholarClient`) verifies them, computes coverage against the 90%
        target, and builds a ``suggested_bibtex`` blob plus a ``citation_map``
        (``{citation_key: title}``). When ``payload["out_dir"]`` is set it writes
        ONLY ``suggested.bib`` and ``suggested_citation_map.json`` there, refusing
        any protected/existing target. Returns an :class:`AgentOutput` with a
        human summary as ``content``, the suggestions in ``structured``, and
        counts in ``metadata``. Never raises: any failure produces an
        error-flagged output (appended once).
        """
        raw_candidates = task.payload.get("candidates")
        if raw_candidates is None:
            raw_candidates = task.payload.get("references")
        if raw_candidates is None:
            return self._error(session, "no 'candidates'/'references' in task.payload")

        if self._client is None:
            return self._error(session, "no scholar client configured")

        try:
            candidates = self._coerce_candidates(raw_candidates)
            if not candidates:
                return self._error(session, "no candidates to verify")

            references = [
                Reference(query_title=c.title, year_hint=c.year, raw=c.reason) for c in candidates
            ]
            verified = verify(
                references,
                self._client,
                cutoff_date=self.cutoff_date,
                threshold=self.threshold,
            )
            min_required, ratio, meets = verified_coverage(candidates, verified)

            suggested_bibtex = "\n\n".join(to_bibtex(v) for v in verified)
            citation_map = {v.citation_key: v.record.title for v in verified}

            wrote: list[str] = []
            out_dir = task.payload.get("out_dir")
            if out_dir:
                wrote = self._write_suggestions(Path(out_dir), suggested_bibtex, citation_map)

            coverage = {
                "min_required": min_required,
                "ratio": ratio,
                "meets_90pct": meets,
            }
            content = (
                f"Verified {len(verified)}/{len(candidates)} candidate citations "
                f"(>=90% target: {'met' if meets else 'not met'}). "
                "Emitted suggestions only; no existing bibliography was modified."
            )
        except _RefusedWriteError as exc:
            return self._error(session, str(exc))
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        output = AgentOutput(
            agent=self.name,
            content=content,
            structured={
                "verified": [v.model_dump() for v in verified],
                "suggested_bibtex": suggested_bibtex,
                "citation_map": citation_map,
                "coverage": coverage,
            },
            metadata={
                "num_candidates": len(candidates),
                "num_verified": len(verified),
                "meets_90pct": meets,
                "wrote": wrote,
            },
        )
        session.add(output)
        return output

    def _write_suggestions(
        self,
        out_dir: Path,
        suggested_bibtex: str,
        citation_map: dict[str, str],
        *,
        bib_name: str = "suggested.bib",
    ) -> list[str]:
        """Write ``suggested.bib`` + ``suggested_citation_map.json`` under ``out_dir``.

        Refuses (raises :class:`_RefusedWriteError`) if any target basename is
        protected (e.g. ``references.bib``), is a symlink (regardless of whether
        its target exists -- a dangling link must not be followed), or already
        exists, so a user's bibliography is never clobbered or written through.
        Writes are performed with :func:`os.open` using
        ``O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW`` so a symlink at the path is
        never followed and an existing file is never clobbered atomically; an
        ``OSError`` from that open (e.g. a race) is converted to a refusal.
        ``bib_name`` is overridable only so the protected-basename guard can be
        exercised directly in tests; the run path always uses ``suggested.bib``.
        """
        bib_path = out_dir / bib_name
        map_path = out_dir / "suggested_citation_map.json"
        for path in (bib_path, map_path):
            if path.name in _PROTECTED_BASENAMES:
                raise _RefusedWriteError(
                    f"refusing to write protected bibliography file: {path.name}"
                )
            if path.is_symlink() or path.exists():
                raise _RefusedWriteError(f"refusing to overwrite existing file: {path}")
        out_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(bib_path, suggested_bibtex)
        _atomic_write_text(map_path, json.dumps(citation_map, indent=2))
        return [str(bib_path), str(map_path)]


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path``, never following a symlink or clobbering a file.

    Opens with ``O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW`` so an existing file or
    a symlink at the path causes an :class:`OSError` (``FileExistsError`` /
    ``ELOOP``) rather than a write-through; that error is re-raised as a
    :class:`_RefusedWriteError` so :meth:`CitationExpert.run` flags it on the
    output instead of raising.
    """
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o644)
    except OSError as exc:
        raise _RefusedWriteError(f"refusing to write {path}: {exc}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


class _RefusedWriteError(RuntimeError):
    """Raised internally when a write target is protected or would clobber a file."""


__all__ = ["CitationExpert", "CITATION_SYSTEM_PROMPT"]

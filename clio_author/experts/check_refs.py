"""The check-refs expert: deterministic bibliography / citation sanity checks.

:class:`CheckRefsExpert` re-expresses the reference-linting step of the JS
writing toolkit wtf-p as a pure-Python, no-LLM expert:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concept* (lint a ``.bib`` and cross-check the ``\\cite{}`` keys in the
prose) is reproduced; no source code is copied. Because it never calls a model
this expert always produces a real, deterministic result -- it runs identically
under the offline :class:`EchoLLMClient`. It emits SUGGESTIONS ONLY and never
writes anything. Like the other experts it never raises: bad input produces an
error-flagged :class:`AgentOutput` (appended once to the session).
"""

from __future__ import annotations

from typing import Any

from clio_author.experts.bib_utils import (
    cross_check,
    extract_cite_keys,
    find_duplicates,
    find_malformed,
    parse_bibtex,
)
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.llm.client import EchoLLMClient, LLMClient

CHECK_REFS_SYSTEM_PROMPT = (
    "You are the reference-checking expert. You lint a BibTeX bibliography and "
    "cross-check it against the citation keys used in the manuscript prose, "
    "reporting malformed and duplicate entries, citations with no matching "
    "bibliography entry, and bibliography entries that are never cited. You emit "
    "SUGGESTIONS ONLY and never modify any file."
)


class CheckRefsExpert(BaseAgent):
    """Expert that lints a bibliography and cross-checks citation usage."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        """Build a check-refs expert.

        Args:
            llm: Accepted for a uniform expert constructor shape and defaulted to
                :class:`EchoLLMClient`; this expert performs no model calls, so
                the value is never invoked.
        """
        super().__init__(
            role="check_refs",
            system_prompt=CHECK_REFS_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _coerce_prose(payload: dict[str, Any]) -> str:
        """Resolve the prose to scan from ``markdown`` / ``text`` / ``sections``."""
        for key in ("markdown", "text"):
            raw = payload.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw
        sections = payload.get("sections")
        if isinstance(sections, (list, tuple)):
            parts: list[str] = []
            for entry in sections:
                if isinstance(entry, dict):
                    parts.append(str(entry.get("draft") or entry.get("text") or ""))
                elif isinstance(entry, str):
                    parts.append(entry)
            joined = "\n\n".join(part for part in parts if part)
            if joined.strip():
                return joined
        return ""

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Lint ``payload["bibtex"]`` and cross-check it against the prose. Never raises.

        Reads ``bibtex`` (a ``.bib`` string; the CLI also accepts a file) and the
        prose to scan (``markdown`` / ``text`` / ``sections`` / ``task.description``).
        Parses the bibliography, flags malformed and duplicate entries, extracts
        the ``\\cite{}`` keys, and reconciles the two key sets.

        ``structured`` carries ``{malformed, duplicates, missing_in_bib,
        uncited_entries, counts}``; ``content`` is a one-line summary; ``metadata``
        carries the same counts. With at least a bibliography *or* prose present
        this always produces a real result (no LLM). An empty payload (neither a
        bibliography nor prose) yields an error-flagged output.
        """
        try:
            payload = task.payload
            bibtex = str(payload.get("bibtex") or "")
            prose = self._coerce_prose(payload)
            if not bibtex.strip() and not prose.strip():
                return self._error(session, "no 'bibtex' and no prose ('markdown'/'text') provided")

            entries = parse_bibtex(bibtex)
            bib_keys = {e["key"] for e in entries if e.get("key")}
            malformed = find_malformed(entries)
            duplicates = find_duplicates(entries)

            cite_keys = extract_cite_keys(prose)
            crossed = cross_check(cite_keys, bib_keys)
            missing_in_bib = crossed["missing_in_bib"]
            uncited_entries = crossed["uncited_in_bib"]

            counts = {
                "num_entries": len(entries),
                "num_cited": len(cite_keys),
                "num_malformed": len(malformed),
                "num_duplicates": len(duplicates),
                "num_missing_in_bib": len(missing_in_bib),
                "num_uncited_entries": len(uncited_entries),
            }
            structured = {
                "malformed": malformed,
                "duplicates": duplicates,
                "missing_in_bib": missing_in_bib,
                "uncited_entries": uncited_entries,
                "counts": counts,
            }
            content = _render_summary(counts)
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        output = AgentOutput(
            agent=self.name,
            content=content,
            structured=structured,
            metadata=counts,
        )
        session.add(output)
        return output


def _render_summary(counts: dict[str, int]) -> str:
    """Render a one-line human summary of the reference check counts."""
    problems = (
        counts["num_malformed"]
        + counts["num_duplicates"]
        + counts["num_missing_in_bib"]
        + counts["num_uncited_entries"]
    )
    head = (
        f"Checked {counts['num_entries']} bib entr(ies) against "
        f"{counts['num_cited']} cited key(s): {problems} issue(s)."
    )
    if not problems:
        return head
    details = (
        f"{counts['num_malformed']} malformed, {counts['num_duplicates']} duplicate, "
        f"{counts['num_missing_in_bib']} cited-but-missing, "
        f"{counts['num_uncited_entries']} uncited."
    )
    return f"{head} {details}"


__all__ = ["CheckRefsExpert", "CHECK_REFS_SYSTEM_PROMPT"]

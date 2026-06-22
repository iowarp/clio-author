"""The audit expert: deterministic final-manuscript completeness checklist.

:class:`AuditExpert` re-expresses the final-pass "is the manuscript actually
done?" checklist of the JS writing toolkit wtf-p as a pure-Python, no-LLM
expert:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concept* (a deterministic completeness audit -- required sections
present, word budgets met, no unresolved placeholders, citations covered) is
reproduced; no source code is copied. Because it never calls a model this expert
always produces a real, deterministic result -- it runs identically under the
offline :class:`EchoLLMClient`. It emits a checklist + verdict and never writes.
Like the other experts it never raises: bad input produces an error-flagged
:class:`AgentOutput` (appended once to the session).
"""

from __future__ import annotations

import re
from typing import Any

from clio_author.experts.bib_utils import extract_cite_keys, parse_bibtex
from clio_author.experts.write_models import PaperOutline
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.retrieval.scholar import Candidate, VerifiedCitation, verified_coverage

AUDIT_SYSTEM_PROMPT = (
    "You are the manuscript-audit expert. You run a deterministic completeness "
    "checklist over a draft manuscript: are all required sections present, does "
    "each section meet its word budget, are there unresolved placeholders "
    "([TODO], [CITE:], empty \\cite{}), and are the cited references covered? You "
    "emit a checklist and a verdict only; you never modify the manuscript."
)

# Unresolved-placeholder markers an audit flags as not-done.
_TODO_RE = re.compile(r"\[TODO[^\]]*\]", re.IGNORECASE)
_CITE_MARKER_RE = re.compile(r"\[CITE:[^\]]*\]", re.IGNORECASE)
_EMPTY_CITE_RE = re.compile(r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{\s*\}")
# How far a section may fall under its budget before it is flagged (fraction).
_UNDER_BUDGET_TOLERANCE = 0.8


class AuditExpert(BaseAgent):
    """Expert that runs a deterministic manuscript completeness audit."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        """Build an audit expert.

        Args:
            llm: Accepted for a uniform expert constructor shape and defaulted to
                :class:`EchoLLMClient`; this expert performs no model calls, so
                the value is never invoked.
        """
        super().__init__(
            role="audit",
            system_prompt=AUDIT_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _coerce_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Resolve sections from ``sections`` or by splitting ``markdown``.

        ``sections`` is a list of ``{title, draft, word_budget?}``; otherwise a
        ``markdown`` string is split on ``^## `` headings into ``{title, draft}``
        pairs.
        """
        raw = payload.get("sections")
        if isinstance(raw, (list, tuple)):
            sections: list[dict[str, Any]] = []
            for entry in raw:
                if isinstance(entry, dict):
                    sections.append(
                        {
                            "title": str(
                                entry.get("title") or entry.get("section_path") or "Section"
                            ),
                            "draft": str(entry.get("draft") or entry.get("text") or ""),
                            "word_budget": entry.get("word_budget"),
                        }
                    )
            if sections:
                return sections

        markdown = payload.get("markdown")
        if markdown:
            return _split_markdown_sections(str(markdown))
        return []

    @staticmethod
    def _required_titles(payload: dict[str, Any]) -> list[str]:
        """Resolve the required section titles from an ``outline`` (if any)."""
        raw = payload.get("outline")
        if raw is None:
            return []
        outline = (
            raw
            if isinstance(raw, PaperOutline)
            else PaperOutline.from_loose_dict(raw)
            if isinstance(raw, dict)
            else None
        )
        if outline is None:
            return []
        return [s.title for s in outline.sections if s.title]

    @staticmethod
    def _candidates(payload: dict[str, Any]) -> list[Candidate]:
        """Coerce optional citation ``candidates`` for coverage; ``[]`` on absence."""
        raw = payload.get("candidates")
        if not isinstance(raw, (list, tuple)):
            return []
        candidates: list[Candidate] = []
        for item in raw:
            try:
                candidates.append(Candidate.model_validate(item))
            except Exception:  # noqa: BLE001 - skip a bad candidate, do not abort the audit
                continue
        return candidates

    @staticmethod
    def _verified(payload: dict[str, Any]) -> list[VerifiedCitation]:
        """Coerce optional pre-verified citations for coverage; ``[]`` on absence."""
        raw = payload.get("verified")
        if not isinstance(raw, (list, tuple)):
            return []
        verified: list[VerifiedCitation] = []
        for item in raw:
            try:
                verified.append(VerifiedCitation.model_validate(item))
            except Exception:  # noqa: BLE001 - skip a bad record, do not abort the audit
                continue
        return verified

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Audit the manuscript in ``task`` for completeness. Never raises.

        Reads ``sections`` (``[{title, draft, word_budget?}]``) or ``markdown``
        (+ optional ``outline`` for required-section presence), an optional
        ``bibtex``, and optional ``candidates`` / ``verified`` for citation
        coverage. Runs four deterministic checks:

        * required sections present (vs the outline),
        * per-section word-count vs budget (with the under-budget delta),
        * unresolved ``[TODO]`` / ``[CITE:]`` / empty ``\\cite{}`` placeholders,
        * citation coverage (``\\cite{}`` keys covered by the bibliography, and the
          90% verified-coverage target when candidates are supplied).

        ``structured`` is the full checklist, ``content`` a one-line verdict,
        ``metadata`` carries the counts and ``passed``. With at least sections or
        markdown present this always produces a real result (no LLM). An empty
        payload yields an error-flagged output.
        """
        try:
            payload = task.payload
            sections = self._coerce_sections(payload)
            if not sections:
                return self._error(session, "no 'sections' and no 'markdown' provided")

            full_text = "\n\n".join(str(s.get("draft") or "") for s in sections)

            missing_sections = self._check_required(sections, self._required_titles(payload))
            word_counts = self._check_word_budgets(sections)
            placeholders = self._check_placeholders(full_text, sections)
            coverage = self._check_coverage(payload, full_text)

            checklist = {
                "missing_sections": missing_sections,
                "word_counts": word_counts,
                "placeholders": placeholders,
                "coverage": coverage,
            }
            problems = (
                len(missing_sections)
                + sum(1 for w in word_counts if w["under_budget"])
                + placeholders["total"]
                + len(coverage["uncovered_cites"])
                + (0 if coverage["meets_90pct"] else 1)
            )
            passed = problems == 0
        except Exception as exc:  # noqa: BLE001 - never raise; flag error on output
            return self._error(session, str(exc))

        content = _render_verdict(passed, checklist)
        output = AgentOutput(
            agent=self.name,
            content=content,
            structured=checklist,
            metadata={
                "passed": passed,
                "num_sections": len(sections),
                "num_problems": problems,
            },
        )
        session.add(output)
        return output

    @staticmethod
    def _check_required(sections: list[dict[str, Any]], required: list[str]) -> list[str]:
        """Return required titles absent from the drafted sections (case-insensitive)."""
        present = {str(s.get("title") or "").strip().lower() for s in sections}
        return [title for title in required if title.strip().lower() not in present]

    @staticmethod
    def _check_word_budgets(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compute per-section word count vs budget and the under-budget flag."""
        results: list[dict[str, Any]] = []
        for section in sections:
            draft = str(section.get("draft") or "")
            words = len(draft.split())
            budget = section.get("word_budget")
            try:
                budget_int = int(budget) if budget is not None else None
            except (TypeError, ValueError):
                budget_int = None
            under = (
                budget_int is not None
                and budget_int > 0
                and words < budget_int * _UNDER_BUDGET_TOLERANCE
            )
            results.append(
                {
                    "title": str(section.get("title") or "Section"),
                    "words": words,
                    "word_budget": budget_int,
                    "delta": (words - budget_int) if budget_int is not None else None,
                    "under_budget": bool(under),
                }
            )
        return results

    @staticmethod
    def _check_placeholders(full_text: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
        """Count unresolved placeholders and the empty sections."""
        todos = _TODO_RE.findall(full_text)
        cite_markers = _CITE_MARKER_RE.findall(full_text)
        empty_cites = _EMPTY_CITE_RE.findall(full_text)
        empty_sections = [
            str(s.get("title") or "Section")
            for s in sections
            if not str(s.get("draft") or "").strip()
        ]
        return {
            "todo": len(todos),
            "cite_markers": len(cite_markers),
            "empty_cite": len(empty_cites),
            "empty_sections": empty_sections,
            "total": len(todos) + len(cite_markers) + len(empty_cites) + len(empty_sections),
        }

    def _check_coverage(self, payload: dict[str, Any], full_text: str) -> dict[str, Any]:
        """Check citation coverage: cited keys vs bibliography, and the 90% target."""
        cite_keys = extract_cite_keys(full_text)
        bibtex = str(payload.get("bibtex") or "")
        bib_keys = {e["key"] for e in parse_bibtex(bibtex) if e.get("key")}
        uncovered = sorted(cite_keys - bib_keys) if bib_keys else sorted(cite_keys)

        candidates = self._candidates(payload)
        verified = self._verified(payload)
        min_required, ratio, meets = verified_coverage(candidates, verified)
        return {
            "num_cited": len(cite_keys),
            "num_bib_entries": len(bib_keys),
            "uncovered_cites": uncovered,
            "min_required": min_required,
            "ratio": ratio,
            "meets_90pct": meets,
        }


def _split_markdown_sections(markdown: str) -> list[dict[str, Any]]:
    """Split ``markdown`` on ``^## `` headings into ``{title, draft}`` pairs.

    Mirrors :func:`clio_author.experts.coherence._split_markdown_sections`;
    content before the first ``## `` heading is ignored.
    """
    sections: list[dict[str, Any]] = []
    title: str | None = None
    body: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^##\s+(?!#)(.*)$", line)
        if match:
            if title is not None:
                sections.append(
                    {"title": title, "draft": "\n".join(body).strip(), "word_budget": None}
                )
            title = match.group(1).strip()
            body = []
        elif title is not None:
            body.append(line)
    if title is not None:
        sections.append({"title": title, "draft": "\n".join(body).strip(), "word_budget": None})
    return sections


def _render_verdict(passed: bool, checklist: dict[str, Any]) -> str:
    """Render a one-line human verdict from the audit checklist."""
    if passed:
        return "Audit PASSED: all sections present, budgets met, no unresolved placeholders."
    parts: list[str] = ["Audit FOUND ISSUES:"]
    if checklist["missing_sections"]:
        parts.append(f"{len(checklist['missing_sections'])} missing section(s)")
    under = sum(1 for w in checklist["word_counts"] if w["under_budget"])
    if under:
        parts.append(f"{under} under-budget section(s)")
    ph = checklist["placeholders"]
    if ph["total"]:
        parts.append(
            f"{ph['todo']} TODO, {ph['cite_markers']} [CITE:], {ph['empty_cite']} empty cite, "
            f"{len(ph['empty_sections'])} empty section(s)"
        )
    cov = checklist["coverage"]
    if cov["uncovered_cites"]:
        parts.append(f"{len(cov['uncovered_cites'])} uncovered citation(s)")
    if not cov["meets_90pct"]:
        parts.append("citation coverage below 90%")
    return " ".join(parts[:1]) + " " + ", ".join(parts[1:]) + "."


__all__ = ["AuditExpert", "AUDIT_SYSTEM_PROMPT"]

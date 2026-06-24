"""Grounding-integrity scoring — the cross-stage "are the claims real?" metric.

:func:`run_grounding` composes two existing checks into one **grounding-integrity
report** for a finished (or in-progress) manuscript:

* **citation integrity** (deterministic, via ``check_refs``): of the in-text
  ``\\cite{...}`` keys, what fraction resolve to a real bibliography entry?
* **claim integrity** (LLM, via ``verify_work``): of the claims the work was
  supposed to make, what fraction are actually *made and supported* by the prose?

The headline ``grounding_integrity`` is the mean of whichever components are
available, so it works deterministically/offline from just a bibliography + prose
(citation half) and gets richer when intended ``claims`` + a real model are
supplied (claim half). This is the number no single-slice tool can produce,
because none of them owns both the citations and the claims of the same paper.

Like :func:`~clio_author.experts.section_review.run_section_review` this is a
plain composing helper (not a :class:`BaseAgent`); each sub-expert already
degrades gracefully, and this never raises -- any failure becomes an
error-flagged :class:`AgentOutput`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from clio_author.experts.check_refs import CheckRefsExpert
from clio_author.experts.verify_work import VerifyWorkExpert
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.tools.files import FileToolError, SafeFiles


def run_grounding(
    task: Task,
    *,
    check_refs: CheckRefsExpert,
    verify_work: VerifyWorkExpert,
    session: SessionContext | None = None,
) -> AgentOutput:
    """Score how much of a manuscript is grounded in real sources. Never raises.

    Reads the prose from ``payload["markdown"]`` / ``["text"]`` / ``["sections"]``,
    an optional ``bibtex`` (drives citation integrity), and optional intended
    ``claims`` / ``section_plan`` (drive claim integrity). Returns an
    :class:`AgentOutput` whose ``structured`` is
    ``{grounding_integrity, citation_integrity, claim_integrity, citations, claims}``
    and whose ``metadata`` carries the headline numbers + ``wrote``. Persists
    ``grounding.json`` / ``grounding.md`` under ``out_dir`` when given.
    """
    try:
        return _run_grounding(task, check_refs=check_refs, verify_work=verify_work, session=session)
    except Exception as exc:  # noqa: BLE001 - never raise; flag error on the output
        out = AgentOutput(agent="grounding", content="", metadata={"error": str(exc)})
        if session is not None:
            session.add(out)
        return out


def _prose(payload: dict[str, Any]) -> str:
    """Resolve manuscript prose from markdown / text / a sections list."""
    for key in ("markdown", "text", "draft"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw
    sections = payload.get("sections")
    if isinstance(sections, (list, tuple)):
        parts: list[str] = []
        for s in sections:
            if isinstance(s, dict):
                body = str(s.get("draft") or s.get("text") or s.get("content") or "")
                if body.strip():
                    parts.append(body)
            elif isinstance(s, str) and s.strip():
                parts.append(s)
        return "\n\n".join(parts)
    return ""


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _run_grounding(
    task: Task,
    *,
    check_refs: CheckRefsExpert,
    verify_work: VerifyWorkExpert,
    session: SessionContext | None,
) -> AgentOutput:
    payload = task.payload
    prose = _prose(payload)
    bibtex = str(payload.get("bibtex") or "")
    has_claims = bool(payload.get("claims") or payload.get("section_plan"))

    if not bibtex.strip() and not has_claims:
        out = AgentOutput(
            agent="grounding",
            content="",
            metadata={
                "error": "provide 'bibtex' (citation integrity) and/or 'claims' (claim integrity)"
            },
        )
        if session is not None:
            session.add(out)
        return out

    components: list[float] = []
    citation_integrity: float | None = None
    claim_integrity: float | None = None
    citations: dict[str, Any] = {}
    claims: list[dict[str, Any]] = []

    # --- citation integrity (deterministic) --------------------------------- #
    if bibtex.strip() or prose.strip():
        cr = check_refs.run(
            Task(
                id=uuid4().hex, description="check_refs", payload={"bibtex": bibtex, "text": prose}
            ),
            SessionContext(id=uuid4().hex),
        )
        counts = (cr.structured or {}).get("counts", {}) if cr.structured else {}
        num_cited = int(counts.get("num_cited", 0))
        missing = int(counts.get("num_missing_in_bib", 0))
        citations = {
            "num_cited": num_cited,
            "num_missing_in_bib": missing,
            "missing_in_bib": (cr.structured or {}).get("missing_in_bib", []),
        }
        if num_cited:
            citation_integrity = (num_cited - missing) / num_cited
            components.append(citation_integrity)

    # --- claim integrity (LLM, optional) ------------------------------------ #
    if has_claims:
        vw = verify_work.run(
            Task(
                id=uuid4().hex,
                description="verify_work",
                payload={
                    "claims": payload.get("claims"),
                    "section_plan": payload.get("section_plan"),
                    "text": prose,
                },
            ),
            SessionContext(id=uuid4().hex),
        )
        claims = (vw.structured or {}).get("claims", []) if vw.structured else []
        if claims:
            supported = sum(1 for c in claims if isinstance(c, dict) and c.get("supported"))
            claim_integrity = supported / len(claims)
            components.append(claim_integrity)

    grounding_integrity = _mean(components)

    summary = _summary(grounding_integrity, citation_integrity, claim_integrity)
    structured = {
        "grounding_integrity": grounding_integrity,
        "citation_integrity": citation_integrity,
        "claim_integrity": claim_integrity,
        "citations": citations,
        "claims": claims,
    }
    wrote = _maybe_write(payload, structured, summary)
    out = AgentOutput(
        agent="grounding",
        content=summary,
        structured=structured,
        metadata={
            "grounding_integrity": grounding_integrity,
            "citation_integrity": citation_integrity,
            "claim_integrity": claim_integrity,
            "wrote": wrote,
        },
    )
    if session is not None:
        session.add(out)
    return out


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{round(x * 100)}%"


def _summary(overall: float | None, cite: float | None, claim: float | None) -> str:
    return (
        f"Grounding integrity: {_pct(overall)} "
        f"(citations {_pct(cite)}, claims {_pct(claim)}). "
        "Fraction of the manuscript traceable to a real source."
    )


def render_grounding_markdown(structured: dict[str, Any], summary: str) -> str:
    """Render the grounding report as a short Markdown document."""
    lines = ["# Grounding-integrity report", "", summary, ""]
    cites = structured.get("citations") or {}
    if cites:
        lines.append(
            f"- **Citations:** {cites.get('num_cited', 0)} cited, "
            f"{cites.get('num_missing_in_bib', 0)} not in the bibliography."
        )
        for key in cites.get("missing_in_bib", []) or []:
            lines.append(f"  - missing: `{key}`")
    claims = structured.get("claims") or []
    if claims:
        made = sum(1 for c in claims if isinstance(c, dict) and c.get("made"))
        sup = sum(1 for c in claims if isinstance(c, dict) and c.get("supported"))
        lines.append(f"- **Claims:** {len(claims)} intended, {made} made, {sup} supported.")
    return "\n".join(lines) + "\n"


def _maybe_write(payload: dict[str, Any], structured: dict[str, Any], summary: str) -> list[str]:
    out_dir = payload.get("out_dir")
    if not out_dir:
        return []
    files = SafeFiles(Path(str(out_dir)))
    try:
        files.root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []
    wrote: list[str] = []
    for name, content in (
        ("grounding.json", json.dumps(structured, indent=2)),
        ("grounding.md", render_grounding_markdown(structured, summary)),
    ):
        try:
            wrote.append(str(files.write_new(name, content)))
        except FileToolError:
            continue
    return wrote


__all__ = ["run_grounding", "render_grounding_markdown"]

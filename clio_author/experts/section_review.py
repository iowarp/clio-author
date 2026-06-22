"""Layered single-section review orchestration.

:func:`run_section_review` composes three existing experts into a layered review
of ONE section, re-expressing the multi-pass review loop of the JS writing
toolkit wtf-p:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concept* (run cheap structural checks first, then deeper semantic
checks) is reproduced; no source code is copied. The three layers are:
L1 deterministic reference/citation checking (``check_refs``), L2 single-section
coherence (``coherence``), and L3 persona-conditioned peer review (``reviewer``).
The aggregate severity is derived deterministically from the three layer
results -- it adds no new prompt.

This is a plain helper (not a :class:`~clio_author.harness.base.BaseAgent`),
mirroring :func:`~clio_author.experts.compose.run_compose`: it composes existing
experts, each of which already degrades gracefully. It never raises -- any
failure becomes an error-flagged :class:`AgentOutput`.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from clio_author.experts.check_refs import CheckRefsExpert
from clio_author.experts.coherence import CoherenceExpert
from clio_author.experts.reviewer import ReviewerExpert
from clio_author.experts.review_models import PersonaSpec
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task

# Below this reviewer overall rating (1-10) the section needs major work.
_OVERALL_MAJOR_THRESHOLD = 5


def run_section_review(
    task: Task,
    *,
    check_refs: CheckRefsExpert,
    coherence: CoherenceExpert,
    reviewer: ReviewerExpert,
    session: SessionContext | None = None,
) -> AgentOutput:
    """Run a layered (refs -> coherence -> review) check on ONE section.

    Reads the section text from ``payload["section"]`` / ``["text"]`` /
    ``["markdown"]`` (or ``task.description``), an optional ``bibtex`` (for L1),
    and an optional reviewer ``persona`` (for L3). Runs each layer in its own
    fresh session, then aggregates:

    ``structured`` is ``{layer1, layer2, layer3, severity_summary}`` where each
    layer is the sub-expert's ``structured`` (or its error/parse metadata) and
    ``severity_summary`` is a deterministically derived list of
    ``{layer, severity, detail}`` findings. ``content`` is a one-line verdict.

    Severity rules (deterministic): an L1 citation cited-but-missing-in-bib is
    ``critical``; an L2 ``contradiction`` coherence issue is ``major``; an L3
    reviewer overall rating below 5 is ``major``. Never raises.
    """
    try:
        return _run_section_review(
            task,
            check_refs=check_refs,
            coherence=coherence,
            reviewer=reviewer,
            session=session,
        )
    except Exception as exc:  # noqa: BLE001 - never raise; flag error on the output
        out = AgentOutput(agent="section_review", content="", metadata={"error": str(exc)})
        if session is not None:
            session.add(out)
        return out


def _section_text(payload: dict[str, Any]) -> str:
    """Resolve the single section's text from the payload."""
    for key in ("section", "text", "markdown", "draft"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw
    return ""


def _run_section_review(
    task: Task,
    *,
    check_refs: CheckRefsExpert,
    coherence: CoherenceExpert,
    reviewer: ReviewerExpert,
    session: SessionContext | None,
) -> AgentOutput:
    payload = task.payload
    text = _section_text(payload)
    if not text.strip():
        out = AgentOutput(
            agent="section_review",
            content="",
            metadata={"error": "no 'section'/'text'/'markdown' provided"},
        )
        if session is not None:
            session.add(out)
        return out

    bibtex = str(payload.get("bibtex") or "")
    persona = payload.get("persona")

    # --- L1: deterministic reference / citation checking -------------------- #
    l1_out = check_refs.run(
        Task(id=uuid4().hex, description="check_refs", payload={"bibtex": bibtex, "text": text}),
        SessionContext(id=uuid4().hex),
    )
    l1 = _layer_payload(l1_out)

    # --- L2: single-section coherence --------------------------------------- #
    l2_out = coherence.run(
        Task(id=uuid4().hex, description="coherence", payload={"text": text}),
        SessionContext(id=uuid4().hex),
    )
    l2 = _layer_payload(l2_out)

    # --- L3: persona-conditioned peer review -------------------------------- #
    review_reviewer = reviewer
    if persona is not None:
        try:
            spec = (
                persona if isinstance(persona, PersonaSpec) else PersonaSpec.model_validate(persona)
            )
            review_reviewer = ReviewerExpert(reviewer.llm, persona=spec)
        except Exception:  # noqa: BLE001 - a bad persona just falls back to the default reviewer
            review_reviewer = reviewer
    l3_out = review_reviewer.run(
        Task(id=uuid4().hex, description="review", payload={"paper": text}),
        SessionContext(id=uuid4().hex),
    )
    l3 = _layer_payload(l3_out)

    severity_summary = _derive_severity(l1_out, l2_out, l3_out)

    structured = {
        "layer1": l1,
        "layer2": l2,
        "layer3": l3,
        "severity_summary": severity_summary,
    }
    content = _verdict(severity_summary)
    out = AgentOutput(
        agent="section_review",
        content=content,
        structured=structured,
        metadata={
            "num_findings": len(severity_summary),
            "max_severity": _max_severity(severity_summary),
        },
    )
    if session is not None:
        session.add(out)
    return out


def _layer_payload(out: AgentOutput) -> dict[str, Any]:
    """Render one sub-expert output as a layer payload (structured + flags)."""
    layer: dict[str, Any] = {"agent": out.agent, "content": out.content}
    if out.structured is not None:
        layer["structured"] = out.structured
    for flag in ("error", "parse_error"):
        if flag in out.metadata:
            layer[flag] = out.metadata[flag]
    return layer


def _derive_severity(l1: AgentOutput, l2: AgentOutput, l3: AgentOutput) -> list[dict[str, Any]]:
    """Deterministically derive severity findings from the three layer outputs."""
    findings: list[dict[str, Any]] = []

    # L1: a cited key with no matching bibliography entry is critical.
    if l1.structured is not None:
        missing = l1.structured.get("missing_in_bib") or []
        if missing:
            findings.append(
                {
                    "layer": "check_refs",
                    "severity": "critical",
                    "detail": f"{len(missing)} cited key(s) missing from the bibliography: "
                    + ", ".join(str(k) for k in missing),
                }
            )

    # L2: a contradiction across the section is major.
    if l2.structured is not None:
        issues = l2.structured.get("issues") or []
        contradictions = [
            issue
            for issue in issues
            if isinstance(issue, dict) and str(issue.get("kind")).lower() == "contradiction"
        ]
        if contradictions:
            findings.append(
                {
                    "layer": "coherence",
                    "severity": "major",
                    "detail": f"{len(contradictions)} contradiction(s) flagged in the section.",
                }
            )

    # L3: a low overall reviewer rating is major.
    if l3.structured is not None:
        overall = l3.structured.get("overall")
        if isinstance(overall, int) and overall < _OVERALL_MAJOR_THRESHOLD:
            findings.append(
                {
                    "layer": "reviewer",
                    "severity": "major",
                    "detail": f"reviewer overall rating {overall}/10 is below the "
                    f"{_OVERALL_MAJOR_THRESHOLD} bar.",
                }
            )

    return findings


_SEVERITY_ORDER = {"critical": 3, "major": 2, "minor": 1}


def _max_severity(findings: list[dict[str, Any]]) -> str | None:
    """Return the highest severity among ``findings`` (``None`` when empty)."""
    if not findings:
        return None
    return max(findings, key=lambda f: _SEVERITY_ORDER.get(str(f.get("severity")), 0))["severity"]


def _verdict(findings: list[dict[str, Any]]) -> str:
    """Render a one-line verdict from the derived severity findings."""
    if not findings:
        return "Section review: no critical or major issues found across the three layers."
    top = _max_severity(findings)
    return f"Section review: {len(findings)} finding(s), highest severity {top}. " + "; ".join(
        f"[{f['severity']}] {f['detail']}" for f in findings
    )


__all__ = ["run_section_review"]

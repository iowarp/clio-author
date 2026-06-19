"""Top-level "write a whole paper" composition (serial subset).

:func:`run_compose` orchestrates a multi-section manuscript from an *idea* and an
optional *experimental log*: generate (or accept) a :class:`PaperOutline`,
optionally verify citation candidates, write each section in isolation (with an
optional per-section writer/reviewer refine loop), and assemble the sections into
a single Markdown manuscript. When an ``out_dir`` is reachable the full
manuscript and per-section files are persisted.

The serial outline -> cite -> write -> assemble pipeline is referenced from
PaperOrchestra (Apache-2.0); no source code is copied. LaTeX export and a
parallel plotting branch are deliberately out of scope (follow-ups).

This is a plain helper (not a :class:`~clio_author.harness.base.BaseAgent`): it
composes the existing writer / reviewer / citation experts. Like those experts it
never raises -- any failure becomes an error-flagged :class:`AgentOutput`, and the
whole output is only error-flagged when there is nothing to produce. With the
default :class:`~clio_author.llm.client.EchoLLMClient` the orchestration and
assembly are fully deterministic, so the default suite stays hermetic.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from clio_author.experts.citation import CitationExpert
from clio_author.experts.reviewer import ReviewerExpert, _extract_json_object
from clio_author.experts.write_loop import run_write_review_loop
from clio_author.experts.write_models import PaperOutline, SectionOutline, SectionPlan
from clio_author.experts.writer import WriterExpert
from clio_author.export.latex import to_latex_document
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.ingest.blocks import MemoryBlocks
from clio_author.llm.client import LLMClient
from clio_author.tools.files import FileToolError, SafeFiles

COMPOSE_SYSTEM_PROMPT = (
    "You are the lead author. You turn a research idea and an experimental log "
    "into a structured paper outline: a title, a one-paragraph vision, and an "
    "ordered list of sections, each with a goal and any citation hints. You do "
    "not write the prose here -- only the plan. Respond with the outline as a "
    "single JSON object and nothing else."
)

_OUTLINE_INSTRUCTIONS = (
    "Produce a paper outline as a fenced JSON block:\n"
    "```json\n"
    '{"title": "<paper title>", "vision": "<one-paragraph thesis>", '
    '"sections": [{"title": "<section title>", "goal": "<what this section '
    'establishes>", "citation_hints": ["<\\\\cite{key} placeholders, optional>"]}]}\n'
    "```\n"
    "Keep the format precise; the JSON is parsed automatically."
)


def run_compose(
    task: Task,
    *,
    writer: WriterExpert,
    reviewer: ReviewerExpert,
    citation: CitationExpert,
    llm: LLMClient,
    files: SafeFiles | None = None,
    session: SessionContext | None = None,
) -> AgentOutput:
    """Compose a whole multi-section manuscript from ``task.payload``.

    Reads ``idea`` (required unless an ``outline`` is given), ``experimental_log``,
    ``outline`` (a :class:`PaperOutline`/loose dict), ``candidates`` (citation
    candidates), ``blocks`` (:class:`MemoryBlocks` for grounding), ``review``
    (bool), ``max_rounds`` (int, default 3), and ``out_dir``.

    Steps: build/parse the outline; best-effort verify citations; write each
    section in a fresh :class:`SessionContext` (optionally through a
    writer/reviewer refine loop); assemble ``# title`` + ``## section`` blocks
    (and a ``## References`` block when a bibliography was produced); persist to
    ``out_dir`` when a :class:`SafeFiles` is reachable.

    Returns one :class:`AgentOutput` (``agent="compose"``). Only error-flags the
    whole output when nothing can be produced (no idea and no outline, an
    unparseable generated outline, or every section failing). Never raises.
    """
    try:
        return _run_compose(
            task,
            writer=writer,
            reviewer=reviewer,
            citation=citation,
            llm=llm,
            files=files,
            session=session,
        )
    except Exception as exc:  # noqa: BLE001 - never raise; flag error on the output
        out = AgentOutput(agent="compose", content="", metadata={"error": str(exc)})
        if session is not None:
            session.add(out)
        return out


def _run_compose(
    task: Task,
    *,
    writer: WriterExpert,
    reviewer: ReviewerExpert,
    citation: CitationExpert,
    llm: LLMClient,
    files: SafeFiles | None,
    session: SessionContext | None,
) -> AgentOutput:
    payload = task.payload
    idea = str(payload.get("idea") or "").strip()
    experimental_log = str(payload.get("experimental_log") or "").strip()
    out_dir = payload.get("out_dir")

    # A SafeFiles rooted at out_dir is how persistence is reached. Prefer an
    # explicitly supplied files instance; otherwise derive one from out_dir
    # (consistent with how the ingestor / citation handle out_dir).
    if files is None and out_dir:
        files = SafeFiles(out_dir)

    metadata: dict[str, Any] = {}

    # --- Outline ------------------------------------------------------------ #
    outline = _build_outline(payload, idea, experimental_log, llm)
    if outline is None:
        if not idea and payload.get("outline") is None:
            return _error(session, "no 'idea' and no 'outline' provided")
        return _error(session, "could not parse generated outline")
    if not outline.sections:
        return _error(session, "outline has no sections")

    # --- Citations (best-effort, optional) ---------------------------------- #
    citations: dict[str, Any] | None = None
    suggested_bibtex = ""
    if payload.get("candidates") is not None:
        cite_payload: dict[str, Any] = {"candidates": payload["candidates"]}
        if out_dir:
            cite_payload["out_dir"] = out_dir
        cite_task = Task(id=uuid4().hex, description="cite", payload=cite_payload)
        cite_out = citation.run(cite_task, SessionContext(id=uuid4().hex))
        if "error" in cite_out.metadata or cite_out.structured is None:
            metadata["citation_error"] = cite_out.metadata.get(
                "error", "citation produced no structured output"
            )
        else:
            suggested_bibtex = str(cite_out.structured.get("suggested_bibtex") or "")
            citations = {
                "suggested_bibtex": suggested_bibtex,
                "citation_map": cite_out.structured.get("citation_map") or {},
            }

    # --- Write sections ----------------------------------------------------- #
    blocks = _coerce_blocks(payload.get("blocks"))
    review = bool(payload.get("review", False))
    max_rounds = int(payload.get("max_rounds", 3))
    base_source = "\n\n".join(part for part in (idea, experimental_log) if part)

    # --- Optional per-section planning (off by default) --------------------- #
    plans = _maybe_plan(payload, outline, llm) if bool(payload.get("plan", False)) else {}
    if plans:
        metadata["planned"] = True

    sections: list[dict[str, Any]] = []
    section_errors: list[dict[str, str]] = []
    for section in outline.sections:
        draft, err = _write_section(
            section,
            outline=outline,
            blocks=blocks,
            base_source=base_source,
            writer=writer,
            reviewer=reviewer,
            review=review,
            max_rounds=max_rounds,
            section_plan=plans.get(_section_key(section)),
        )
        section_path = section.section_path or section.title
        if err is not None:
            section_errors.append({"section": section_path, "error": err})
            draft = f"_(section draft unavailable: {err})_"
        sections.append({"title": section.title, "section_path": section_path, "draft": draft})

    if section_errors and len(section_errors) == len(outline.sections):
        return _error(session, "every section failed to draft")

    # --- Assemble ----------------------------------------------------------- #
    manuscript = _assemble(outline, sections, suggested_bibtex)

    # --- Persist (if reachable) --------------------------------------------- #
    wrote: list[str] = []
    latex_written = False
    if files is not None:
        wrote = _persist(files, manuscript, sections)
        if bool(payload.get("latex", False)):
            wrote.extend(_persist_latex(files, outline, sections, suggested_bibtex))
            latex_written = True

    metadata.update(
        {
            "num_sections": len(sections),
            "reviewed": review,
            "wrote": wrote,
            "section_errors": section_errors,
            "latex": latex_written,
        }
    )
    out = AgentOutput(
        agent="compose",
        content=manuscript,
        structured={
            "outline": outline.model_dump(),
            "sections": sections,
            "citations": citations,
        },
        metadata=metadata,
    )
    if session is not None:
        session.add(out)
    return out


def _build_outline(
    payload: dict[str, Any],
    idea: str,
    experimental_log: str,
    llm: LLMClient,
) -> PaperOutline | None:
    """Coerce a provided outline or generate one via the LLM. ``None`` on failure."""
    raw = payload.get("outline")
    if raw is not None:
        if isinstance(raw, PaperOutline):
            return raw
        if isinstance(raw, dict):
            return PaperOutline.from_loose_dict(raw)
        return None

    if not idea:
        return None

    parts = [_OUTLINE_INSTRUCTIONS, f"Research idea:\n{idea}"]
    if experimental_log:
        parts.append(f"Experimental log:\n{experimental_log}")
    parts.append("Produce the outline JSON now.")
    messages = [
        Message(role="system", content=COMPOSE_SYSTEM_PROMPT),
        Message(role="user", content="\n\n".join(parts)),
    ]
    raw_text = llm.complete(messages)
    parsed = _extract_json_object(raw_text)
    if parsed is None:
        return None
    return PaperOutline.from_loose_dict(parsed)


def _section_key(section: SectionOutline) -> str:
    """Stable key identifying a section across the outline and its plans."""
    return section.section_path or section.title


def _maybe_plan(
    payload: dict[str, Any],
    outline: PaperOutline,
    llm: LLMClient,
) -> dict[str, SectionPlan]:
    """Run the planner once over the resolved outline; index plans by section key.

    Best-effort / never-raise: the planner already flags its own failures, so a
    planning failure yields an empty index and compose falls back to the bare
    outline. The :class:`PlannerExpert` import is local to avoid a circular import
    (the planner reuses :func:`_build_outline` from this module).
    """
    from clio_author.experts.planner import PlannerExpert

    plan_payload: dict[str, Any] = {"outline": outline}
    for key in ("blocks", "source", "candidates", "citation_hints", "idea", "experimental_log"):
        if payload.get(key) is not None:
            plan_payload[key] = payload[key]
    plan_task = Task(id=uuid4().hex, description="plan", payload=plan_payload)
    out = PlannerExpert(llm).run(plan_task, SessionContext(id=uuid4().hex))
    if "error" in out.metadata or out.structured is None:
        return {}

    indexed: dict[str, SectionPlan] = {}
    for raw in out.structured.get("plans", []):
        try:
            plan = SectionPlan.from_loose_dict(raw) if isinstance(raw, dict) else None
        except Exception:  # noqa: BLE001 - planning is best-effort
            plan = None
        if plan is not None:
            indexed[_section_key(plan.outline)] = plan
    return indexed


def _coerce_blocks(raw: Any) -> MemoryBlocks | None:
    """Coerce ``raw`` into :class:`MemoryBlocks` (``None`` when absent/invalid)."""
    if raw is None:
        return None
    if isinstance(raw, MemoryBlocks):
        return raw
    if isinstance(raw, dict):
        return MemoryBlocks.model_validate(raw)
    return None


def _write_section(
    section: SectionOutline,
    *,
    outline: PaperOutline,
    blocks: MemoryBlocks | None,
    base_source: str,
    writer: WriterExpert,
    reviewer: ReviewerExpert,
    review: bool,
    max_rounds: int,
    section_plan: SectionPlan | None = None,
) -> tuple[str, str | None]:
    """Draft one section in a FRESH session; return ``(draft, error_or_None)``.

    A fresh :class:`SessionContext` per section is critical: it stops the
    writer's ``session.data["draft"]`` / ``["critic_feedback"]`` from leaking
    between sections (section isolation). When ``section_plan`` is given it is
    passed through as the writer's ``section_plan`` so the draft follows the plan.
    """
    section_payload: dict[str, Any] = {"outline": section, "vision": outline.vision}
    if section_plan is not None:
        section_payload["section_plan"] = section_plan
    if blocks is not None:
        section_payload["blocks"] = blocks
    else:
        section_payload["source"] = base_source
    section_task = Task(
        id=uuid4().hex,
        description=section.title,
        payload=section_payload,
    )
    fresh = SessionContext(id=uuid4().hex)
    if review:
        outputs = run_write_review_loop(
            section_task,
            writer=writer,
            reviewer=reviewer,
            max_rounds=max_rounds,
            session=fresh,
        )
        result = outputs[-1]
    else:
        result = writer.run(section_task, fresh)

    if "error" in result.metadata:
        return "", str(result.metadata["error"])
    draft = result.content or (str(result.structured.get("draft", "")) if result.structured else "")
    return draft, None


def _section_body(title: str, draft: str) -> str:
    """One ``## title`` block, dropping a duplicate leading heading from ``draft``.

    The writer often emits its own ``## Title`` (or ``## 1. Title``) heading; we
    supply the canonical one, so strip a matching leading heading to avoid a
    doubled header in the assembled manuscript.
    """
    body = draft.lstrip("\n")
    lines = body.split("\n", 1)
    first = lines[0].strip()
    if first.startswith("#"):
        heading_text = first.lstrip("#").strip()
        # Normalise "1. Introduction"/"Introduction" -> "introduction" for compare.
        norm = re.sub(r"^\d+(\.\d+)*\.?\s*", "", heading_text).strip().lower()
        if norm == title.strip().lower():
            body = lines[1].lstrip("\n") if len(lines) > 1 else ""
    return f"## {title}\n\n{body}"


def _assemble(
    outline: PaperOutline,
    sections: list[dict[str, Any]],
    suggested_bibtex: str,
) -> str:
    """Deterministically assemble the manuscript Markdown."""
    parts = [f"# {outline.title}".rstrip()]
    for section in sections:
        parts.append(_section_body(section["title"], section["draft"]))
    if suggested_bibtex:
        parts.append(f"## References\n\n{suggested_bibtex}")
    return "\n\n".join(parts) + "\n"


def _persist(
    files: SafeFiles,
    manuscript: str,
    sections: list[dict[str, Any]],
) -> list[str]:
    """Write ``paper.md`` and ``sections/NN-slug.md`` via ``write_new``.

    Best-effort: a refusal (e.g. an existing file) is skipped rather than
    aborting the compose, so a re-run does not lose the in-memory manuscript.
    """
    wrote: list[str] = []
    try:
        wrote.append(str(files.write_new("paper.md", manuscript)))
    except FileToolError:
        pass
    # write_new does not create parent dirs; mint the sections/ folder once.
    (files.root / "sections").mkdir(parents=True, exist_ok=True)
    for index, section in enumerate(sections, start=1):
        slug = _slug(section.get("section_path") or section.get("title") or "section")
        rel = f"sections/{index:02d}-{slug}.md"
        body = _section_body(section["title"], section["draft"]) + "\n"
        try:
            wrote.append(str(files.write_new(rel, body)))
        except FileToolError:
            continue
    return wrote


def _persist_latex(
    files: SafeFiles,
    outline: PaperOutline,
    sections: list[dict[str, Any]],
    suggested_bibtex: str,
) -> list[str]:
    """Build a LaTeX document and write ``paper.tex`` (+ ``references.bib``).

    Best-effort/never-raise, mirroring :func:`_persist`: a refused or failed
    write is skipped rather than aborting the compose.
    """
    wrote: list[str] = []
    bib = suggested_bibtex or None
    try:
        latex = to_latex_document(
            outline.title,
            [(s["title"], s["draft"]) for s in sections],
            bibtex=bib,
        )
    except Exception:  # noqa: BLE001 - LaTeX export is best-effort
        return wrote
    try:
        wrote.append(str(files.write_new("paper.tex", latex)))
    except FileToolError:
        pass
    if bib:
        try:
            wrote.append(str(files.write_new("references.bib", bib.rstrip("\n") + "\n")))
        except FileToolError:
            pass
    return wrote


def _slug(text: str) -> str:
    """Slugify ``text`` into a filename-safe stem."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-").lower()
    return slug[:48] or "section"


def _error(session: SessionContext | None, message: str) -> AgentOutput:
    """Build (and record) an error-flagged compose output."""
    out = AgentOutput(agent="compose", content="", metadata={"error": message})
    if session is not None:
        session.add(out)
    return out


__all__ = ["run_compose", "COMPOSE_SYSTEM_PROMPT"]

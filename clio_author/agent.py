"""The main agent and entry surface for clio-author.

:class:`ClioAuthorAgent` is the object the CLIO agent (and tests) invoke. It is
the **main agent**: it owns the expert set and routes a :class:`Task` to the
right expert based on ``task.payload["action"]``. The expert set shares one
:class:`~clio_author.llm.client.LLMClient` (default
:class:`~clio_author.llm.client.EchoLLMClient`, so the harness runs offline),
plus an optional :class:`~clio_author.tools.files.SafeFiles` and scholar client.

Routing is hermetic and never raises across the public surface: experts already
flag their own failures on the returned :class:`AgentOutput`, and the router
wraps dispatch in a guard so an unexpected error becomes an error-flagged output
rather than a propagated exception.

Back-compat: an unknown / missing ``action`` (and a bare ``str`` task) falls
through to the :class:`~clio_author.experts.echo.EchoExpert` via the M0
:class:`Engine` / :class:`Sequential` wiring, so ``invoke("hello world")`` still
returns the echo output.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from clio_author.experts.audit import AuditExpert
from clio_author.experts.check_refs import CheckRefsExpert
from clio_author.experts.citation import CitationExpert
from clio_author.experts.coherence import CoherenceExpert
from clio_author.experts.compose import run_compose
from clio_author.experts.echo import EchoExpert
from clio_author.experts.editor import EditorExpert
from clio_author.experts.figure_agent import FigureAgentExpert, run_figure_refine
from clio_author.experts.ingestor import IngestorExpert
from clio_author.experts.kg import KGExpert
from clio_author.experts.meta_reviewer import MetaReviewerExpert
from clio_author.experts.orchestrate import run_orchestrate
from clio_author.experts.paper_qa import PaperQAExpert
from clio_author.experts.planner import PlannerExpert
from clio_author.experts.polish import PolishExpert
from clio_author.experts.rebuttal import RebuttalExpert
from clio_author.experts.research import ResearchExpert
from clio_author.experts.reviewer import ReviewerExpert
from clio_author.experts.section_review import run_section_review
from clio_author.experts.verify_work import VerifyWorkExpert
from clio_author.experts.write_loop import run_write_review_loop
from clio_author.experts.writer import WriterExpert
from clio_author.export.latex import run_export
from clio_author.harness.engine import Engine
from clio_author.harness.patterns import Sequential
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.llm.vision import VisionClient
from clio_author.retrieval.scholar import ScholarClient
from clio_author.tools.files import SafeFiles


class ClioAuthorAgent:
    """Main orchestrator agent and primary entry point.

    Builds the full expert set sharing one ``llm`` (and optional ``files`` /
    ``scholar_client`` where each expert accepts them) and routes a
    :class:`Task` to the right expert by ``payload["action"]``.
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        files: SafeFiles | None = None,
        scholar_client: ScholarClient | None = None,
        vision: VisionClient | None = None,
    ) -> None:
        """Construct the expert set.

        Args:
            llm: Shared completion client; defaults to :class:`EchoLLMClient`
                so the agent runs offline.
            files: Optional :class:`SafeFiles` shared by the experts that write
                (ingestor / writer / editor / figure).
            scholar_client: Optional scholar client given to the citation expert
                (the network seam). Citation runs degrade gracefully when absent.
            vision: Optional :class:`VisionClient` (e.g. Gemini) given to the
                figure agent. ``None`` (default) keeps the hermetic text/code path.
        """
        self.llm: LLMClient = llm if llm is not None else EchoLLMClient()
        self.files = files
        self.scholar_client = scholar_client
        self.vision = vision

        self.echo_expert = EchoExpert(self.llm)
        self.ingestor = IngestorExpert(self.llm, out_dir=files.root if files else None)
        self.paper_qa = PaperQAExpert(self.llm)
        self.reviewer = ReviewerExpert(self.llm, scholar_client=scholar_client, vision=vision)
        self.meta_reviewer = MetaReviewerExpert(self.llm)
        self.rebuttal = RebuttalExpert(self.llm, files=files)
        self.citation = CitationExpert(self.llm, client=scholar_client)
        self.writer = WriterExpert(self.llm, files=files)
        self.editor = EditorExpert(self.llm, files=files)
        self.polish = PolishExpert(self.llm, files=files)
        self.coherence = CoherenceExpert(self.llm)
        self.kg_expert = KGExpert(self.llm, files=files)
        self.planner = PlannerExpert(self.llm, files=files)
        self.figure = FigureAgentExpert(self.llm, files=files, vision=vision)
        self.research = ResearchExpert(self.llm, scholar_client=scholar_client)
        self.verify_work = VerifyWorkExpert(self.llm)
        self.check_refs = CheckRefsExpert(self.llm)
        self.audit = AuditExpert(self.llm)

        # M0 echo wiring is preserved for the unknown/None-action fallthrough.
        self.engine = Engine()
        self.pattern = Sequential()

    def invoke(self, task: str | Task) -> AgentOutput:
        """Route ``task`` to the right expert and return its output.

        A bare ``str`` is wrapped in a :class:`Task` (M0 behavior). Routing is on
        ``task.payload["action"]``; an unknown / missing action falls through to
        the echo expert. Never raises: dispatch is guarded so any unexpected
        error becomes an error-flagged :class:`AgentOutput`.
        """
        task_obj = (
            task if isinstance(task, Task) else Task(id=uuid4().hex, description=task, payload={})
        )
        action = task_obj.payload.get("action")
        try:
            out = self._route(action, task_obj)
            # format="prose": return a human-readable text answer (drop the JSON).
            # Experts that write prose themselves (e.g. review) already set
            # structured=None, so this only re-renders the data-shaped actions.
            if (
                str(task_obj.payload.get("format", "")).lower() == "prose"
                and out.structured is not None
            ):
                return AgentOutput(
                    agent=out.agent,
                    content=_prose_view(action, out),
                    structured=None,
                    metadata={**out.metadata, "format": "prose"},
                )
            return out
        except Exception as exc:  # noqa: BLE001 - never raise across the public surface
            return AgentOutput(
                agent="clio-author",
                content="",
                metadata={"error": str(exc), "action": action},
            )

    def _route(self, action: Any, task: Task) -> AgentOutput:
        """Dispatch ``task`` for ``action`` against a fresh session."""
        session = SessionContext(id=uuid4().hex)

        if action == "ingest":
            return self.ingestor.run(task, session)
        if action == "ask":
            return self.paper_qa.run(task, session)
        if action == "review":
            return self.reviewer.run(task, session)
        if action == "meta_review":
            return self.meta_reviewer.run(task, session)
        if action == "rebuttal":
            return self.rebuttal.run(task, session)
        if action == "cite":
            return self.citation.run(task, session)
        if action == "write":
            return self.writer.run(task, session)
        if action == "edit":
            return self.editor.run(task, session)
        if action == "polish":
            return self.polish.run(task, session)
        if action == "coherence":
            return self.coherence.run(task, session)
        if action == "kg":
            return self.kg_expert.run(task, session)
        if action == "plan":
            return self.planner.run(task, session)
        if action == "research":
            return self.research.run(task, session)
        if action == "verify_work":
            return self.verify_work.run(task, session)
        if action == "check_refs":
            return self.check_refs.run(task, session)
        if action == "audit":
            return self.audit.run(task, session)
        if action == "section_review":
            return run_section_review(
                task,
                check_refs=self.check_refs,
                coherence=self.coherence,
                reviewer=self.reviewer,
                session=session,
            )
        if action == "describe_figures":
            return self.figure.run(
                task.model_copy(update={"payload": {**task.payload, "mode": "describe"}}),
                session,
            )
        if action == "plot":
            return self.figure.run(
                task.model_copy(update={"payload": {**task.payload, "mode": "plot"}}),
                session,
            )
        if action == "compose":
            return run_compose(
                task,
                writer=self.writer,
                reviewer=self.reviewer,
                citation=self.citation,
                llm=self.llm,
                files=self.files,
                session=session,
            )
        if action == "export":
            return run_export(task, files=self.files, session=session)
        if action == "write_review":
            outputs = run_write_review_loop(
                task,
                writer=self.writer,
                reviewer=self.reviewer,
                max_rounds=int(task.payload.get("max_rounds", 3)),
                session=session,
            )
            return outputs[-1]
        if action == "figure_refine":
            producer = FigureAgentExpert(self.llm, files=self.files, vision=self.vision)
            critic = self.figure
            outputs = run_figure_refine(
                task.model_copy(update={"payload": {**task.payload, "mode": "plot"}}),
                producer=producer,
                critic=critic,
                max_rounds=int(task.payload.get("max_rounds", 3)),
                session=session,
            )
            return outputs[-1]
        if action == "orchestrate":
            # Local import of the capability manifest: it lives in the
            # integration package whose __init__ imports this module's
            # ClioAuthorAgent, so a top-level import would be circular.
            from clio_author.integration.manifest import ACTIONS

            return run_orchestrate(
                task,
                execute=self._execute_step,
                manifest=ACTIONS,
                llm=self.llm,
                files=self.files,
                session=session,
            )

        # Unknown / None action -> echo fallthrough (M0 back-compat).
        outputs = self.engine.run([self.echo_expert], self.pattern, task, session)
        return outputs[-1]

    def _execute_step(self, action: str, payload: dict[str, Any]) -> AgentOutput:
        """Run ONE routed action for the orchestrator and return its output.

        Builds a routed :class:`Task` and dispatches it through :meth:`_route`
        (a single action against a fresh session), guarding the call so a failure
        becomes an error-flagged output rather than propagating. ``orchestrate``
        is refused here so the orchestrator cannot recurse into itself.
        """
        if action == "orchestrate":
            return AgentOutput(
                agent="clio-author",
                content="",
                metadata={"error": "orchestrate cannot call itself", "action": action},
            )
        step_task = Task(
            id=uuid4().hex,
            description=action,
            payload={**payload, "action": action},
        )
        try:
            return self._route(action, step_task)
        except Exception as exc:  # noqa: BLE001 - never raise into the orchestrator
            return AgentOutput(
                agent="clio-author",
                content="",
                metadata={"error": str(exc), "action": action},
            )

    # --- typed convenience methods ------------------------------------------ #
    def _invoke(self, action: str, payload: dict[str, Any]) -> AgentOutput:
        """Build a routed :class:`Task` for ``action`` and invoke it."""
        return self.invoke(
            Task(id=uuid4().hex, description=action, payload={**payload, "action": action})
        )

    def ingest(self, source: str) -> AgentOutput:
        """Ingest ``source`` (arXiv id / URL / PDF path) into Markdown + blocks."""
        return self._invoke("ingest", {"source": source})

    def ask(self, question: str, blocks: Any) -> AgentOutput:
        """Answer ``question`` grounded in memory ``blocks``."""
        return self._invoke("ask", {"question": question, "blocks": blocks})

    def review(self, paper: Any, persona: Any = None) -> AgentOutput:
        """Produce a structured peer review of ``paper``."""
        payload: dict[str, Any] = {"paper": paper}
        if persona is not None:
            payload["persona"] = persona
        return self._invoke("review", payload)

    def cite(self, candidates: Any, **kw: Any) -> AgentOutput:
        """Verify citation ``candidates`` and emit suggestions only."""
        return self._invoke("cite", {"candidates": candidates, **kw})

    def write(self, *, outline: Any = None, source: Any = None, **kw: Any) -> AgentOutput:
        """Draft a section from ``outline`` grounded in ``source``."""
        payload: dict[str, Any] = dict(kw)
        if outline is not None:
            payload["outline"] = outline
        if source is not None:
            payload["source"] = source
        return self._invoke("write", payload)

    def compose(self, *, idea: Any = None, outline: Any = None, **kw: Any) -> AgentOutput:
        """Draft a whole multi-section manuscript from ``idea`` (+ optional ``outline``)."""
        payload: dict[str, Any] = dict(kw)
        if idea is not None:
            payload["idea"] = idea
        if outline is not None:
            payload["outline"] = outline
        return self._invoke("compose", payload)

    def plan(self, *, idea: Any = None, outline: Any = None, **kw: Any) -> AgentOutput:
        """Turn an ``idea`` (+ optional ``outline``) into per-section writing plans."""
        payload: dict[str, Any] = dict(kw)
        if idea is not None:
            payload["idea"] = idea
        if outline is not None:
            payload["outline"] = outline
        return self._invoke("plan", payload)

    def edit(self, draft: Any, review: Any) -> AgentOutput:
        """Revise ``draft`` to address ``review`` feedback."""
        return self._invoke("edit", {"draft": draft, "review": review})

    def describe_figures(self, blocks: Any) -> AgentOutput:
        """Fill figure descriptions for the figures in ``blocks``."""
        return self._invoke("describe_figures", {"blocks": blocks})

    def plot(self, spec: Any) -> AgentOutput:
        """Generate matplotlib plot code from ``spec`` (code text only)."""
        return self._invoke("plot", {"spec": spec})

    def kg(self, blocks: Any, **kw: Any) -> AgentOutput:
        """Extract a content knowledge graph from a paper's memory ``blocks``."""
        return self._invoke("kg", {"blocks": blocks, **kw})


def _bullets(label: str, items: Any) -> str:
    """Render ``items`` as a labelled bullet list (empty string when none)."""
    if not items:
        return ""
    lines = "\n".join(f"- {it}" for it in items)
    return f"{label}:\n{lines}\n\n"


def _source_titles(notes: Any) -> list[str]:
    """Render a list of research source-note dicts as ``title (grounded?)`` lines."""
    if not isinstance(notes, (list, tuple)):
        return []
    rendered: list[str] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        title = str(note.get("title") or "").strip()
        if not title:
            continue
        suffix = " [grounded]" if note.get("grounded") else ""
        rendered.append(f"{title}{suffix}")
    return rendered


def _prose_view(action: Any, out: AgentOutput) -> str:
    """Render an action's structured result as human-readable prose.

    Used when a caller asks for ``format="prose"``. Actions whose ``content`` is
    already prose/code (ask / write / edit / plot) just reuse it; the data-shaped
    actions (cite / meta_review / describe_figures) are textualized from their
    structured fields. Falls back to pretty-printed JSON if nothing else fits.
    """
    s = out.structured or {}
    meta = out.metadata or {}
    if action == "cite":
        bib = s.get("suggested_bibtex") or ""
        head = (
            f"Verified {meta.get('num_verified', '?')}/{meta.get('num_candidates', '?')} citations."
        )
        return f"{head}\n\n{bib}".strip()
    if action == "meta_review":
        head = (
            f"Meta-review across {s.get('reviewer_count', '?')} reviews — "
            f"Decision: {s.get('decision')} (overall {s.get('overall')}/10).\n\n"
        )
        return (
            head
            + _bullets("Strengths", s.get("strengths"))
            + _bullets("Weaknesses", s.get("weaknesses"))
        ).strip()
    if action == "describe_figures":
        ds = s.get("descriptions") or []
        rendered = "\n".join(f"Figure {d.get('figure_id')}: {d.get('description')}" for d in ds)
        return rendered or out.content
    if action == "research":
        head = (
            f"Research brief on '{s.get('topic', '')}' — confidence {s.get('confidence', '?')}.\n\n"
        )
        return (
            head
            + _bullets("Foundational", _source_titles(s.get("foundational")))
            + _bullets("Recent", _source_titles(s.get("recent")))
            + _bullets("Competing", _source_titles(s.get("competing")))
            + _bullets("Gaps", s.get("gaps"))
        ).strip() or out.content
    if action == "verify_work":
        head = f"Verification: {s.get('status', '?')}.\n\n"
        claim_lines = [
            f"- [{'made' if c.get('made') else 'not made'}/"
            f"{'supported' if c.get('supported') else 'unsupported'}] {c.get('claim', '')}"
            for c in (s.get("claims") or [])
            if isinstance(c, dict)
        ]
        body = ("Claims:\n" + "\n".join(claim_lines) + "\n\n") if claim_lines else ""
        return (head + body + _bullets("Gaps", s.get("gaps"))).strip() or out.content
    if action in ("check_refs", "audit", "section_review"):
        # These deterministic / aggregated actions already summarise themselves
        # in `content`; reuse it (falling back to pretty JSON).
        return out.content or json.dumps(s, indent=2)
    # ask / write / edit / plot / polish / coherence: content is already the
    # human answer / draft / code / polished prose / issue summary.
    return out.content or json.dumps(s, indent=2)


__all__ = ["ClioAuthorAgent"]

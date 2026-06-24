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
from clio_author.experts.cite_support import CiteSupportExpert
from clio_author.experts.coherence import CoherenceExpert
from clio_author.experts.compose import run_compose
from clio_author.experts.context import ContextExpert
from clio_author.experts.discover import DiscoverExpert
from clio_author.experts.echo import EchoExpert
from clio_author.experts.editor import EditorExpert
from clio_author.experts.experiment import ExperimentExpert
from clio_author.experts.figure_agent import FigureAgentExpert, run_figure_refine
from clio_author.experts.grounding import run_grounding
from clio_author.experts.ingestor import IngestorExpert
from clio_author.experts.kg import KGExpert
from clio_author.experts.meta_reviewer import MetaReviewerExpert
from clio_author.experts.orchestrate import run_orchestrate
from clio_author.experts.paper_qa import PaperQAExpert
from clio_author.experts.plan_check import PlanCheckExpert
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


# Actions that ground on memory ``blocks`` and so accept a ``sources`` list which
# is auto-gathered into blocks before dispatch (see ``_resolve_sources``).
_GROUNDING_ACTIONS: frozenset[str] = frozenset(
    {"ask", "plan", "write", "compose", "write_review", "research", "kg", "review", "experiment"}
)


def _arxiv_source_for(entry: dict[str, Any]) -> str | None:
    """Derive an ingestable arXiv id / source from a normalized citation entry.

    Prefers an explicit ``source``; otherwise reads the cited record's
    ``external_ids['ArXiv']`` or an ``arxiv:<id>`` ``paper_id``. Returns ``None``
    when no arXiv source is available (so deep mode falls back to the abstract).
    """
    source = entry.get("source")
    if isinstance(source, str) and source.strip():
        return source.strip()
    rec = entry.get("record")
    record: dict[str, Any] = rec if isinstance(rec, dict) else {}
    ext_raw = record.get("external_ids")
    ext: dict[str, Any] = ext_raw if isinstance(ext_raw, dict) else {}
    for field in ("ArXiv", "arxiv", "ARXIV"):
        value = ext.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    paper_id = str(record.get("paper_id") or "")
    if paper_id.lower().startswith("arxiv:"):
        return paper_id.split(":", 1)[1].strip() or None
    return None


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
        retriever: Any = None,
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
        self.paper_qa = PaperQAExpert(self.llm, retriever=retriever)
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
        self.discover = DiscoverExpert(self.llm, scholar_client=scholar_client)
        self.context = ContextExpert(self.llm, out_dir=files.root if files else None)
        self.experiment_expert = ExperimentExpert(self.llm, files=files)
        self.verify_work = VerifyWorkExpert(self.llm)
        self.check_refs = CheckRefsExpert(self.llm)
        self.cite_support = CiteSupportExpert(self.llm, full_text_resolver=self._cited_full_text)
        self.audit = AuditExpert(self.llm)
        self.plan_check = PlanCheckExpert(self.llm)

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
            # Attach "what to run next" hints (advisory; skipped on errors) so a
            # host or the CLI can guide the user through the pipeline.
            if not out.metadata.get("error") and isinstance(action, str):
                from clio_author.integration.manifest import suggested_next

                nxt = suggested_next(action)
                if nxt:
                    out.metadata.setdefault("suggested_next", nxt)
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

        # Auto-chain multi-source grounding: a `sources` list on a grounding
        # action (and no explicit `blocks`) is gathered into merged memory blocks
        # before dispatch, so `plan`/`write`/`compose`/... can be pointed straight
        # at files, folders, globs, git repos, or PDFs.
        task = self._resolve_sources(action, task)

        if action == "ingest":
            return self.ingestor.run(task, session)
        if action == "gather":
            return self.context.run(task, session)
        if action == "experiment":
            return self.experiment_expert.run(task, session)
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
        if action == "revise":
            return self._revise(task, session)
        # `edit` / `polish` are retained as backward-compatible aliases of the
        # unified `revise` action (edit == feedback mode, polish == style mode).
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
        if action == "discover":
            return self.discover.run(task, session)
        if action == "verify_work":
            return self.verify_work.run(task, session)
        if action == "check_refs":
            return self.check_refs.run(task, session)
        if action == "audit":
            return self.audit.run(task, session)
        if action == "plan_check":
            return self.plan_check.run(task, session)
        if action == "cite_support":
            return self.cite_support.run(task, session)
        if action == "ground":
            return run_grounding(
                task,
                check_refs=self.check_refs,
                verify_work=self.verify_work,
                cite_support=self.cite_support,
                session=session,
            )
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

    def _resolve_sources(self, action: Any, task: Task) -> Task:
        """Gather a ``sources`` list into ``blocks`` for grounding actions.

        When a grounding action carries a non-empty ``sources`` payload key and no
        explicit ``blocks``, ingest every source (file / folder / glob / git repo /
        PDF) and inject the merged :class:`MemoryBlocks` dump as ``blocks`` so the
        expert grounds on it unchanged. Best-effort and never raises: a gather
        failure or an empty result leaves the task untouched (the expert then
        reports missing grounding as before). The ``gather`` action is excluded --
        it consumes ``sources`` directly.
        """
        if action not in _GROUNDING_ACTIONS:
            return task
        payload = task.payload
        sources = payload.get("sources")
        if not sources or payload.get("blocks") is not None:
            return task
        try:
            from clio_author.ingest.gather import gather_context

            result = gather_context(sources, out_dir=self.files.root if self.files else None)
        except Exception:  # noqa: BLE001 - grounding is best-effort; never abort dispatch
            return task
        if not result.blocks.sections and not result.blocks.figures:
            return task
        return task.model_copy(
            update={
                "payload": {
                    **payload,
                    "blocks": result.blocks.model_dump(),
                    "gathered": {"ingested": result.ingested, "skipped": result.skipped},
                }
            }
        )

    def _cited_full_text(self, key: str, entry: dict[str, Any]) -> str | None:
        """Resolve a cited paper's full text for ``cite_support`` deep mode.

        The network seam injected into :class:`CiteSupportExpert`: derives an
        arXiv id (or an explicit ``source``) from the citation record, ingests it
        into Markdown via :class:`IngestorExpert`, and returns that text. Returns
        ``None`` on any failure so deep mode falls back to the abstract; never
        raises.
        """
        source = _arxiv_source_for(entry)
        if not source:
            return None
        try:
            out = self.ingestor.run(
                Task(id=uuid4().hex, description="ingest", payload={"source": source}),
                SessionContext(id=uuid4().hex),
            )
        except Exception:  # noqa: BLE001 - best-effort; fall back to abstract
            return None
        if out.metadata.get("error"):
            return None
        return out.content or None

    def _revise(self, task: Task, session: SessionContext) -> AgentOutput:
        """Unified prose revision: route by ``mode`` to the editor or polish expert.

        ``mode='style'`` (or ``'polish'``) runs the style-preserving
        :class:`PolishExpert`; any other value (default ``'feedback'``) runs the
        feedback-driven :class:`EditorExpert`. The prose is normalised onto
        ``draft`` so either expert finds it regardless of whether the caller
        supplied ``draft`` or ``text``.
        """
        payload = task.payload
        mode = str(payload.get("mode") or "feedback").strip().lower()
        prose = payload.get("draft") or payload.get("text")
        if prose is not None:
            payload = {**payload, "draft": prose, "text": prose}
            task = task.model_copy(update={"payload": payload})
        if mode in ("style", "polish"):
            return self.polish.run(task, session)
        return self.editor.run(task, session)

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

    def gather(self, sources: Any, **kw: Any) -> AgentOutput:
        """Gather many ``sources`` (files/folders/globs/git/PDFs) into merged blocks."""
        return self._invoke("gather", {"sources": sources, **kw})

    def experiment(self, *, idea: Any = None, **kw: Any) -> AgentOutput:
        """Extract reference paper designs and (with ``idea``) recreate an eval plan."""
        payload: dict[str, Any] = dict(kw)
        if idea is not None:
            payload["idea"] = idea
        return self._invoke("experiment", payload)

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

    def revise(self, draft: Any, *, mode: str = "feedback", **kw: Any) -> AgentOutput:
        """Revise ``draft``: ``mode='feedback'`` (address review) or ``'style'`` (polish)."""
        return self._invoke("revise", {"draft": draft, "mode": mode, **kw})

    def edit(self, draft: Any, review: Any) -> AgentOutput:
        """Revise ``draft`` to address ``review`` feedback (alias of ``revise``)."""
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
    if action == "discover":
        papers = s.get("papers") or []
        head = f"Discovered {s.get('count', len(papers))} candidate paper(s).\n\n"
        lines = []
        for paper in papers:
            if not isinstance(paper, dict):
                continue
            title = str(paper.get("title") or "").strip()
            if not title:
                continue
            year = paper.get("year")
            venue = str(paper.get("venue") or "").strip()
            suffix = " — ".join(part for part in (str(year) if year else "", venue) if part)
            lines.append(f"- {title}" + (f" ({suffix})" if suffix else ""))
        return (head + "\n".join(lines)).strip() or out.content
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

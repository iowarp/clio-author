"""The plan-check expert: deterministic *pre-write* validation of a section plan.

:class:`PlanCheckExpert` is :class:`~clio_author.experts.audit.AuditExpert`'s
twin from the other end of the pipeline. ``audit`` checks a *finished*
manuscript; ``plan_check`` checks the *plan* **before** any prose is written, so
problems are caught while they are still cheap to fix. It re-expresses the
pre-write "is this plan actually executable?" gate of the JS writing toolkit
wtf-p as a pure-Python, no-LLM expert:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concept* is reproduced (no source code copied). It validates the
``{outline, plans}`` structure that :class:`~clio_author.experts.planner.PlannerExpert`
emits against the dimensions our plan model supports:

* **outline coverage** — every outline section has a matching plan,
* **task completeness** — every section plan has at least one task,
* **claim coverage** — every section plan asserts at least one claim,
* **citation coverage** — every claim-bearing section has a source / citation hint,
* **word budgets** — every section has a budget, and (with a ``word_target``) the
  budgets sum to the target within a tolerance,
* **research readiness** — every ``research_needed`` section names its topics.

Because it never calls a model it always produces a real, deterministic result
(identical under the offline :class:`EchoLLMClient`). It emits a checklist + a
verdict and never writes. Like the other experts it never raises: bad input
produces an error-flagged :class:`AgentOutput` (appended once to the session).
"""

from __future__ import annotations

from typing import Any

from clio_author.experts.write_models import PaperOutline, SectionPlan
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Task
from clio_author.llm.client import EchoLLMClient, LLMClient

PLAN_CHECK_SYSTEM_PROMPT = (
    "You are the plan-check expert. Before any section is written, you run a "
    "deterministic validation over the writing plan: does every outline section "
    "have a plan, does every plan have tasks and claims, is every claim backed by "
    "a source, does every section have a word budget (summing to the target), and "
    "is every research-flagged section's topic named? You emit a checklist and a "
    "verdict only; you never write prose."
)

# How far the summed budget may drift from a supplied word_target (fraction).
_BUDGET_TOLERANCE = 0.15


class PlanCheckExpert(BaseAgent):
    """Expert that deterministically validates a writing plan before drafting."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        """Build a plan-check expert.

        Args:
            llm: Accepted for a uniform expert constructor shape and defaulted to
                :class:`EchoLLMClient`; this expert performs no model calls, so the
                value is never invoked.
        """
        super().__init__(
            role="plan_check",
            system_prompt=PLAN_CHECK_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )

    @staticmethod
    def _resolve(payload: dict[str, Any]) -> tuple[PaperOutline | None, list[SectionPlan]]:
        """Resolve ``(outline, plans)`` from the payload.

        Accepts ``plan`` (the planner's ``{outline, plans}`` structure or its
        ``model_dump``), or ``plans`` (a list) and ``outline`` supplied separately.
        Coercion is loose and never raises; unparseable plans are skipped.
        """
        plan_blob = payload.get("plan")
        raw_outline: Any = payload.get("outline")
        raw_plans: Any = payload.get("plans")
        if isinstance(plan_blob, dict):
            raw_outline = raw_outline if raw_outline is not None else plan_blob.get("outline")
            raw_plans = raw_plans if raw_plans is not None else plan_blob.get("plans")

        outline: PaperOutline | None = None
        if isinstance(raw_outline, PaperOutline):
            outline = raw_outline
        elif isinstance(raw_outline, dict):
            outline = PaperOutline.from_loose_dict(raw_outline)

        plans: list[SectionPlan] = []
        if isinstance(raw_plans, (list, tuple)):
            for item in raw_plans:
                if isinstance(item, SectionPlan):
                    plans.append(item)
                elif isinstance(item, dict):
                    try:
                        plans.append(SectionPlan.from_loose_dict(item))
                    except Exception:  # noqa: BLE001 - skip a bad plan, do not abort the check
                        continue
        return outline, plans

    @staticmethod
    def _word_target(payload: dict[str, Any]) -> int | None:
        raw = payload.get("word_target")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Validate the writing plan in ``task`` before drafting. Never raises.

        Reads ``plan`` (the planner's ``{outline, plans}``) or ``plans`` +
        ``outline``, plus an optional ``word_target``. Runs the six deterministic
        checks (outline coverage, task completeness, claim coverage, citation
        coverage, word budgets, research readiness). ``structured`` is the full
        checklist, ``content`` a one-line verdict, ``metadata`` carries
        ``passed`` / ``num_sections`` / ``num_problems``. With at least one plan
        present this always produces a real result (no LLM). No plans yields an
        error-flagged output.
        """
        try:
            payload = task.payload
            outline, plans = self._resolve(payload)
            if not plans:
                return self._error(session, "no 'plan'/'plans' provided to validate")

            word_target = self._word_target(payload)
            checklist = self._validate(outline, plans, word_target)
            problems = (
                len(checklist["missing_plans"])
                + len(checklist["taskless"])
                + len(checklist["claimless"])
                + len(checklist["uncited_claim_sections"])
                + len(checklist["missing_budgets"])
                + len(checklist["unresolved_research"])
                + (0 if checklist["budget_ok"] else 1)
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
                "num_sections": len(plans),
                "num_problems": problems,
            },
        )
        session.add(output)
        return output

    @staticmethod
    def _validate(
        outline: PaperOutline | None,
        plans: list[SectionPlan],
        word_target: int | None,
    ) -> dict[str, Any]:
        """Run the deterministic checks; return the full checklist dict."""
        plan_titles = {p.outline.title.strip().lower() for p in plans if p.outline.title}
        missing_plans = (
            [
                s.title
                for s in outline.sections
                if s.title and s.title.strip().lower() not in plan_titles
            ]
            if outline is not None
            else []
        )

        taskless: list[str] = []
        claimless: list[str] = []
        uncited: list[str] = []
        missing_budgets: list[str] = []
        unresolved_research: list[str] = []
        per_section: list[dict[str, Any]] = []
        budget_total = 0

        for plan in plans:
            node = plan.outline
            title = node.title or "Section"
            has_tasks = bool(plan.tasks)
            has_claims = bool(plan.claims)
            has_evidence = bool(plan.sources) or bool(node.citation_hints)
            budget = node.word_budget if (node.word_budget and node.word_budget > 0) else None
            if budget:
                budget_total += budget

            if not has_tasks:
                taskless.append(title)
            if not has_claims:
                claimless.append(title)
            if has_claims and not has_evidence:
                uncited.append(title)
            if budget is None:
                missing_budgets.append(title)
            if node.research_needed and not node.research_topics:
                unresolved_research.append(title)

            per_section.append(
                {
                    "title": title,
                    "num_tasks": len(plan.tasks),
                    "num_claims": len(plan.claims),
                    "has_evidence": has_evidence,
                    "word_budget": budget,
                    "research_ok": (not node.research_needed) or bool(node.research_topics),
                }
            )

        budget_ok = True
        if word_target is not None and word_target > 0:
            budget_ok = abs(budget_total - word_target) <= _BUDGET_TOLERANCE * word_target

        return {
            "sections": per_section,
            "missing_plans": missing_plans,
            "taskless": taskless,
            "claimless": claimless,
            "uncited_claim_sections": uncited,
            "missing_budgets": missing_budgets,
            "unresolved_research": unresolved_research,
            "budget_total": budget_total,
            "word_target": word_target,
            "budget_ok": budget_ok,
        }


def _render_verdict(passed: bool, checklist: dict[str, Any]) -> str:
    """Render a one-line human verdict from the plan-check checklist."""
    if passed:
        return (
            "Plan check PASSED: every section has a plan, tasks, claims, a backed "
            "source, and a word budget."
        )
    parts: list[str] = ["Plan check FOUND ISSUES:"]
    bits: list[str] = []
    if checklist["missing_plans"]:
        bits.append(f"{len(checklist['missing_plans'])} outline section(s) with no plan")
    if checklist["taskless"]:
        bits.append(f"{len(checklist['taskless'])} section(s) with no tasks")
    if checklist["claimless"]:
        bits.append(f"{len(checklist['claimless'])} section(s) with no claims")
    if checklist["uncited_claim_sections"]:
        bits.append(f"{len(checklist['uncited_claim_sections'])} section(s) claim without a source")
    if checklist["missing_budgets"]:
        bits.append(f"{len(checklist['missing_budgets'])} section(s) with no word budget")
    if checklist["unresolved_research"]:
        bits.append(f"{len(checklist['unresolved_research'])} research section(s) with no topics")
    if not checklist["budget_ok"]:
        bits.append(f"budget {checklist['budget_total']} off target {checklist['word_target']}")
    return parts[0] + " " + ", ".join(bits) + "."


__all__ = ["PlanCheckExpert", "PLAN_CHECK_SYSTEM_PROMPT"]

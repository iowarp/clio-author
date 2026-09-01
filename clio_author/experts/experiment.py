"""The experiment expert: extract paper designs, recreate an evaluation plan.

:class:`ExperimentExpert` (action ``experiment``) supports the workflow "read the
design / architecture / experiments of one or more reference papers, then
recreate a grounded evaluation plan for the new paper I'm writing". It works in
two phases:

1. **Extract** -- for each reference paper it reads (a merged :class:`MemoryBlocks`
   from ``ingest``/``gather``, or raw Markdown/text), it asks the model for a
   :class:`~clio_author.experts.experiment_models.PaperDesign`: research
   questions, architecture/method, datasets, baselines, metrics, ablations,
   protocol, compute, and limitations.
2. **Recreate** -- when a new-paper ``idea`` is supplied, it synthesises an
   :class:`~clio_author.experts.experiment_models.EvaluationPlan`: which datasets
   to use, baselines to compare against, metrics to report, ablations to run, the
   protocol, and threats to validity -- each recommendation grounded in (and
   citing) the reference papers and adapted to the new idea.

Multi-paper input is recovered from the ``[label]`` section prefixes that
``gather`` writes, so a single merged block set yields one design per source.
Like every expert it never raises (missing input or any failure -> error-flagged
:class:`AgentOutput`) and defaults to :class:`EchoLLMClient` so the harness runs
offline; a section whose JSON does not parse degrades to an empty design rather
than aborting.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from clio_author.experts.experiment_models import EvaluationPlan, PaperDesign, PlanItem
from clio_author.experts.reviewer import _extract_json_object
from clio_author.harness.base import BaseAgent
from clio_author.harness.session import SessionContext
from clio_author.harness.types import AgentOutput, Message, Task
from clio_author.ingest.blocks import MemoryBlocks
from clio_author.llm.client import EchoLLMClient, LLMClient
from clio_author.tools.files import SafeFiles, wants_overwrite, write_artifacts

EXPERIMENT_SYSTEM_PROMPT = (
    "You are the experiment-design analyst. From a paper's text you extract its "
    "empirical design: research questions, architecture/method components, "
    "datasets, baselines, metrics, ablations, experimental protocol/setup, "
    "compute/hardware, and limitations/threats to validity. Extract only what the "
    "paper states; never invent datasets, baselines, or numbers."
)

PLAN_SYSTEM_PROMPT = (
    "You are the evaluation architect. Given the experimental designs extracted "
    "from one or more reference papers and the idea for a NEW paper, you recreate "
    "a concrete, grounded evaluation plan for the new paper: which datasets to "
    "use, which baselines to compare against, which metrics to report, which "
    "ablations to run, the experimental protocol, and threats to validity to "
    "control for. Ground every recommendation in the reference papers (name the "
    "source paper); adapt it to the new idea. Mark anything not supported by a "
    "reference as a suggested extension."
)

_EXTRACT_INSTRUCTIONS = (
    "Extract this paper's empirical design as a fenced JSON block:\n"
    "```json\n"
    '{"research_questions": ["..."], "architecture": ["<method/system component>"], '
    '"datasets": ["..."], "baselines": ["..."], "metrics": ["..."], '
    '"ablations": ["<ablation/variation studied>"], '
    '"protocol": ["<experimental setup/procedure step>"], '
    '"compute": ["<hardware/resource>"], "limitations": ["<limitation/threat>"]}\n'
    "```\n"
    "Use [] for anything the paper does not state. The JSON is parsed automatically."
)

_PLAN_INSTRUCTIONS = (
    "Recreate an evaluation plan for the NEW paper as a fenced JSON block. Each "
    "dataset/baseline/metric/ablation is an object {name, rationale, source} where "
    "source names the reference paper it is grounded in:\n"
    "```json\n"
    '{"datasets": [{"name": "...", "rationale": "...", "source": "..."}], '
    '"baselines": [{"name": "...", "rationale": "...", "source": "..."}], '
    '"metrics": [{"name": "...", "rationale": "...", "source": "..."}], '
    '"ablations": [{"name": "...", "rationale": "...", "source": "..."}], '
    '"protocol": ["<setup/procedure step the new paper should follow>"], '
    '"risks": ["<threat to validity to control for>"], '
    '"notes": "<short guidance>"}\n'
    "```\n"
    "The JSON is parsed automatically."
)

# Section titles whose content is most relevant to the empirical design; used to
# bias the per-paper context toward methods/experiments before the char cap.
_RELEVANT_RE = re.compile(
    r"method|approach|architect|model|system|design|experiment|evaluat|setup|"
    r"dataset|benchmark|baseline|metric|ablation|result|implementation|protocol",
    re.IGNORECASE,
)
_SECTION_LABEL_RE = re.compile(r"^\[(?P<label>[^\]]+)\]\s*(?P<rest>.*)$")
_PER_PAPER_CHARS = 8000


class ExperimentExpert(BaseAgent):
    """Expert that extracts paper designs and recreates an evaluation plan."""

    def __init__(self, llm: LLMClient | None = None, *, files: SafeFiles | None = None) -> None:
        """Build an experiment expert.

        Args:
            llm: Completion client; defaults to :class:`EchoLLMClient` (offline).
            files: Optional :class:`SafeFiles` for persisting artifacts when
                ``payload["out_dir"]`` is provided.
        """
        super().__init__(
            role="experiment",
            system_prompt=EXPERIMENT_SYSTEM_PROMPT,
            llm=llm or EchoLLMClient(),
        )
        self._files = files

    def _error(self, session: SessionContext, message: str) -> AgentOutput:
        output = AgentOutput(agent=self.name, content="", metadata={"error": message})
        session.add(output)
        return output

    def run(self, task: Task, session: SessionContext) -> AgentOutput:
        """Extract reference designs and (with an ``idea``) recreate an eval plan.

        Reads ``blocks`` (a merged :class:`MemoryBlocks`, possibly multi-paper via
        ``[label]`` section prefixes), or ``markdown`` / ``text`` (one paper);
        ``idea`` (the new paper -- triggers plan synthesis); and ``out_dir``.
        Returns an :class:`AgentOutput` whose ``structured`` is
        ``{"designs": [...], "evaluation_plan": {...}|None}`` and whose
        ``metadata`` carries ``num_papers`` / ``has_plan`` / ``wrote``. Never
        raises: missing input or any failure produces an error-flagged output.
        """
        try:
            return self._run(task, session)
        except Exception as exc:  # noqa: BLE001 - experts never raise
            return self._error(session, str(exc))

    def _run(self, task: Task, session: SessionContext) -> AgentOutput:
        payload = task.payload
        papers = self._resolve_papers(payload)
        if not papers:
            return self._error(session, "no 'blocks'/'markdown'/'text'/'sources' provided")

        designs = [self._extract_design(label, text) for label, text in papers]

        idea = str(payload.get("idea") or "").strip()
        plan: EvaluationPlan | None = None
        if idea:
            plan = self._recreate_plan(idea, designs)

        wrote, write_skipped = self._maybe_write(payload, designs, plan)

        if plan is not None:
            content = render_plan_markdown(plan)
        else:
            content = render_designs_markdown(designs)
        summary = f"Extracted {len(designs)} paper design(s)" + (
            "; recreated an evaluation plan." if plan is not None else "."
        )
        output = AgentOutput(
            agent=self.name,
            content=content or summary,
            structured={
                "designs": [d.model_dump() for d in designs],
                "evaluation_plan": plan.model_dump() if plan is not None else None,
            },
            metadata={
                "num_papers": len(designs),
                "has_plan": plan is not None,
                "summary": summary,
                "wrote": wrote,
                **({"write_skipped": write_skipped} if write_skipped else {}),
            },
        )
        session.add(output)
        return output

    # --- input resolution --------------------------------------------------- #
    @staticmethod
    def _resolve_papers(payload: dict[str, Any]) -> list[tuple[str, str]]:
        """Resolve ``(label, text)`` pairs, one per reference paper.

        Prefers ``blocks`` (grouped by the ``[label]`` section prefix that
        ``gather`` writes -> one paper per source); falls back to raw
        ``markdown`` / ``text`` (a single paper).
        """
        blocks_raw = payload.get("blocks")
        if blocks_raw is not None:
            blocks = (
                blocks_raw
                if isinstance(blocks_raw, MemoryBlocks)
                else MemoryBlocks.model_validate(blocks_raw)
                if isinstance(blocks_raw, dict)
                else None
            )
            if blocks is not None:
                grouped = _group_sections_by_paper(blocks)
                if grouped:
                    return grouped
        raw = payload.get("markdown") or payload.get("text") or payload.get("paper")
        if raw:
            text = raw if isinstance(raw, str) else str(raw)
            return [("paper", text[:_PER_PAPER_CHARS])]
        return []

    # --- phase 1: extract --------------------------------------------------- #
    def _extract_design(self, label: str, text: str) -> PaperDesign:
        """Extract one paper's :class:`PaperDesign` (empty on parse failure)."""
        messages = [
            Message(role="system", content=self.system_prompt),
            Message(
                role="user",
                content=f"Paper: {label}\n\n{text}\n\n{_EXTRACT_INSTRUCTIONS}",
            ),
        ]
        parsed = _extract_json_object(self.llm.complete(messages))
        if parsed is None:
            return PaperDesign(paper=label)
        return PaperDesign.from_loose_dict(parsed, paper=label)

    # --- phase 2: recreate -------------------------------------------------- #
    def _recreate_plan(self, idea: str, designs: list[PaperDesign]) -> EvaluationPlan:
        """Synthesise an :class:`EvaluationPlan` from designs + the new idea."""
        designs_json = json.dumps([d.model_dump() for d in designs], indent=2)
        messages = [
            Message(role="system", content=PLAN_SYSTEM_PROMPT),
            Message(
                role="user",
                content=(
                    f"New paper idea:\n{idea}\n\n"
                    f"Reference paper designs (JSON):\n{designs_json}\n\n"
                    f"{_PLAN_INSTRUCTIONS}"
                ),
            ),
        ]
        parsed = _extract_json_object(self.llm.complete(messages))
        if parsed is None:
            return EvaluationPlan(idea=idea)
        return EvaluationPlan.from_loose_dict(parsed, idea=idea)

    # --- persistence -------------------------------------------------------- #
    def _maybe_write(
        self,
        payload: dict[str, Any],
        designs: list[PaperDesign],
        plan: EvaluationPlan | None,
    ) -> tuple[list[str], list[str]]:
        """Persist design/plan artifacts under ``out_dir`` (best-effort, no clobber).

        Mirrors :meth:`PlannerExpert._maybe_write`: when constructed with a
        :class:`SafeFiles`, ``out_dir`` is a subdirectory under that sandbox;
        otherwise ``out_dir`` is the output root directly (the CLI/adapter case).
        """
        out_dir = payload.get("out_dir")
        if not out_dir:
            return [], []
        if self._files is not None:
            files = self._files
            prefix = f"{out_dir}/"
        else:
            files = SafeFiles(Path(str(out_dir)))
            prefix = ""
        try:
            (files.root / prefix).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return [], [f"{out_dir}: {exc}"]

        artifacts: list[tuple[str, str]] = [
            (
                "experiment_designs.json",
                json.dumps([d.model_dump() for d in designs], indent=2),
            ),
            ("experiment_designs.md", render_designs_markdown(designs)),
        ]
        if plan is not None:
            artifacts.append(("evaluation_plan.json", json.dumps(plan.model_dump(), indent=2)))
            artifacts.append(("evaluation_plan.md", render_plan_markdown(plan)))
        return write_artifacts(
            files,
            ((f"{prefix}{name}", content) for name, content in artifacts),
            overwrite=wants_overwrite(payload),
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _group_sections_by_paper(blocks: MemoryBlocks) -> list[tuple[str, str]]:
    """Group a (possibly merged) block set into ``(label, text)`` per paper.

    Recovers the per-source grouping from the ``[label]`` prefix ``gather`` writes
    onto each ``section_path``. Unlabelled blocks fall under the paper title (or
    ``"paper"``). Relevant (method/experiment) sections are placed first, and each
    paper's text is capped to keep the extraction prompt bounded.
    """
    order: list[str] = []
    grouped: dict[str, list[tuple[bool, str]]] = {}
    default_label = str(blocks.metadata.get("title") or "").strip() or "paper"

    for section in blocks.sections:
        match = _SECTION_LABEL_RE.match(section.section_path)
        if match:
            label = match.group("label").strip() or default_label
            heading = match.group("rest").strip()
        else:
            label = default_label
            heading = section.section_path
        if label not in grouped:
            grouped[label] = []
            order.append(label)
        relevant = bool(_RELEVANT_RE.search(heading)) if heading else False
        body = f"## {heading}\n{section.text}".strip() if heading else section.text.strip()
        if body:
            grouped[label].append((relevant, body))

    papers: list[tuple[str, str]] = []
    for label in order:
        chunks = grouped[label]
        # Relevant sections first (stable), then the rest; then cap.
        chunks.sort(key=lambda pair: 0 if pair[0] else 1)
        text = "\n\n".join(body for _, body in chunks)[:_PER_PAPER_CHARS]
        if text.strip():
            papers.append((label, text))
    return papers


def _bullets(items: list[str]) -> str:
    """Render a list as Markdown bullets (empty string when none)."""
    return "\n".join(f"- {item}" for item in items)


def _design_block(design: PaperDesign) -> str:
    """Render one :class:`PaperDesign` as a Markdown subsection."""
    parts = [f"### {design.paper or 'paper'}"]
    fields = [
        ("Research questions", design.research_questions),
        ("Architecture / method", design.architecture),
        ("Datasets", design.datasets),
        ("Baselines", design.baselines),
        ("Metrics", design.metrics),
        ("Ablations", design.ablations),
        ("Protocol / setup", design.protocol),
        ("Compute", design.compute),
        ("Limitations / threats", design.limitations),
    ]
    for title, items in fields:
        if items:
            parts.append(f"**{title}:**\n{_bullets(items)}")
    if design.is_empty():
        parts.append("_(no design fields extracted)_")
    return "\n\n".join(parts)


def render_designs_markdown(designs: list[PaperDesign]) -> str:
    """Render extracted paper designs as a Markdown document."""
    if not designs:
        return ""
    body = "\n\n".join(_design_block(d) for d in designs)
    return f"# Reference experiment designs\n\n{body}\n"


def _item_table(title: str, items: list[PlanItem]) -> str:
    """Render a list of :class:`PlanItem`s as a Markdown table under ``title``."""
    if not items:
        return ""
    rows = "\n".join(
        f"| {item.name} | {item.rationale or '—'} | {item.source or '—'} |" for item in items
    )
    return f"## {title}\n\n| Item | Why | From |\n|---|---|---|\n{rows}"


def render_plan_markdown(plan: EvaluationPlan) -> str:
    """Render an :class:`EvaluationPlan` as a drop-in Markdown evaluation section."""
    header = f"# Evaluation plan: {plan.idea}" if plan.idea else "# Evaluation plan"
    sections = [
        header,
        _item_table("Datasets", plan.datasets),
        _item_table("Baselines", plan.baselines),
        _item_table("Metrics", plan.metrics),
        _item_table("Ablations", plan.ablations),
    ]
    if plan.protocol:
        sections.append(f"## Protocol\n\n{_bullets(plan.protocol)}")
    if plan.risks:
        sections.append(f"## Threats to validity / risks\n\n{_bullets(plan.risks)}")
    if plan.notes:
        sections.append(f"## Notes\n\n{plan.notes}")
    return "\n\n".join(part for part in sections if part).strip() + "\n"


__all__ = [
    "ExperimentExpert",
    "EXPERIMENT_SYSTEM_PROMPT",
    "PLAN_SYSTEM_PROMPT",
    "render_designs_markdown",
    "render_plan_markdown",
]

"""Pydantic v2 schemas for experiment-design extraction and evaluation planning.

Two shapes back the ``experiment`` action:

* :class:`PaperDesign` -- the empirical design extracted from one reference
  paper: research questions, architecture/method components, datasets,
  baselines, metrics, ablations, protocol/setup, compute, and limitations.
* :class:`EvaluationPlan` -- a *recreated* evaluation blueprint for a new paper,
  synthesised from one or more :class:`PaperDesign`s and the new idea. Each
  recommended dataset/baseline/metric/ablation is a :class:`PlanItem` carrying a
  rationale and the reference paper it is grounded in.

Each model exposes ``from_loose_dict`` to map a loose / partial LLM response onto
the fields, coercing scalars to lists and supplying defaults so a noisy response
still validates. The coercion idioms follow ``research_models.py`` /
``write_models.py``; no external source is copied.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


def _coerce_list(raw: Any) -> list[str]:
    """Coerce ``raw`` into a list of strings (wrapping a lone scalar)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [str(raw)]


def _norm_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Lower-case / underscore-normalise the keys of a loose dict."""
    return {str(key).strip().lower().replace(" ", "_"): value for key, value in raw.items()}


class PaperDesign(BaseModel):
    """The empirical design extracted from one reference paper."""

    paper: str = ""
    research_questions: list[str] = Field(default_factory=list)
    architecture: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    ablations: list[str] = Field(default_factory=list)
    protocol: list[str] = Field(default_factory=list)
    compute: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any], *, paper: str = "") -> PaperDesign:
        """Build a :class:`PaperDesign` from a loose/partial LLM dict."""
        data = _norm_keys(raw)
        # Accept a few common synonyms for the keys.
        method = data.get("architecture") or data.get("method") or data.get("approach")
        protocol = data.get("protocol") or data.get("setup") or data.get("experimental_setup")
        compute = data.get("compute") or data.get("hardware") or data.get("resources")
        rqs = data.get("research_questions") or data.get("questions") or data.get("goals")
        return cls(
            paper=str(data.get("paper") or paper or "").strip(),
            research_questions=_coerce_list(rqs),
            architecture=_coerce_list(method),
            datasets=_coerce_list(data.get("datasets")),
            baselines=_coerce_list(data.get("baselines")),
            metrics=_coerce_list(data.get("metrics")),
            ablations=_coerce_list(data.get("ablations")),
            protocol=_coerce_list(protocol),
            compute=_coerce_list(compute),
            limitations=_coerce_list(data.get("limitations") or data.get("threats")),
        )

    def is_empty(self) -> bool:
        """True when no design fields were populated (only the paper label)."""
        return not any(
            (
                self.research_questions,
                self.architecture,
                self.datasets,
                self.baselines,
                self.metrics,
                self.ablations,
                self.protocol,
                self.compute,
                self.limitations,
            )
        )


class PlanItem(BaseModel):
    """One recommended evaluation element, grounded in a reference paper."""

    name: str
    rationale: str = ""
    source: str = ""

    @classmethod
    def from_loose(cls, raw: Any) -> PlanItem | None:
        """Build a :class:`PlanItem` from a string or a loose dict (``None`` if empty)."""
        if isinstance(raw, str):
            name = raw.strip()
            return cls(name=name) if name else None
        if isinstance(raw, dict):
            data = _norm_keys(raw)
            name = str(data.get("name") or data.get("item") or data.get("title") or "").strip()
            if not name:
                return None
            source = data.get("source") or data.get("from") or data.get("paper")
            return cls(
                name=name,
                rationale=str(data.get("rationale") or data.get("why") or "").strip(),
                source=str(source or "").strip(),
            )
        return None


def _coerce_items(raw: Any) -> list[PlanItem]:
    """Coerce ``raw`` (list of strings/dicts) into :class:`PlanItem`s."""
    if not isinstance(raw, (list, tuple)):
        raw = [raw] if raw else []
    items = [PlanItem.from_loose(entry) for entry in raw]
    return [item for item in items if item is not None]


class EvaluationPlan(BaseModel):
    """A recreated evaluation blueprint for a new paper, grounded in references."""

    idea: str = ""
    datasets: list[PlanItem] = Field(default_factory=list)
    baselines: list[PlanItem] = Field(default_factory=list)
    metrics: list[PlanItem] = Field(default_factory=list)
    ablations: list[PlanItem] = Field(default_factory=list)
    protocol: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any], *, idea: str = "") -> EvaluationPlan:
        """Build an :class:`EvaluationPlan` from a loose/partial LLM dict."""
        data = _norm_keys(raw)
        risks = data.get("risks") or data.get("threats") or data.get("threats_to_validity")
        return cls(
            idea=str(data.get("idea") or idea or "").strip(),
            datasets=_coerce_items(data.get("datasets")),
            baselines=_coerce_items(data.get("baselines")),
            metrics=_coerce_items(data.get("metrics")),
            ablations=_coerce_items(data.get("ablations")),
            protocol=_coerce_list(data.get("protocol") or data.get("setup")),
            risks=_coerce_list(risks),
            notes=str(data.get("notes") or "").strip(),
        )


__all__ = ["PaperDesign", "PlanItem", "EvaluationPlan"]

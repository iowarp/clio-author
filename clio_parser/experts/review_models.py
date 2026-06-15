"""Pydantic v2 schemas for paper review and meta-review.

The review rubric and field set are adapted from the AgentReview prompt used in
PaperOrchestra ``autoraters/agent_review.py``:

    https://github.com/google-deepmind/paper-orchestra  (Apache-2.0)
    Copyright 2026 Google LLC; licensed under the Apache License, Version 2.0.

Only the *concepts* (field names, score ranges, rubric semantics) are re-typed
here as Pydantic models; no source code is copied. :meth:`PaperReview.from_loose_dict`
maps the upstream TitleCase JSON keys onto these snake_case fields, coerces
scalars to lists where the schema expects a list, clamps numeric scores into
their declared bounds, and supplies defaults for missing fields so a noisy or
partial LLM response still yields a valid model.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

Decision = Literal["Accept", "Reject"]
"""The two allowed review decisions (no borderline/weak variants)."""


class PersonaSpec(BaseModel):
    """Reviewer persona dimensions, mirroring AgentReview's role descriptions."""

    knowledgeable: bool = True
    responsible: bool = True
    benign: bool = True
    label: str = "reviewer"


def _clamp(value: int, low: int, high: int) -> int:
    """Clamp ``value`` into the inclusive ``[low, high]`` range."""
    return max(low, min(high, value))


def _coerce_int(raw: Any, default: int, low: int, high: int) -> int:
    """Best-effort parse ``raw`` to an int, then clamp into ``[low, high]``."""
    try:
        value = int(round(float(raw)))
    except (TypeError, ValueError):
        return default
    return _clamp(value, low, high)


def _coerce_list(raw: Any) -> list[str]:
    """Coerce ``raw`` into a list of strings (wrapping a lone scalar)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw if str(item).strip()]
    return [str(raw)]


def _coerce_bool(raw: Any) -> bool:
    """Coerce common truthy/falsey scalar encodings into a ``bool``."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "yes", "1"}
    return bool(raw)


def _coerce_decision(raw: Any) -> Decision:
    """Map ``raw`` onto ``Accept``/``Reject`` (defaulting to ``Reject``).

    Detection is *substring*-based on ``"accept"`` (case-insensitive): any string
    containing it maps to ``"Accept"`` (so ``"Weak Accept"`` -> ``Accept``), and
    anything else -- including ``"Borderline Reject"`` or non-strings -- maps to
    ``"Reject"``.
    """
    if isinstance(raw, str) and "accept" in raw.strip().lower():
        return "Accept"
    return "Reject"


class PaperReview(BaseModel):
    """A single peer review of a paper (AgentReview field set, re-typed)."""

    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    ethical_concerns: bool = False
    originality: int = Field(default=1, ge=1, le=4)
    quality: int = Field(default=1, ge=1, le=4)
    clarity: int = Field(default=1, ge=1, le=4)
    significance: int = Field(default=1, ge=1, le=4)
    soundness: int = Field(default=1, ge=1, le=4)
    presentation: int = Field(default=1, ge=1, le=4)
    contribution: int = Field(default=1, ge=1, le=4)
    overall: int = Field(default=1, ge=1, le=10)
    confidence: int = Field(default=1, ge=1, le=5)
    decision: Decision = "Reject"

    # Maps a snake_case field name -> the inclusive (low, high) score bounds.
    _AXIS_BOUNDS: ClassVar[dict[str, tuple[int, int]]] = {
        "originality": (1, 4),
        "quality": (1, 4),
        "clarity": (1, 4),
        "significance": (1, 4),
        "soundness": (1, 4),
        "presentation": (1, 4),
        "contribution": (1, 4),
        "overall": (1, 10),
        "confidence": (1, 5),
    }

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any]) -> PaperReview:
        """Build a :class:`PaperReview` from a loose (AgentReview-shaped) dict.

        Accepts the upstream TitleCase keys (e.g. ``"Summary"``,
        ``"Ethical Concerns"``) as well as the model's own snake_case names.
        Scalars are coerced to lists where the schema expects a list, numeric
        scores are parsed and clamped into bounds, and any missing field falls
        back to its schema default (lists -> ``[]``, decision -> ``"Reject"``).
        Never raises on malformed input.
        """
        # Normalise keys: TitleCase / spaced -> snake_case, lower-cased.
        norm: dict[str, Any] = {}
        for key, value in raw.items():
            slug = str(key).strip().lower().replace(" ", "_")
            norm[slug] = value

        def pick(*names: str) -> Any:
            for name in names:
                if name in norm:
                    return norm[name]
            return None

        data: dict[str, Any] = {
            "summary": str(pick("summary") or ""),
            "strengths": _coerce_list(pick("strengths")),
            "weaknesses": _coerce_list(pick("weaknesses")),
            "questions": _coerce_list(pick("questions")),
            "limitations": _coerce_list(pick("limitations")),
            "ethical_concerns": _coerce_bool(pick("ethical_concerns")),
            "decision": _coerce_decision(pick("decision")),
        }
        for axis, (low, high) in cls._AXIS_BOUNDS.items():
            data[axis] = _coerce_int(norm.get(axis), default=low, low=low, high=high)

        return cls.model_validate(data)


class MetaReview(PaperReview):
    """An area-chair meta-review aggregating multiple :class:`PaperReview`s."""

    reviewer_count: int = 0


__all__ = ["Decision", "PersonaSpec", "PaperReview", "MetaReview"]

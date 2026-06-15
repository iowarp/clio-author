"""Pydantic v2 schemas for the figure agent: plot specs, descriptions, artifacts.

The figure-agent capability set (describe/caption figures + generate plot code via
a visualizer that is refined by a critic) is a behavior reference from PaperBanana /
papervizagent:

    https://github.com/JoshuaChou2018/papervizagent  (Apache-2.0)

Only the *concepts* (a plot spec, a per-figure description, a generated artifact)
are re-typed here as Pydantic models; no source code is copied. The
``PlotSpec.from_loose_dict`` coercion idiom follows ``review_models.py`` /
``write_models.py``: it maps a loose / partial LLM dict onto the fields, coercing
scalars and supplying defaults so a noisy response still validates. Never raises on
bad input.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

PlotKind = Literal["plot", "diagram"]
"""Whether a :class:`PlotSpec` asks for a data plot or a schematic diagram."""


def _str_or_none(raw: Any) -> str | None:
    """Render ``raw`` to a stripped string, or ``None`` when absent/empty."""
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


class PlotSpec(BaseModel):
    """A request for a generated figure: what to draw and any data hint."""

    kind: PlotKind = "plot"
    intent: str
    data_hint: str = ""
    aspect_ratio: str | None = None

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any]) -> PlotSpec:
        """Build a :class:`PlotSpec` from a loose / partial dict. Never raises.

        Accepts common key spellings, defaults ``kind`` to ``"plot"`` (and falls
        back to ``"plot"`` for any unrecognised value), and supplies empty
        defaults for missing fields.
        """
        norm: dict[str, Any] = {}
        for key, value in raw.items():
            slug = str(key).strip().lower().replace(" ", "_")
            norm[slug] = value

        def pick(*names: str) -> Any:
            for name in names:
                if name in norm:
                    return norm[name]
            return None

        raw_kind = str(pick("kind", "type") or "plot").strip().lower()
        kind: PlotKind = "diagram" if raw_kind == "diagram" else "plot"

        return cls(
            kind=kind,
            intent=str(pick("intent", "goal", "description") or ""),
            data_hint=str(pick("data_hint", "data", "hint") or ""),
            aspect_ratio=_str_or_none(pick("aspect_ratio", "aspect", "ratio")),
        )


class FigureDescription(BaseModel):
    """A description (and optional caption) produced for one figure."""

    figure_id: int
    description: str
    caption: str | None = None


class FigureArtifact(BaseModel):
    """A generated figure artifact: plot code, an image path, and/or a description.

    The figure agent's default (hermetic) path produces only ``code`` (matplotlib
    text); ``image_path`` is populated only by a gated render step.
    """

    kind: str
    code: str | None = None
    image_path: str | None = None
    description: str | None = None


__all__ = [
    "PlotKind",
    "PlotSpec",
    "FigureDescription",
    "FigureArtifact",
]

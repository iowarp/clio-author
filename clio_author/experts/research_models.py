"""Pydantic v2 schemas for a literature-research brief.

The notion of a structured "research brief" -- foundational vs. recent vs.
competing sources, identified gaps, and a confidence verdict -- mirrors the
research/ideation step of the JS writing toolkit wtf-p:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concepts* (the source-bucketing taxonomy and the gap/synthesis
shape) are re-typed here as Pydantic models; no source code is copied.
:meth:`SourceNote.from_loose_dict` and :meth:`ResearchBrief.from_loose_dict` map
a loose / partial LLM dict onto these fields, coercing scalars to lists and
supplying defaults so a noisy response still validates. The coercion idioms
follow ``write_models.py`` / ``review_models.py``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Confidence = Literal["HIGH", "MEDIUM", "LOW"]
"""How confident the brief is, given how well sources were grounded."""


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


def _coerce_confidence(raw: Any) -> Confidence:
    """Map ``raw`` onto ``HIGH``/``MEDIUM``/``LOW`` (defaulting to ``LOW``)."""
    text = str(raw or "").strip().upper()
    if text in ("HIGH", "MEDIUM", "LOW"):
        return text  # type: ignore[return-value]
    return "LOW"


def _norm_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Lower-case / underscore-normalise the keys of a loose dict."""
    return {str(key).strip().lower().replace(" ", "_"): value for key, value in raw.items()}


class SourceNote(BaseModel):
    """A single proposed source: a title, why it matters, and grounding state."""

    title: str
    note: str = ""
    year: int | None = None
    grounded: bool = False
    verified_title: str | None = None

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any]) -> SourceNote:
        """Build a :class:`SourceNote` from a loose / partial dict. Never raises."""
        norm = _norm_keys(raw)

        def pick(*names: str) -> Any:
            for name in names:
                if name in norm:
                    return norm[name]
            return None

        year_raw = pick("year")
        try:
            year = int(round(float(year_raw))) if year_raw is not None else None
        except (TypeError, ValueError):
            year = None

        return cls(
            title=str(pick("title", "name") or "").strip(),
            note=str(pick("note", "reason", "why", "relevance") or "").strip(),
            year=year,
            grounded=bool(pick("grounded") or False),
            verified_title=(str(pick("verified_title")) if pick("verified_title") else None),
        )


class ResearchBrief(BaseModel):
    """A structured literature-research brief for a topic / section."""

    topic: str = ""
    foundational: list[SourceNote] = Field(default_factory=list)
    recent: list[SourceNote] = Field(default_factory=list)
    competing: list[SourceNote] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    synthesis: dict[str, list[str]] = Field(default_factory=dict)
    confidence: Confidence = "LOW"
    recommendations: list[str] = Field(default_factory=list)

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any]) -> ResearchBrief:
        """Build a :class:`ResearchBrief` from a loose / partial dict. Never raises."""
        norm = _norm_keys(raw)

        def pick(*names: str) -> Any:
            for name in names:
                if name in norm:
                    return norm[name]
            return None

        def sources(*names: str) -> list[SourceNote]:
            value = pick(*names)
            notes: list[SourceNote] = []
            if isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, SourceNote):
                        notes.append(item)
                    elif isinstance(item, dict):
                        notes.append(SourceNote.from_loose_dict(item))
                    elif isinstance(item, str) and item.strip():
                        notes.append(SourceNote(title=item.strip()))
            return notes

        synthesis_raw = pick("synthesis")
        synthesis: dict[str, list[str]] = {}
        if isinstance(synthesis_raw, dict):
            for key, value in synthesis_raw.items():
                synthesis[str(key)] = _coerce_list(value)

        return cls(
            topic=str(pick("topic", "subject") or "").strip(),
            foundational=sources("foundational", "seminal", "classic"),
            recent=sources("recent", "current", "latest"),
            competing=sources("competing", "alternative", "contrasting"),
            gaps=_coerce_list(pick("gaps", "open_problems")),
            synthesis=synthesis,
            confidence=_coerce_confidence(pick("confidence")),
            recommendations=_coerce_list(pick("recommendations", "next_steps")),
        )

    def num_sources(self) -> int:
        """Total number of proposed sources across the three buckets."""
        return len(self.foundational) + len(self.recent) + len(self.competing)


__all__ = ["Confidence", "SourceNote", "ResearchBrief"]

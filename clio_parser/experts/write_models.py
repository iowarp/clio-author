"""Pydantic v2 schemas for paper writing: outline, plan, section structure.

The outline -> plan -> write -> revise taxonomy and field set mirror the writing
workflow in wtf-p:

    https://github.com/JimmyMa99/wtf-p  (MIT)

Only the *concepts* (a recursive section outline, a per-section plan with tasks /
claims / sources) are re-typed here as Pydantic models; no source code is copied.
:meth:`SectionPlan.from_loose_dict` and :meth:`PaperOutline.from_loose_dict` map a
loose / partial LLM dict onto these fields, coercing scalars to lists where the
schema expects a list and supplying defaults so a noisy response still validates.
The coercion idioms follow ``review_models.py``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


def _coerce_list(raw: Any) -> list[str]:
    """Coerce ``raw`` into a list of strings (wrapping a lone scalar).

    Mirrors :func:`clio_parser.experts.review_models._coerce_list`.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw if str(item).strip()]
    return [str(raw)]


def _coerce_int_or_none(raw: Any) -> int | None:
    """Best-effort parse ``raw`` to an int, or ``None`` when absent/unparseable."""
    if raw is None:
        return None
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None


class SectionOutline(BaseModel):
    """A node in a recursive paper outline (a section and its subsections)."""

    title: str
    section_path: str = ""
    goal: str = ""
    word_budget: int | None = None
    citation_hints: list[str] = Field(default_factory=list)
    figure_refs: list[str] = Field(default_factory=list)
    subsections: list[SectionOutline] = Field(default_factory=list)

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any]) -> SectionOutline:
        """Build a :class:`SectionOutline` from a loose / partial dict.

        Accepts common key spellings, coerces list fields, recurses into
        ``subsections``, and supplies defaults for missing fields. Never raises
        on malformed input.
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

        sub_raw = pick("subsections", "children", "sections")
        subsections: list[SectionOutline] = []
        if isinstance(sub_raw, (list, tuple)):
            for item in sub_raw:
                if isinstance(item, SectionOutline):
                    subsections.append(item)
                elif isinstance(item, dict):
                    subsections.append(cls.from_loose_dict(item))

        return cls(
            title=str(pick("title", "name") or ""),
            section_path=str(pick("section_path", "path") or ""),
            goal=str(pick("goal", "objective", "purpose") or ""),
            word_budget=_coerce_int_or_none(pick("word_budget", "words", "budget")),
            citation_hints=_coerce_list(pick("citation_hints", "citations", "cite")),
            figure_refs=_coerce_list(pick("figure_refs", "figures", "figure")),
            subsections=subsections,
        )


class PaperOutline(BaseModel):
    """A whole-paper outline: a title, a vision, and top-level sections."""

    title: str
    vision: str = ""
    sections: list[SectionOutline] = Field(default_factory=list)

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any]) -> PaperOutline:
        """Build a :class:`PaperOutline` from a loose / partial dict. Never raises."""
        norm: dict[str, Any] = {}
        for key, value in raw.items():
            slug = str(key).strip().lower().replace(" ", "_")
            norm[slug] = value

        def pick(*names: str) -> Any:
            for name in names:
                if name in norm:
                    return norm[name]
            return None

        sections_raw = pick("sections", "outline", "children")
        sections: list[SectionOutline] = []
        if isinstance(sections_raw, (list, tuple)):
            for item in sections_raw:
                if isinstance(item, SectionOutline):
                    sections.append(item)
                elif isinstance(item, dict):
                    sections.append(SectionOutline.from_loose_dict(item))

        return cls(
            title=str(pick("title", "name") or ""),
            vision=str(pick("vision", "thesis", "abstract") or ""),
            sections=sections,
        )


class SectionPlan(BaseModel):
    """A per-section writing plan: the outline node plus tasks/claims/sources."""

    outline: SectionOutline
    tasks: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    @classmethod
    def from_loose_dict(cls, raw: dict[str, Any]) -> SectionPlan:
        """Build a :class:`SectionPlan` from a loose / partial dict. Never raises.

        The outline may be nested under ``outline``/``section`` or, failing that,
        the whole dict is treated as the outline node itself.
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

        outline_raw = pick("outline", "section")
        if isinstance(outline_raw, SectionOutline):
            outline = outline_raw
        elif isinstance(outline_raw, dict):
            outline = SectionOutline.from_loose_dict(outline_raw)
        else:
            outline = SectionOutline.from_loose_dict(raw)

        return cls(
            outline=outline,
            tasks=_coerce_list(pick("tasks", "steps")),
            claims=_coerce_list(pick("claims", "arguments")),
            sources=_coerce_list(pick("sources", "references", "materials")),
        )


# Resolve the forward reference in ``SectionOutline.subsections``.
SectionOutline.model_rebuild()


__all__ = ["SectionOutline", "PaperOutline", "SectionPlan"]

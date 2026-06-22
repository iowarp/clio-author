"""Tests for the writing schemas (outline / plan, loose-dict coercion)."""

from __future__ import annotations

from clio_author.experts.write_models import PaperOutline, SectionOutline, SectionPlan


def test_section_outline_recursive_subsections() -> None:
    outline = SectionOutline(
        title="Methods",
        section_path="Methods",
        subsections=[SectionOutline(title="Setup", section_path="Methods > Setup")],
    )
    assert outline.subsections[0].title == "Setup"


def test_section_outline_from_loose_dict_coerces_and_recurses() -> None:
    raw = {
        "Title": "Methods",
        "path": "Methods",
        "goal": "describe the approach",
        "Words": "350",
        "citations": "smith2020",
        "figure": ["fig:arch"],
        "research_needed": "yes",
        "research_topics": "fast attention",
        "children": [{"title": "Setup", "citations": ["a", "b"]}],
    }
    outline = SectionOutline.from_loose_dict(raw)

    assert outline.title == "Methods"
    assert outline.section_path == "Methods"
    assert outline.goal == "describe the approach"
    assert outline.word_budget == 350
    assert outline.citation_hints == ["smith2020"]
    assert outline.figure_refs == ["fig:arch"]
    assert outline.research_needed is True
    assert outline.research_topics == ["fast attention"]
    assert outline.subsections[0].title == "Setup"
    assert outline.subsections[0].citation_hints == ["a", "b"]


def test_section_outline_research_fields_default_false() -> None:
    outline = SectionOutline.from_loose_dict({"title": "Intro"})
    assert outline.research_needed is False
    assert outline.research_topics == []


def test_section_outline_from_loose_dict_defaults() -> None:
    outline = SectionOutline.from_loose_dict({})
    assert outline.title == ""
    assert outline.word_budget is None
    assert outline.citation_hints == []
    assert outline.subsections == []


def test_paper_outline_from_loose_dict() -> None:
    raw = {
        "title": "A Paper",
        "thesis": "X improves Y",
        "sections": [{"title": "Intro"}, {"title": "Methods"}],
    }
    outline = PaperOutline.from_loose_dict(raw)
    assert outline.title == "A Paper"
    assert outline.vision == "X improves Y"
    assert [s.title for s in outline.sections] == ["Intro", "Methods"]


def test_section_plan_from_loose_dict_nested_outline() -> None:
    raw = {
        "outline": {"title": "Results", "goal": "report findings"},
        "tasks": ["draft table", "summarise"],
        "claims": "X beats Y",
        "sources": ["block:1"],
    }
    plan = SectionPlan.from_loose_dict(raw)
    assert plan.outline.title == "Results"
    assert plan.tasks == ["draft table", "summarise"]
    assert plan.claims == ["X beats Y"]
    assert plan.sources == ["block:1"]


def test_section_plan_from_loose_dict_flat_treated_as_outline() -> None:
    plan = SectionPlan.from_loose_dict({"title": "Intro", "goal": "motivate"})
    assert plan.outline.title == "Intro"
    assert plan.outline.goal == "motivate"
    assert plan.tasks == []

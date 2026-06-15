"""Hermetic tests for figure-agent Pydantic schemas (construction/coercion)."""

from __future__ import annotations

from clio_parser.experts.figure_models import (
    FigureArtifact,
    FigureDescription,
    PlotSpec,
)


def test_plotspec_defaults() -> None:
    spec = PlotSpec(intent="bar chart of accuracy by model")
    assert spec.kind == "plot"
    assert spec.data_hint == ""
    assert spec.aspect_ratio is None


def test_plotspec_from_loose_dict_coerces_kind_and_keys() -> None:
    spec = PlotSpec.from_loose_dict(
        {"Type": "diagram", "Goal": "system architecture", "Aspect": "16:9", "data": "n/a"}
    )
    assert spec.kind == "diagram"
    assert spec.intent == "system architecture"
    assert spec.aspect_ratio == "16:9"
    assert spec.data_hint == "n/a"


def test_plotspec_from_loose_dict_unknown_kind_falls_back_to_plot() -> None:
    spec = PlotSpec.from_loose_dict({"kind": "sketch", "intent": "x"})
    assert spec.kind == "plot"


def test_figure_description_missing_caption_is_none() -> None:
    desc = FigureDescription(figure_id=1, description="a plot")
    assert desc.caption is None


def test_figure_artifact_defaults() -> None:
    art = FigureArtifact(kind="plot", code="import matplotlib")
    assert art.code == "import matplotlib"
    assert art.image_path is None
    assert art.description is None

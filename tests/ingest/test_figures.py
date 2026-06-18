"""Hermetic tests for figure embedding at captions."""

from __future__ import annotations

from clio_author.ingest.postprocess.figures import (
    _build_figure_map,
    get_unembedded_figures,
    process_figures,
)


def test_build_figure_map_naming_variants() -> None:
    files = ["figure1.png", "fig_2.png", "Figure-3.png", "document_img_004.png"]
    fmap = _build_figure_map(files)
    assert fmap == {
        1: "figure1.png",
        2: "fig_2.png",
        3: "Figure-3.png",
        4: "document_img_004.png",
    }


def test_embed_at_caption_line_start() -> None:
    md = "Figure 1: System architecture."
    out = process_figures(md, ["figure1.png"])
    assert "![Figure 1](./img/figure1.png)" in out
    assert out.index("![Figure 1]") < out.index("Figure 1: System")


def test_mid_sentence_reference_not_embedded() -> None:
    md = "As shown in Fig. 1 the system scales."
    out = process_figures(md, ["figure1.png"])
    assert "![Figure 1]" not in out


def test_embed_is_idempotent() -> None:
    md = "Figure 1: Caption."
    once = process_figures(md, ["figure1.png"])
    twice = process_figures(once, ["figure1.png"])
    assert once == twice
    assert once.count("![Figure 1]") == 1


def test_unembedded_figures_reported() -> None:
    md = "Figure 1: Present.\n"
    out = process_figures(md, ["figure1.png", "figure2.png"])
    assert get_unembedded_figures(out, ["figure1.png", "figure2.png"]) == ["figure2.png"]

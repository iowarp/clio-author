# Adapted from the paper-to-md project (MIT, (c) 2025 Jaime Cernuda): https://github.com/JaimeCernuda/paper-to-md
"""Figure processing: embed extracted images directly above their captions.

Logo/badge filtering happens earlier during extraction (by image dimensions),
so every filename handed here is assumed to be a real figure. Embedding is
idempotent: a figure already present in the content is not embedded twice, and
each figure is embedded at most once.
"""

from __future__ import annotations

import re

# Filename -> figure-number patterns we understand, tried in order:
#   figure1.png / fig_1 / Figure-1   and   document_img_001.png
_FIGURE_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:figure|fig)[_-]?(\d+)", re.IGNORECASE),
    re.compile(r"_img[_-]?0*(\d+)", re.IGNORECASE),
)


def process_figures(content: str, image_files: list[str]) -> str:
    """Embed each available image above its caption line.

    Args:
        content: Markdown content.
        image_files: Available image filenames (e.g. ``["figure1.png"]``).

    Returns:
        Markdown with ``![Figure N](./img/<file>)`` inserted above captions.
    """
    if not image_files:
        return content

    figure_map = _build_figure_map(image_files)
    if not figure_map:
        return content

    return _embed_figures_at_captions(content, figure_map)


def _build_figure_map(image_files: list[str]) -> dict[int, str]:
    """Map figure numbers to filenames.

    Handles ``figure1.png``, ``fig_1.png``, ``Figure-1.png`` and
    ``document_img_001.png`` (zero-padded ``_img_NNN`` form). The first matching
    pattern wins; an earlier file keeps the slot if numbers collide.
    """
    figure_map: dict[int, str] = {}
    for filename in image_files:
        for pattern in _FIGURE_NAME_PATTERNS:
            match = pattern.search(filename)
            if match:
                num = int(match.group(1))
                figure_map.setdefault(num, filename)
                break
    return figure_map


def _embedded_figure_numbers(content: str) -> set[int]:
    """Figure numbers already embedded as ``![Figure N]`` in ``content``."""
    return {int(m.group(1)) for m in re.finditer(r"!\[Figure (\d+)\]", content)}


def _embed_figures_at_captions(content: str, figure_map: dict[int, str]) -> str:
    """Insert the image for each caption line, once per figure."""
    lines = content.split("\n")
    result: list[str] = []
    embedded: set[int] = _embedded_figure_numbers(content)

    for line in lines:
        # Match only at line start to avoid mid-sentence "As shown in Fig. 1...".
        caption_match = re.match(
            r"^\s*(?:\*\*)?Fig(?:ure)?\.?\s*(\d+)[.:\s]",
            line,
            re.IGNORECASE,
        )
        if caption_match:
            fig_num = int(caption_match.group(1))
            if fig_num in figure_map and fig_num not in embedded:
                result.append(f"![Figure {fig_num}](./img/{figure_map[fig_num]})")
                result.append("")
                embedded.add(fig_num)
        result.append(line)

    return "\n".join(result)


def get_unembedded_figures(content: str, image_files: list[str]) -> list[str]:
    """Return filenames that were never embedded (no matching caption found)."""
    figure_map = _build_figure_map(image_files)
    embedded = _embedded_figure_numbers(content)
    return [filename for num, filename in sorted(figure_map.items()) if num not in embedded]

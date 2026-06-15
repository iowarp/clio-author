"""Gated render test: `render_plot_code` actually produces a PNG (needs matplotlib).

Marked ``live`` (deselected by default) and skipped cleanly when matplotlib (the
optional ``viz`` extra) is not installed. This is the ONLY path that executes the
generated code -- in a subprocess with the ``Agg`` backend.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.live

_TINY_SCRIPT = (
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "fig, ax = plt.subplots()\n"
    "ax.plot([0, 1, 2], [0, 1, 4])\n"
    "fig.savefig('out.png')\n"
)


def test_render_plot_code_produces_png(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    from clio_parser.experts.figure_agent import render_plot_code

    out_path = tmp_path / "out.png"
    result = render_plot_code(_TINY_SCRIPT, out_path, timeout=30)

    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0

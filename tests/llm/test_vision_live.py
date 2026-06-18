"""Live Gemini vision test (gated).

Gated by the ``live`` marker and skipped unless ``GEMINI_API_KEY`` (or
``GOOGLE_API_KEY``) is set. Hits the real Gemini REST API, so it needs network;
it skips cleanly otherwise. Kept minimal: describe a tiny local PNG.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.live

# A 1x1 transparent PNG.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_describe_tiny_png_returns_text(tmp_path: Path) -> None:
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        pytest.skip("GEMINI_API_KEY/GOOGLE_API_KEY not set")

    from clio_author.llm.vision import GeminiVisionClient

    img = tmp_path / "tiny.png"
    img.write_bytes(_TINY_PNG)

    client = GeminiVisionClient()
    text = client.describe_image(str(img), "Describe this image in one sentence.")
    assert isinstance(text, str)
    assert text.strip()

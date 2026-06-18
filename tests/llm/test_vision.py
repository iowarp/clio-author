"""Hermetic tests for the optional Gemini vision path.

No network: these only exercise the resolver and the no-key error path. The
``describe_image`` / ``generate_image`` calls under test never reach urllib
because the missing-key guard raises :class:`VisionError` first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clio_author.llm.vision import (
    GeminiVisionClient,
    VisionError,
    resolve_vision_client,
)


def _clear_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def test_resolve_gemini_returns_client() -> None:
    client = resolve_vision_client("gemini")
    assert isinstance(client, GeminiVisionClient)


def test_resolve_off_and_none_return_none() -> None:
    assert resolve_vision_client("off") is None
    assert resolve_vision_client("none") is None
    assert resolve_vision_client("") is None
    assert resolve_vision_client(None) is None


def test_resolve_unknown_raises() -> None:
    with pytest.raises(ValueError):
        resolve_vision_client("midjourney")


def test_resolve_reads_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLIO_VISION_MODEL", "gemini-describe-x")
    monkeypatch.setenv("CLIO_IMAGE_MODEL", "gemini-image-x")
    client = resolve_vision_client("gemini")
    assert isinstance(client, GeminiVisionClient)
    assert client.describe_model == "gemini-describe-x"
    assert client.image_model == "gemini-image-x"


def test_describe_image_without_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_keys(monkeypatch)
    img = tmp_path / "fig.png"
    img.write_bytes(b"\x89PNG\r\n")
    client = GeminiVisionClient(api_key=None)
    with pytest.raises(VisionError):
        client.describe_image(str(img), "describe this")


def test_generate_image_without_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_keys(monkeypatch)
    client = GeminiVisionClient(api_key=None)
    with pytest.raises(VisionError):
        client.generate_image("a diagram", tmp_path / "out.png")

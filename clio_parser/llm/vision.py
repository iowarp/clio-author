"""Optional Gemini vision path (image understanding + generation), stdlib-only.

This adds PaperBanana's "true image" route as an optional capability for the
figure agent: looking at a real figure to describe it, and generating a real
diagram image from a text prompt. It is **off by default** and is never used by
the hermetic test suite.

The :class:`VisionClient` protocol is the seam the figure agent calls. The
concrete :class:`GeminiVisionClient` talks to the Gemini REST API using only the
standard library (:mod:`urllib.request` + :mod:`json` + :mod:`base64`), all
lazy-imported *inside* the methods so importing this module never performs I/O
and pulls no dependency. :func:`resolve_vision_client` mirrors
``resolve_llm`` / ``resolve_scholar_client``: a short spec string selects a
client, ``off`` / ``none`` / empty / ``None`` selects nothing.

The vision route is a behavior reference from PaperBanana / papervizagent
(https://github.com/JoshuaChou2018/papervizagent, Apache-2.0); no source code is
copied -- the Gemini REST calls are re-implemented here from the public API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "VisionClient",
    "VisionError",
    "GeminiVisionClient",
    "resolve_vision_client",
]

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_DESCRIBE_MODEL = "gemini-2.5-flash"
_DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"

# Image mime types by file suffix, for the inline_data part Gemini expects.
_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


class VisionError(RuntimeError):
    """Raised when a vision call cannot complete (no key, bad response, etc.).

    The figure agent catches this (and any other exception) per figure and falls
    back to its text/code path, so a vision failure never propagates.
    """


@runtime_checkable
class VisionClient(Protocol):
    """The seam the figure agent calls for real image understanding/generation."""

    def describe_image(self, image_path: str, prompt: str) -> str:
        """Look at the image at ``image_path`` and return a textual description."""
        ...

    def generate_image(self, prompt: str, out_path: Path) -> Path:
        """Generate an image from ``prompt``, write it to ``out_path``, return it."""
        ...


class GeminiVisionClient:
    """:class:`VisionClient` backed by the Gemini REST ``generateContent`` API.

    Uses only the standard library; ``urllib`` / ``json`` / ``base64`` are
    imported lazily inside the methods so importing this module is hermetic and
    performs no network I/O. The API key defaults to ``GEMINI_API_KEY`` (then
    ``GOOGLE_API_KEY``) from the environment.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        describe_model: str = _DEFAULT_DESCRIBE_MODEL,
        image_model: str = _DEFAULT_IMAGE_MODEL,
        timeout: int = 60,
    ) -> None:
        """Build a Gemini vision client.

        Args:
            api_key: Gemini API key; defaults to ``GEMINI_API_KEY`` or
                ``GOOGLE_API_KEY`` from the environment.
            describe_model: Model id for :meth:`describe_image`.
            image_model: Model id for :meth:`generate_image`.
            timeout: Per-request timeout in seconds.
        """
        self.api_key = (
            api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        )
        self.describe_model = describe_model
        self.image_model = image_model
        self.timeout = timeout

    # --- internals -----------------------------------------------------------
    def _require_key(self) -> str:
        if not self.api_key:
            raise VisionError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set; cannot call the Gemini vision API."
            )
        return self.api_key

    def _post(self, model: str, body: dict[str, object]) -> dict[str, object]:
        """POST ``body`` to ``model``'s ``generateContent`` and return parsed JSON."""
        import json
        import urllib.error
        import urllib.request

        key = self._require_key()
        url = f"{_GEMINI_BASE}/{model}:generateContent?key={key}"
        req = urllib.request.Request(  # noqa: S310 - https REST endpoint
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001 - best-effort error detail only
                detail = ""
            raise VisionError(f"Gemini API returned HTTP {exc.code} for {model}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise VisionError(f"Gemini API request to {model} failed: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            raise VisionError(f"Gemini API returned a malformed body for {model}") from exc
        if not isinstance(data, dict):
            raise VisionError(f"Gemini API returned an unexpected body for {model}")
        return data

    @staticmethod
    def _parts(data: dict[str, object]) -> list[dict[str, object]]:
        """Pull the first candidate's content parts out of a response body."""
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise VisionError("Gemini API response had no candidates")
        first = candidates[0]
        content = first.get("content") if isinstance(first, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list) or not parts:
            raise VisionError("Gemini API response had no content parts")
        return [p for p in parts if isinstance(p, dict)]

    # --- VisionClient --------------------------------------------------------
    def describe_image(self, image_path: str, prompt: str) -> str:
        """Look at ``image_path`` and return Gemini's textual description.

        Raises :class:`VisionError` if the key is unset, the file is unreadable,
        the response is non-200, or the body is malformed / has no text part.
        """
        import base64

        path = Path(image_path)
        suffix = path.suffix.lower()
        mime = _MIME_BY_SUFFIX.get(suffix, "image/png")
        try:
            image_bytes = path.read_bytes()
        except OSError as exc:
            raise VisionError(f"could not read image {image_path!r}: {exc}") from exc

        body: dict[str, object] = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ]
                }
            ]
        }
        data = self._post(self.describe_model, body)
        for part in self._parts(data):
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
        raise VisionError("Gemini API response had no text part")

    def generate_image(self, prompt: str, out_path: Path) -> Path:
        """Generate an image from ``prompt``, write it to ``out_path``, return it.

        Raises :class:`VisionError` if the key is unset, the response is non-200,
        the body is malformed, or no image part is returned.
        """
        import base64

        out_path = Path(out_path)
        body: dict[str, object] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        data = self._post(self.image_model, body)
        for part in self._parts(data):
            inline = part.get("inline_data") or part.get("inlineData")
            if isinstance(inline, dict):
                encoded = inline.get("data")
                if isinstance(encoded, str) and encoded:
                    try:
                        raw = base64.b64decode(encoded)
                    except (ValueError, TypeError) as exc:
                        raise VisionError("Gemini API returned undecodable image data") from exc
                    try:
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_bytes(raw)
                    except OSError as exc:
                        raise VisionError(
                            f"could not write generated image to {out_path!s}: {exc}"
                        ) from exc
                    return out_path
        raise VisionError("Gemini API response had no image part")


def resolve_vision_client(spec: str | None = None) -> VisionClient | None:
    """Resolve a :class:`VisionClient` from a short spec (e.g. ``CLIO_VISION``).

    ``gemini`` -> a :class:`GeminiVisionClient` (models overridable via
    ``CLIO_VISION_MODEL`` / ``CLIO_IMAGE_MODEL``); ``off`` / ``none`` / empty /
    ``None`` -> ``None`` (the figure agent stays on its hermetic text/code path).
    Construction performs no network I/O.
    """
    name = (spec or "off").strip().lower()
    if name in ("off", "none", "offline", "disabled", ""):
        return None
    if name in ("gemini", "google"):
        return GeminiVisionClient(
            describe_model=os.environ.get("CLIO_VISION_MODEL") or _DEFAULT_DESCRIBE_MODEL,
            image_model=os.environ.get("CLIO_IMAGE_MODEL") or _DEFAULT_IMAGE_MODEL,
        )
    raise ValueError(f"unknown CLIO_VISION={spec!r} (use one of: gemini, off)")

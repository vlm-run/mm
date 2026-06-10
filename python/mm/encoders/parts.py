"""Shared message-construction helpers for encoders.

Centralizes the provider-aware content-part builders so every encoder
module imports from one canonical location instead of reaching into
``mm.encoders.image`` internals.
"""

from __future__ import annotations

from typing import Any

from mm.encoders.base import Message


def openai_image_part(b64: str, mime: str) -> dict[str, Any]:
    """Build an OpenAI ``image_url`` content part."""
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}"},
    }


def gemini_image_part(b64: str, mime: str) -> dict[str, Any]:
    """Build a Gemini ``inline_data`` content part."""
    return {"inline_data": {"mime_type": mime, "data": b64}}


def image_part(b64: str, mime: str, provider: str) -> dict[str, Any]:
    """Build a provider-appropriate image content part.

    Args:
        b64: Base64-encoded image bytes.
        mime: MIME type string.
        provider: ``"openai"`` or ``"gemini"``.
    """
    if provider == "gemini":
        return gemini_image_part(b64, mime)
    return openai_image_part(b64, mime)


def to_message(parts: list[dict[str, Any]]) -> Message:
    """Wrap content parts in a complete Message dict."""
    return {"role": "user", "content": parts}

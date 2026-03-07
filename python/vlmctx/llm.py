"""LLM backend for L2 semantic understanding.

Supports any OpenAI-compatible API (Ollama, vLLM, OpenAI, etc.)
via --llm-base-url / --llm-api-key or environment variables.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path
from typing import Any


class LlmBackend:
    """Wraps any OpenAI-compatible API for L2 semantic operations."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("VLMCTX_LLM_BASE_URL")
            or "http://localhost:11434/v1"
        )
        self.api_key = api_key or os.environ.get("VLMCTX_LLM_API_KEY", "")
        self.model = model or os.environ.get("VLMCTX_LLM_MODEL", "llava")
        self.base_url = self.base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        """Check if an LLM backend is available."""
        return bool(self.base_url)

    def caption(self, image_path: Path) -> str:
        """Generate a caption for an image using the LLM."""
        image_data = image_path.read_bytes()
        b64 = base64.b64encode(image_data).decode()
        mime = _guess_image_mime(image_path)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image in detail."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ]

        return self._chat(messages)

    def describe(self, file_path: Path, content: str | None = None) -> str:
        """Generate a description of a file's content."""
        if content is None:
            content = file_path.read_text(errors="replace")[:4000]

        messages = [
            {
                "role": "user",
                "content": (
                    f"Describe the contents of this file ({file_path.name}):\n\n"
                    f"```\n{content}\n```"
                ),
            }
        ]

        return self._chat(messages)

    def _chat(self, messages: list[dict[str, Any]]) -> str:
        """Send a chat completion request to the OpenAI-compatible API."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 1024,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                msg = result["choices"][0]["message"]
                content = msg.get("content") or ""
                if not content.strip():
                    content = msg.get("reasoning") or msg.get("reasoning_content") or ""
                return content
        except Exception as e:
            return f"[LLM error: {e}]"


def _guess_image_mime(path: Path) -> str:
    """Guess MIME type for an image file."""
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
    }.get(ext, "image/png")

"""LLM backend for L2 semantic understanding.

Supports any OpenAI-compatible API (Ollama, vLLM, OpenAI, etc.).

Provider settings are resolved in order:
  CLI flags > env vars > ~/.vlmctx/config.toml [provider] > defaults

Auto-detects Ollama and uses its native API for structured JSON output
with thinking-enabled models (Qwen3-VL, etc).
"""

from __future__ import annotations

import base64
import json
import re
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
        from vlmctx.config import get_provider

        cfg = get_provider()
        self.base_url = (base_url or cfg.base_url).rstrip("/")
        self.api_key = api_key or cfg.api_key
        self.model = model or cfg.model

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    @property
    def _is_ollama(self) -> bool:
        return "11434" in self.base_url

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

        return self._chat_openai(messages)

    def describe(self, file_path: Path, content: str | None = None) -> str:
        """Generate a description of a file's content."""
        if content is None:
            content = file_path.read_text(errors="replace")[:4000]

        messages = [
            {
                "role": "user",
                "content": (
                    f"Describe the contents of this file ({file_path.name}):\n\n```\n{content}\n```"
                ),
            }
        ]

        return self._chat_openai(messages)

    def describe_video(
        self,
        mosaic_paths: list[Path],
        *,
        video_name: str = "",
        duration_s: float = 0,
    ) -> dict[str, Any]:
        """Analyze video mosaics and return a suggested filename + tags.

        Uses Ollama native API with format:json when available (reliable
        with thinking models like Qwen3-VL). Falls back to OpenAI API.

        Returns {"filename": "...", "tags": [...], "summary": "..."}.
        """
        images_b64 = [base64.b64encode(mp.read_bytes()).decode() for mp in mosaic_paths]

        dur_ctx = ""
        if duration_s > 0:
            mins, secs = divmod(duration_s, 60)
            dur_ctx = f" ({int(mins)}m{secs:.0f}s)"

        prompt = (
            f"What is this video mosaic{dur_ctx} about? "
            "Give a descriptive content-based filename (not the original), tags, summary."
        )

        if self._is_ollama:
            raw = self._ollama_chat(prompt, images_b64, json_mode=True)
        else:
            content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            for b64 in images_b64:
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    }
                )
            raw = self._chat_openai(
                [{"role": "user", "content": content_parts}],
                temperature=0.1,
                max_tokens=512,
                json_mode=True,
            )

        return _parse_video_json(raw)

    def _ollama_chat(
        self,
        prompt: str,
        images_b64: list[str] | None = None,
        *,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        timeout: int = 30,
    ) -> str:
        """Ollama native /api/chat with format:json and thinking support.

        Includes timeout-based retry: if the model's thinking phase
        exceeds the timeout, retries with a shorter token budget.
        """
        base = self.base_url.replace("/v1", "")
        url = f"{base}/api/chat"

        msg: dict[str, Any] = {"role": "user", "content": prompt}
        if images_b64:
            msg["images"] = images_b64

        for attempt_tokens in [max_tokens, max_tokens // 2]:
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": [msg],
                "stream": False,
                "options": {
                    "num_predict": attempt_tokens,
                    "temperature": temperature,
                },
            }
            if json_mode:
                payload["format"] = "json"

            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )

            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    result = json.loads(resp.read())
                    content = result.get("message", {}).get("content", "")
                    if content.strip():
                        return content
            except Exception:
                continue

        return ""

    def _chat_openai(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        """Standard OpenAI-compatible chat completions."""
        base = self.base_url
        if self._is_ollama and not base.endswith("/v1"):
            base = f"{base}/v1"
        url = f"{base}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
                msg = result["choices"][0]["message"]
                content = msg.get("content") or ""
                if not content.strip():
                    content = msg.get("reasoning") or msg.get("reasoning_content") or ""
                return content
        except Exception as e:
            return f"[LLM error: {e}]"


def _parse_video_json(raw: str) -> dict[str, Any]:
    """Extract and normalize {filename, tags, summary} from LLM response."""
    if not raw or raw.startswith("[LLM error"):
        return {"filename": "", "tags": [], "summary": raw}

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"filename": "", "tags": [], "summary": raw.strip()}

    filename = ""
    for key in ("filename", "name", "file_name", "title"):
        if key in data and isinstance(data[key], str):
            filename = data[key]
            break

    tags: list[str] = []
    for key in ("tags", "relevant_tags", "keywords"):
        if key in data and isinstance(data[key], list):
            tags = [str(t) for t in data[key]]
            break

    summary = ""
    for key in ("summary", "one_sentence_summary", "description"):
        if key in data and isinstance(data[key], str):
            summary = data[key]
            break

    filename = _to_kebab_case(filename)

    return {"filename": filename, "tags": tags, "summary": summary}


def _to_kebab_case(s: str) -> str:
    """Convert any string to kebab-case suitable for a filename."""
    s = re.sub(r"\d+m\d+s$", "", s)
    s = s.replace("_", " ")
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    s = re.sub(r"(?i)\bmosaic\b", "", s)
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s.strip())
    s = re.sub(r"-+", "-", s)
    return s.lower().strip("-")[:80]


def _guess_image_mime(path: Path) -> str:
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

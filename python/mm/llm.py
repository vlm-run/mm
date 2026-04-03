"""LLM backend for L2 semantic understanding.

Supports any OpenAI-compatible API (Ollama, vLLM, OpenAI, etc.)
via the official openai Python SDK.

Profile settings are resolved in order:
    CLI flags > env vars > active profile in ~/.config/mm/mm.toml > built-in defaults
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openai import OpenAI

if TYPE_CHECKING:
    from mm.config import Mode


@dataclass
class LlmUsage:
    """Token usage from a single LLM/VLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# Module-level usage tracker — updated by every _chat() call.
# Allows callers without access to the LlmBackend instance
# (e.g. bench command factories) to read token usage after _extract().
_last_global_usage = LlmUsage()


def get_last_usage() -> LlmUsage:
    """Return token usage from the most recent LLM/VLM call."""
    return _last_global_usage


class LlmBackend:
    """Wraps any OpenAI-compatible chat/completions API for L2 semantic operations."""

    last_usage: LlmUsage

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        from mm import __version__
        from mm.profile import get_profile

        profile = get_profile()
        resolved_base = (base_url or profile.base_url).rstrip("/")
        if not resolved_base.endswith("/v1"):
            resolved_base = f"{resolved_base}/v1"

        self.api_key = api_key or profile.api_key or "no-key"
        self.model = model or profile.model
        self.client = OpenAI(
            base_url=resolved_base,
            api_key=self.api_key,
            timeout=120.0,
            default_headers={"User-Agent": f"mm-ctx/{__version__}"},
        )
        self.last_usage = LlmUsage()

    @property
    def is_configured(self) -> bool:
        return bool(self.client.base_url)

    def caption(self, image_path: Path, *, detail: bool = False) -> str:
        """Generate a caption for an image."""
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        mime = _guess_image_mime(image_path)

        if detail:
            prompt = "Describe this image in about 80 words. Cover the main subject, setting, and notable details."
            max_tokens = 512
        else:
            prompt = "Describe this image in one sentence (max 20 words)."
            max_tokens = 128

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ]
        return self._chat(messages, max_tokens=max_tokens)

    def describe(self, file_path: Path, content: str | None = None, *, detail: bool = False) -> str:
        """Generate a description of a file's content."""
        if content is None:
            content = file_path.read_text(errors="replace")[:4000]

        if detail:
            prompt = (
                f"Summarize this file ({file_path.name}) in about 80 words:\n\n```\n{content}\n```"
            )
            max_tokens = 512
        else:
            prompt = f"Summarize this file ({file_path.name}) in one sentence (max 20 words):\n\n```\n{content}\n```"
            max_tokens = 128

        return self._chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)

    def describe_video(
        self,
        mosaic_paths: list[Path],
        *,
        video_name: str = "",
        duration_s: float = 0,
    ) -> dict[str, Any]:
        """Analyze video mosaics and return {filename, tags, summary}."""
        dur_ctx = ""
        if duration_s > 0:
            mins, secs = divmod(duration_s, 60)
            dur_ctx = f" ({int(mins)}m{secs:.0f}s)"

        prompt = (
            f"What is this video mosaic{dur_ctx} about? "
            "Give a descriptive content-based filename (not the original), tags, summary."
        )

        content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for mp in mosaic_paths:
            b64 = base64.b64encode(mp.read_bytes()).decode()
            content_parts.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            )

        raw = self._chat(
            [{"role": "user", "content": content_parts}],
            temperature=0.1,
            max_tokens=512,
            json_mode=True,
        )
        return _parse_video_json(raw)

    def _chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int = 128,
        json_mode: bool = False,
    ) -> str:
        """Single chat/completions call via the OpenAI SDK.

        Thinking models consume tokens for reasoning before producing
        the answer, so we request extra headroom (capped at 2048).
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": min(max_tokens * 8, 2048),
        }
        kwargs["temperature"] = temperature if temperature is not None else 0.1
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        extra_body: dict[str, Any] = {"think": False, "reasoning_effort": "none"}

        try:
            response = self.client.chat.completions.create(**kwargs, extra_body=extra_body)

            # Capture token usage (instance + global)
            if response.usage:
                global _last_global_usage
                usage = LlmUsage(
                    prompt_tokens=response.usage.prompt_tokens or 0,
                    completion_tokens=response.usage.completion_tokens or 0,
                    total_tokens=response.usage.total_tokens or 0,
                )
                self.last_usage = usage
                _last_global_usage = usage

            choice = response.choices[0].message
            content = (choice.content or "").strip()
            if content:
                return content
            reasoning = (
                getattr(choice, "reasoning", None)
                or getattr(choice, "reasoning_content", None)
                or ""
            )
            if isinstance(reasoning, str) and reasoning.strip():
                return _extract_answer_from_thinking(reasoning.strip())
            return ""
        except Exception as e:
            return f"[LLM error: {e}]"

    def caption_modal(self, image_path: Path, *, mode: Mode = "fast") -> str:
        """Generate a markdown image caption with mode-specific detail.

        Args:
            image_path: Path to image file.
            mode: "fast" (10 words + 5 tags) or "accurate" (200 words + 10 tags + objects).

        Returns:
            Markdown string with description, tags, and optionally objects.
        """
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        mime = _guess_image_mime(image_path)

        if mode == "accurate":
            prompt = (
                "Describe this image in detail (~200 words).\n"
                "Then list up to 10 keyword tags.\n"
                "Then list up to 10 identifiable objects, people, faces, or logos.\n\n"
                "Use this format:\n"
                "## Description\n<description>\n\n"
                "## Tags\n- tag1\n- tag2\n...\n\n"
                "## Objects\n- object1\n- object2\n..."
            )
            max_tokens = 1024
        else:
            prompt = (
                "Describe this image in 10 words or less.\n"
                "Then list exactly 5 keyword tags.\n\n"
                "Use this format:\n"
                "## Description\n<description>\n\n"
                "## Tags\n- tag1\n- tag2\n..."
            )
            max_tokens = 256

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ]
        return self._chat(messages, max_tokens=max_tokens)

    def analyze_video_visual(
        self,
        mosaic_paths: list[Path],
        *,
        video_name: str = "",
        duration_s: float = 0,
        mode: Mode = "fast",
    ) -> str:
        """Analyze video from visual mosaics only (no transcript).

        Pure vision call — faster because no transcript text in prompt.
        Transcript is concatenated separately in the output.

        Args:
            mosaic_paths: List of mosaic JPEG paths.
            video_name: Original video filename.
            duration_s: Video duration in seconds.
            mode: "fast" (concise) or "accurate" (detailed).

        Returns:
            Markdown string with summary, tags, and scenes.
        """
        dur_ctx = ""
        if duration_s > 0:
            mins, secs = divmod(duration_s, 60)
            dur_ctx = f" Duration: {int(mins)}m{secs:.0f}s."

        if mode == "accurate":
            prompt = (
                f"Analyze this video mosaic ({video_name}).{dur_ctx}\n\n"
                "Provide a detailed visual analysis (~200 words), up to 10 keyword tags, "
                "and describe each major scene or segment visible in the frames.\n\n"
                "Use this format:\n"
                "## Summary\n<detailed analysis>\n\n"
                "## Tags\n- tag1\n- tag2\n...\n\n"
                "## Scenes\n- Scene 1: <description>\n- Scene 2: <description>\n..."
            )
            max_tokens = 1536
        else:
            prompt = (
                f"Analyze this video mosaic ({video_name}).{dur_ctx}\n\n"
                "Provide a concise summary (~50 words), 5 keyword tags, "
                "and a brief scene list.\n\n"
                "Use this format:\n"
                "## Summary\n<summary>\n\n"
                "## Tags\n- tag1\n- tag2\n...\n\n"
                "## Scenes\n- Scene 1: <description>\n..."
            )
            max_tokens = 512

        content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for mp in mosaic_paths:
            b64 = base64.b64encode(mp.read_bytes()).decode()
            content_parts.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            )

        return self._chat(
            [{"role": "user", "content": content_parts}],
            max_tokens=max_tokens,
        )

    def summarize_transcript(
        self,
        transcript: str,
        *,
        mode: Mode = "fast",
        filename: str = "",
    ) -> str:
        """Summarize an audio transcript via LLM.

        Args:
            transcript: Whisper transcript text.
            mode: "fast" (concise) or "accurate" (detailed).
            filename: Original audio filename.

        Returns:
            Markdown string with summary, tags, and language.
        """
        max_chars = 4000 if mode == "fast" else 16000
        t = transcript[:max_chars]
        if len(transcript) > max_chars:
            t += "..."

        if mode == "accurate":
            prompt = (
                f"Analyze this audio transcript ({filename}):\n\n{t}\n\n"
                "Provide a detailed summary (~200 words), up to 10 keyword tags, "
                "and the detected language.\n\n"
                "Use this format:\n"
                "## Summary\n<detailed summary>\n\n"
                "## Tags\n- tag1\n- tag2\n...\n\n"
                "## Language\n<detected language>"
            )
            max_tokens = 1024
        else:
            prompt = (
                f"Summarize this audio transcript ({filename}):\n\n{t}\n\n"
                "Provide a concise summary (~50 words), 5 keyword tags, "
                "and the detected language.\n\n"
                "Use this format:\n"
                "## Summary\n<summary>\n\n"
                "## Tags\n- tag1\n- tag2\n...\n\n"
                "## Language\n<detected language>"
            )
            max_tokens = 256

        return self._chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )


def _extract_answer_from_thinking(thinking: str) -> str:
    """Best-effort extraction of the final answer from a thinking trace.

    Thinking models interleave reasoning with the answer. The actual
    answer is typically the last quoted sentence or the last paragraph.
    """
    quotes: list[str] = re.findall(r'"([^"]{10,})"', thinking)
    if quotes:
        return quotes[-1].strip()
    paragraphs = [p.strip() for p in thinking.split("\n\n") if p.strip()]
    if paragraphs:
        last = paragraphs[-1]
        last = re.sub(r"^(?:So|Answer|Result|Summary)[:\s]+", "", last, flags=re.IGNORECASE)
        return last.strip()
    return thinking.strip()


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

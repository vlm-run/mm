"""LLM backend for accurate-mode pipelines.

Supports any OpenAI-compatible API (Ollama, vLLM, OpenAI, etc.)
via the official openai Python SDK.

Profile settings are resolved in order:
    CLI flags > env vars > active profile in ~/.config/mm/mm.toml > built-in defaults

Public API:
    LlmBackend.generate(kind, mode, *, context, parts)          — template-driven
    LlmBackend.generate_chunked(kind, mode, *, context, chunks) — multi-chunk concat
    image_part(path, *, mime)                                    — build an image content part
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion

from mm.constants import BinaryFileKind
from mm.pipelines.schema import PipelineSpec


@dataclass
class LlmUsage:
    """Token usage from a single LLM/VLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LlmBackend:
    """Wraps any OpenAI-compatible chat/completions API for accurate-mode generate calls."""

    last_usage: LlmUsage

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        from mm import __version__
        from mm._logfire import configure_logfire
        from mm.profile import get_profile

        configure_logfire()
        profile = get_profile()
        resolved_base = (base_url or profile.base_url).rstrip("/")

        resolved_key = api_key or profile.api_key or None
        self.api_key = resolved_key or ""
        self.model = model or profile.model
        headers: dict[str, str] = {"User-Agent": f"mm-ctx/{__version__}"}
        if not resolved_key:
            headers["Authorization"] = ""
        self.client = OpenAI(
            base_url=resolved_base,
            api_key=resolved_key or "noop",
            timeout=120.0,
            default_headers=headers,
        )
        self.last_usage = LlmUsage()

    @property
    def is_configured(self) -> bool:
        return bool(self.client.base_url)

    def generate(
        self,
        kind: BinaryFileKind,
        mode: str = "fast",
        *,
        context: dict[str, Any] | None = None,
        parts: list[dict[str, Any]] | None = None,
        pipeline_spec: PipelineSpec | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> str:
        """Pipeline-driven MLLM generation.

        Args:
            kind: Media kind (image, video, audio, document).
            mode: Processing mode (fast, accurate).
            context: Template variables — {filename}, {duration_ctx},
                {content}, {transcript}, {word_count}, etc.
            parts: OpenAI-compatible content parts (image_url, text, etc.)
                to include alongside the prompt.
            pipeline_spec: Pre-loaded ``PipelineSpec`` (with overrides
                already applied).  When provided, ``load(kind, mode)``
                is skipped.
            extra_body: Provider-specific knobs forwarded to the OpenAI
                SDK's ``extra_body``. Deep-merged on top of any
                ``Generate.extra_body`` from the pipeline (call-site
                values win on conflicts). Use this for vlmrt's
                ``method``, ``method_params``, ``video_fps``, etc.

        Returns:
            Raw LLM response text.
        """
        from mm.pipelines import deep_merge, load, render_prompt, run_pyfunc

        ctx = context or {}
        tpl = pipeline_spec if pipeline_spec is not None else load(kind, mode)

        if tpl.generate is None:
            return ""

        prompt = render_prompt(tpl, ctx)
        content_parts: list[dict[str, Any]] = parts or []
        content_parts = run_pyfunc(tpl, content_parts, ctx)

        if content_parts:
            message_content: list[dict[str, Any]] | str = [
                {"type": "text", "text": prompt},
                *content_parts,
            ]
        else:
            message_content = prompt

        messages: list[dict[str, Any]] = [{"role": "user", "content": message_content}]

        merged_extra_body = deep_merge(tpl.generate.extra_body or {}, extra_body or {})

        return self._chat(
            messages,
            max_tokens=tpl.generate.max_tokens,
            temperature=tpl.generate.temperature,
            json_mode=tpl.generate.json_mode,
            think=tpl.generate.think,
            reasoning_effort=tpl.generate.reasoning_effort,
            extra_body=merged_extra_body or None,
        )

    def generate_chunked(
        self,
        kind: BinaryFileKind,
        mode: str = "fast",
        *,
        context: dict[str, Any] | None = None,
        chunks: list[list[dict[str, Any]]],
        separator: str = "\n\n---\n\n",
        on_chunk: Any | None = None,
        pipeline_spec: PipelineSpec | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> str:
        """Process multiple content chunks sequentially and concatenate results.

        When the pipeline uses ``json_mode``, chunk results are merged into
        a JSON array instead of being joined with a plain text separator.

        Args:
            kind: Media kind (image, video, audio, document).
            mode: Processing mode (fast, accurate).
            context: Template variables shared across all chunks.
            chunks: List of content-part lists, one per chunk.
            separator: String inserted between chunk results (text mode only).
            on_chunk: Optional callback ``(chunk_idx, total, result) -> None``
                called after each chunk completes.
            pipeline_spec: Pre-loaded ``PipelineSpec`` (with overrides
                already applied).

        Returns:
            Concatenated LLM responses (text mode) or JSON array (json_mode).
        """
        from mm.pipelines import load

        tpl = pipeline_spec if pipeline_spec is not None else load(kind, mode)
        is_json = tpl.generate is not None and tpl.generate.json_mode

        results: list[str] = []
        total = len(chunks)
        cumulative_usage = LlmUsage()

        for i, parts in enumerate(chunks):
            result = self.generate(
                kind,
                mode,
                context=context,
                parts=parts,
                pipeline_spec=pipeline_spec,
                extra_body=extra_body,
            )
            results.append(result)

            cumulative_usage.prompt_tokens += self.last_usage.prompt_tokens
            cumulative_usage.completion_tokens += self.last_usage.completion_tokens
            cumulative_usage.total_tokens += self.last_usage.total_tokens

            if on_chunk is not None:
                on_chunk(i, total, result)

        self.last_usage = cumulative_usage
        good = [r for r in results if r and not r.startswith("[LLM error")]

        if is_json and good:
            import json

            merged: list[Any] = []
            for r in good:
                try:
                    parsed = json.loads(r)
                    if isinstance(parsed, list):
                        merged.extend(parsed)
                    else:
                        merged.append(parsed)
                except json.JSONDecodeError:
                    merged.append(r)
            return json.dumps(merged)

        return separator.join(good)

    def _chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int = 128,
        json_mode: bool = False,
        think: bool = False,
        reasoning_effort: str = "none",
        extra_body: dict[str, Any] | None = None,
    ) -> str:
        """Single chat/completions call via the OpenAI SDK.

        ``extra_body`` is deep-merged with the built-in ``think`` /
        ``reasoning_effort`` keys (caller-supplied values win).
        """
        from mm.pipelines import deep_merge

        effective_max = min(max_tokens * 8, 16384) if think else max_tokens
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": effective_max,
        }
        kwargs["temperature"] = temperature if temperature is not None else 0.1
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        eb: dict[str, Any] = {}
        if think:
            eb["think"] = True
        if reasoning_effort != "none":
            eb["reasoning_effort"] = reasoning_effort
        if extra_body:
            eb = deep_merge(eb, extra_body)

        if eb:
            kwargs["extra_body"] = eb

        try:
            response: ChatCompletion = self.client.chat.completions.create(**kwargs)
            if response.usage:
                self.last_usage = LlmUsage(
                    prompt_tokens=response.usage.prompt_tokens or 0,
                    completion_tokens=response.usage.completion_tokens or 0,
                    total_tokens=response.usage.total_tokens or 0,
                )

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


def image_part(path: Path, *, mime: str | None = None) -> dict[str, Any]:
    """Build an OpenAI ``image_url`` content part from a file path."""
    b64 = base64.b64encode(path.read_bytes()).decode()
    if mime is None:
        from mm.constants import guess_mime

        mime = guess_mime(path.name, fallback="image/png")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def _extract_answer_from_thinking(thinking: str) -> str:
    """Best-effort extraction of the final answer from a thinking trace."""
    quotes: list[str] = re.findall(r'"([^"]{10,})"', thinking)
    if quotes:
        return quotes[-1].strip()
    paragraphs = [p.strip() for p in thinking.split("\n\n") if p.strip()]
    if paragraphs:
        last = paragraphs[-1]
        last = re.sub(r"^(?:So|Answer|Result|Summary)[:\s]+", "", last, flags=re.IGNORECASE)
        return last.strip()
    return thinking.strip()

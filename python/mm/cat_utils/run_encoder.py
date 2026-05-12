import time
from pathlib import Path
from typing import Any

from mm.cat_utils.base_utils import (
    CatOpts,
    RunResult,
    format_generate_verbose,
    make_llm_from_spec,
    spec_extra_body,
)
from mm.constants import BinaryFileKind
from mm.pipelines.schema import PipelineSpec


def _format_pipeline_tree(encode_info: str, generate_info: str | None = None) -> str:
    """Format pipeline steps as a tree structure."""
    encode_text = (
        encode_info.replace("[dim]", "").replace("[/dim]", "").replace("Encode: ", "encode: ")
    )

    if generate_info:
        generate_text = generate_info.replace("[dim]", "").replace("[/dim]", "")
        pipeline = f"pipeline\n  ├─ {encode_text}\n  └─ {generate_text}"
    else:
        pipeline = f"pipeline\n  └─ {encode_text}"
    return f"[dim]{pipeline}[/dim]"


def _format_encode_verbose(strategy: str | None, messages: list[dict], elapsed_ms: float) -> str:
    """Format verbose output for the encode step."""
    from mm.display import format_time

    if not strategy:
        strategy = "unknown"

    # Count part types
    text_count = 0
    image_count = 0
    total_parts = 0

    for msg in messages:
        content = msg.get("content", [])
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total_parts += 1
                    part_type = part.get("type", "unknown")
                    if part_type == "text":
                        text_count += 1
                    elif part_type == "image_url" or "inline_data" in part:
                        image_count += 1

    # Format part summary
    part_details = []
    if text_count > 0:
        part_details.append(f"{text_count} text" if text_count == 1 else f"{text_count} texts")
    if image_count > 0:
        part_details.append(f"{image_count} image" if image_count == 1 else f"{image_count} images")

    part_summary = ", ".join(part_details)
    encode_text = (
        f"Encode: {strategy} • {format_time(elapsed_ms)} → {total_parts} parts ({part_summary})"
    )

    return f"[dim]{encode_text}[/dim]"


def _extract_llm_parts(msg: dict) -> list[dict]:
    """Extract OpenAI-compatible content parts from a Message dict."""
    parts: list[dict] = []
    content = msg.get("content", [])
    if isinstance(content, list):
        for part in content:
            if "inline_data" in part:
                idata = part["inline_data"]
                mime = idata.get("mime_type", "")
                b64 = idata.get("data", "")
                if mime.startswith("video/"):
                    continue
                parts.append(
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                )
            else:
                parts.append(part)
    elif isinstance(content, str):
        parts.append({"type": "text", "text": content})
    return parts


def run_encoder(path: Path, kind: BinaryFileKind, spec: PipelineSpec, opts: CatOpts) -> RunResult:
    """Run a named encoder strategy and output JSON messages or pipe to LLM."""
    from mm.encoders import get as get_encoder

    assert spec.encode.strategy is not None
    t_encode = time.monotonic()
    strat = get_encoder(spec.encode.strategy)
    encode_kwargs: dict[str, Any] = dict(spec.encode.strategy_opts)
    if spec.encode.backend is not None:
        encode_kwargs.setdefault("backend", spec.encode.backend)
    if spec.encode.model is not None:
        encode_kwargs.setdefault("model", spec.encode.model)
    messages = list(strat.encode(path, **encode_kwargs))
    encode_elapsed = (time.monotonic() - t_encode) * 1000

    if spec.generate is None:
        text_parts: list[str] = []
        for msg in messages:
            content = msg.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text", "")
                        if text:
                            text_parts.append(text)
            elif isinstance(content, str):
                if content:
                    text_parts.append(content)

        result = "\n\n".join(text_parts) if text_parts else ""
        encode_output = _format_encode_verbose(spec.encode.strategy, messages, encode_elapsed)
        return RunResult(content=result, verbose_suffix=_format_pipeline_tree(encode_output))

    from mm.profile import get_active_profile_name

    t0 = time.monotonic()
    llm = make_llm_from_spec(spec)
    chunks: list[list[dict]] = []
    for msg in messages:
        parts = _extract_llm_parts(msg)
        if parts:
            chunks.append(parts)

    if not chunks:
        return RunResult(content="[No LLM-compatible content parts from encoder]")

    ctx = {"filename": path.name}
    extra = spec_extra_body(spec)
    if len(chunks) == 1:
        result = llm.generate(
            kind, opts.mode, context=ctx, parts=chunks[0], pipeline_spec=spec, extra_body=extra
        )
    else:
        result = llm.generate_chunked(
            kind, opts.mode, context=ctx, chunks=chunks, pipeline_spec=spec, extra_body=extra
        )

    elapsed = (time.monotonic() - t0) * 1000
    u = llm.last_usage

    encode_output = _format_encode_verbose(spec.encode.strategy, messages, encode_elapsed)
    profile_name = get_active_profile_name()
    generate_output = format_generate_verbose(
        profile_name, elapsed, u.prompt_tokens, u.completion_tokens
    )
    return RunResult(
        content=result,
        verbose_suffix=_format_pipeline_tree(encode_output, generate_output),
    )

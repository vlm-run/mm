import time
from pathlib import Path

from mm.cat_utils.base_utils import (
    CatOpts,
    RunResult,
    format_footer,
    format_generate_verbose,
    make_llm_from_spec,
    spec_extra_body,
)
from mm.cat_utils.extract_meta import extract_meta
from mm.cat_utils.run_encoder import run_encoder
from mm.pipelines.schema import PipelineSpec


def accurate_audio(path: Path, spec: PipelineSpec, opts: CatOpts) -> RunResult:
    """Audio extraction with transcription."""
    from mm.common.audio import transcribe_available, transcribe_file
    from mm.ffmpeg import ffmpeg_available

    if not ffmpeg_available():
        return RunResult(content=f"[ffmpeg not found — cannot process {path.name}]")

    if not transcribe_available():
        return RunResult(
            content=(
                "[no transcription backend available — "
                "the openai package is required for the default gateway backend; "
                "for local MLX: pip install mm-ctx[mlx]; "
                "for local GPU/CPU: pip install mm-ctx[gpu]]"
            )
        )

    if spec.encode.strategy:
        return run_encoder(path, "audio", spec, opts)

    if spec.generate is None:
        return RunResult(content=extract_meta(path, "audio"))

    timing: dict[str, float] = {}
    t_total = time.monotonic()

    akw = spec.encode.strategy_opts
    model: str | None = spec.encode.model or akw.get("model") or None
    audio_speed = akw.get("audio_speed") or 2.0
    beam_size = 5
    backend = spec.encode.backend or akw.get("backend")
    base_url: str | None = akw.get("base_url")
    api_key: str | None = akw.get("api_key")

    whisper_result = transcribe_file(
        path,
        model=model,
        audio_speed=audio_speed,
        beam_size=beam_size,
        backend=backend,
        base_url=base_url,
        api_key=api_key,
    )
    timing["audio_transcription_ms"] = whisper_result.elapsed_ms
    transcript = whisper_result.text

    if not transcript or transcript.startswith("["):
        return RunResult(content=transcript or "[No speech detected]")

    t_llm = time.monotonic()
    llm = make_llm_from_spec(spec)
    summary = llm.generate(
        "audio",
        "accurate",
        context={"filename": path.name, "transcript": transcript},
        pipeline_spec=spec,
        extra_body=spec_extra_body(spec),
    )
    timing["llm_call_ms"] = (time.monotonic() - t_llm) * 1000
    timing["total_ms"] = (time.monotonic() - t_total) * 1000
    u = llm.last_usage

    word_count = len(transcript.split())
    content = f"{summary}\n\n[Transcript: {word_count} words]"

    from mm.profile import get_active_profile_name

    profile_name = get_active_profile_name()
    generate_output = format_generate_verbose(
        profile_name, timing["total_ms"], u.prompt_tokens, u.completion_tokens
    )
    footer = format_footer(
        path, "accurate", timing["total_ms"], u.prompt_tokens, u.completion_tokens
    )
    suffix = "\n\n".join([generate_output, footer])

    return RunResult(content=content, verbose_suffix=suffix)

import time
from pathlib import Path

from mm.cat_utils.base_utils import CatOpts, RunResult, format_footer, format_generate_verbose
from mm.cat_utils.extract_meta import extract_local
from mm.cat_utils.run_encoder import run_encoder
from mm.pipelines.schema import PipelineSpec


def accurate_audio(path: Path, spec: PipelineSpec, opts: CatOpts) -> RunResult:
    """Audio extraction with transcription."""
    from mm.ffmpeg import extract_audio, ffmpeg_available
    from mm.whisper import transcribe, whisper_available

    if not ffmpeg_available():
        return RunResult(content=f"[ffmpeg not found — cannot process {path.name}]")

    if not whisper_available():
        return RunResult(
            content=(
                "[whisper not available — faster-whisper should be included in core mm install. "
                "For MLX on Apple Silicon: pip install mm-ctx[mlx]]"
            )
        )

    if spec.generate is None:
        return RunResult(content=extract_local(path, "audio"))

    # The hard-coded whisper+LLM fast path only implements `transcribe`.
    # Anything else (e.g. audio-gemini) must be routed through the
    # generic encoder runner so we only report stages that actually ran.
    _AUDIO_NATIVE = {"transcribe", "audio-transcribe"}
    if spec.encode.strategy and spec.encode.strategy not in _AUDIO_NATIVE:
        return run_encoder(path, "audio", spec, opts)

    timing: dict[str, float] = {}
    t_total = time.monotonic()

    akw = spec.encode.strategy_opts
    whisper_model = akw.get("whisper_model") or "medium"
    audio_speed = akw.get("audio_speed") or 1.0
    beam_size = 5

    t0 = time.monotonic()
    audio_result = extract_audio(path, speed=audio_speed)
    timing["audio_extraction_ms"] = (time.monotonic() - t0) * 1000

    whisper_result = transcribe(
        audio_result.path,
        model_size=whisper_model,
        beam_size=beam_size,
        audio_speed=audio_speed,
    )
    timing["audio_transcription_ms"] = whisper_result.elapsed_ms
    transcript = whisper_result.text

    try:
        audio_result.path.unlink(missing_ok=True)
    except Exception:
        pass

    if not transcript or transcript.startswith("["):
        return RunResult(content=transcript or "[No speech detected]")

    from mm.llm import LlmBackend

    t_llm = time.monotonic()
    llm = LlmBackend()
    summary = llm.generate(
        "audio",
        "accurate",
        context={"filename": path.name, "transcript": transcript},
        pipeline_spec=spec,
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

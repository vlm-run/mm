import time
from pathlib import Path
from typing import Any

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

_VIDEO_HEAVY_DURATION_S = 30 * 60
_VIDEO_HEAVY_SIZE_B = 500 * 1024 * 1024
_VIDEO_HEAVY_NUM_FRAMES = 64
_VIDEO_DEFAULT_NUM_FRAMES = 128


def _adaptive_num_frames(path: Path, duration: float, ekw: dict[str, Any]) -> int:
    """Adapt opts for long or large videos."""
    is_long = duration > _VIDEO_HEAVY_DURATION_S
    is_large = path.stat().st_size > _VIDEO_HEAVY_SIZE_B
    if not (is_long or is_large):
        return _VIDEO_DEFAULT_NUM_FRAMES

    from mm.display import console

    reasons: list[str] = []
    if is_long:
        reasons.append(f"duration {(duration / 60):.0f}min > 30min")
    if is_large:
        reasons.append(f"size {(path.stat().st_size / (1024 * 1024)):.0f}MB > 500MB")
    console.print(
        f"[dim]Video auto-tune ({', '.join(reasons)}): frames={_VIDEO_HEAVY_NUM_FRAMES}.[/dim]"
    )
    return _VIDEO_HEAVY_NUM_FRAMES


def _parse_tile(tile: str) -> tuple[int, int]:
    parts = tile.lower().split("x")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    n = int(parts[0])
    return n, n


def accurate_video(path: Path, spec: PipelineSpec, opts: CatOpts) -> RunResult:
    """Video extraction with mode-aware mosaic + whisper + LLM pipeline."""
    import shutil

    from mm.ffmpeg import (
        extract_audio,
        extract_frames_at_timestamps,
        extract_uniform_mosaics,
        ffmpeg_available,
        probe_duration,
        tile_frames_to_mosaics,
    )
    from mm.llm import image_part

    if not ffmpeg_available():
        return RunResult(content=f"[ffmpeg not found — cannot process {path.name}]")

    if spec.generate is None:
        return RunResult(content=extract_meta(path, "video"))

    # The hard-coded mosaic+whisper fast path only implements a fixed
    # set of strategies. Anything else (e.g. video-gemini, frame-sample)
    # must be routed through the generic encoder runner so we only
    # report stages that actually ran.
    _VIDEO_NATIVE = {"frames-transcript", "video-frames-transcript", "mosaic", "video-mosaic"}
    if spec.encode.strategy and spec.encode.strategy not in _VIDEO_NATIVE:
        return run_encoder(path, "video", spec, opts)

    timing: dict[str, float] = {}
    t_total = time.monotonic()

    duration = probe_duration(path)
    if duration <= 0:
        return RunResult(content=f"[Could not determine duration for {path.name}]")

    from concurrent.futures import Future, ThreadPoolExecutor

    ekw = dict(spec.encode.strategy_opts)
    tile_spec = ekw.get("mosaic_tile") or "4x4"
    tile_cols, tile_rows = _parse_tile(tile_spec)
    num_mosaics = ekw.get("mosaic_count") or 8
    num_frames = _adaptive_num_frames(path, duration, ekw)

    thumb_width = ekw.get("mosaic_image_width") or (1500 // tile_cols)

    use_scenes = True

    def _extract_visual_and_vlm() -> tuple[list[Path], str]:
        t0 = time.monotonic()
        if use_scenes:
            from mm.common.video.shot_detection import (
                detect_scenes,
                sample_scene_timestamps,
                sample_uniform_timestamps,
                scenedetect_available,
            )

            if scenedetect_available():
                t_scene = time.monotonic()
                scene_result = detect_scenes(path)
                timing["scene_detection_ms"] = (time.monotonic() - t_scene) * 1000
                if scene_result.scenes:
                    timestamps = sample_scene_timestamps(scene_result.scenes, num_frames)
                else:
                    timestamps = sample_uniform_timestamps(duration, num_frames)
            else:
                timestamps = sample_uniform_timestamps(duration, num_frames)

            frames = extract_frames_at_timestamps(
                path,
                timestamps,
                thumb_width=thumb_width,
                out_dir=opts.output_dir,
            )
            timing["frame_extraction_ms"] = (time.monotonic() - t0) * 1000

            t_tile = time.monotonic()
            mosaics = tile_frames_to_mosaics(
                frames,
                tile_cols=tile_cols,
                tile_rows=tile_rows,
                stem=path.stem,
                out_dir=opts.output_dir,
            )
            timing["mosaic_assembly_ms"] = (time.monotonic() - t_tile) * 1000
        else:
            result = extract_uniform_mosaics(
                path,
                out_dir=opts.output_dir,
                tile_cols=tile_cols,
                tile_rows=tile_rows,
                thumb_width=thumb_width,
                num_mosaics=num_mosaics,
            )
            mosaics = result.mosaic_paths
            timing["frame_extraction_ms"] = result.elapsed_ms

        if not mosaics:
            return mosaics, ""

        dur_ctx = ""
        if duration > 0:
            mins, secs = divmod(duration, 60)
            dur_ctx = f" Duration: {int(mins)}m{secs:.0f}s."

        t_vlm = time.monotonic()
        llm = make_llm_from_spec(spec)
        img_parts = [image_part(mp, mime="image/jpeg") for mp in mosaics]
        analysis = llm.generate(
            "video",
            "accurate",
            context={"filename": path.name, "duration_ctx": dur_ctx},
            parts=img_parts,
            pipeline_spec=spec,
            extra_body=spec_extra_body(spec),
        )
        timing["vlm_call_ms"] = (time.monotonic() - t_vlm) * 1000
        timing["vlm_prompt_tokens"] = llm.last_usage.prompt_tokens
        timing["vlm_completion_tokens"] = llm.last_usage.completion_tokens
        return mosaics, analysis

    def _extract_audio_transcript() -> str:
        if not ekw.get("transcribe"):
            return ""

        from mm.common.audio import transcribe_available

        if not transcribe_available():
            return ""

        model: str | None = ekw.get("audio_model") or ekw.get("model") or None
        audio_speed = ekw.get("audio_speed") or 1.0
        beam_size = 5
        backend: str | None = ekw.get("audio_backend") or ekw.get("backend") or None
        base_url: str | None = ekw.get("audio_base_url") or ekw.get("base_url") or None
        api_key: str | None = ekw.get("audio_api_key") or ekw.get("api_key") or None

        t_audio = time.monotonic()
        audio_result = extract_audio(path, speed=audio_speed)
        timing["audio_extraction_ms"] = (time.monotonic() - t_audio) * 1000

        from mm.common.audio import transcribe

        whisper_result = transcribe(
            audio_result.path,
            model=model,
            beam_size=beam_size,
            audio_speed=audio_speed,
            backend=backend,
            base_url=base_url,
            api_key=api_key,
        )
        timing["audio_transcription_ms"] = whisper_result.elapsed_ms

        try:
            audio_result.path.unlink(missing_ok=True)
        except Exception:
            pass
        return whisper_result.text

    with ThreadPoolExecutor(max_workers=2) as pool:
        visual_future: Future[tuple[list[Path], str]] = pool.submit(_extract_visual_and_vlm)
        audio_future: Future[str] = pool.submit(_extract_audio_transcript)
        mosaic_paths, analysis = visual_future.result()
        transcript = audio_future.result()

    if not mosaic_paths:
        return RunResult(content=f"[No frames extracted from {path.name}]")

    timing["total_ms"] = (time.monotonic() - t_total) * 1000

    if opts.output_dir is None:
        for mp in mosaic_paths:
            try:
                parent = mp.parent
                mp.unlink(missing_ok=True)
                if parent.name.startswith("mm_"):
                    shutil.rmtree(parent, ignore_errors=True)
            except Exception:
                pass

    out_parts: list[str] = [analysis]
    if transcript:
        word_count = len(transcript.split())
        out_parts.append(f"\n## Transcript ({word_count} words)\n{transcript}")

    token_keys = {k: v for k, v in timing.items() if "tokens" in k}
    prompt_tokens = int(token_keys.get("vlm_prompt_tokens", 0))
    completion_tokens = int(token_keys.get("vlm_completion_tokens", 0))

    from mm.profile import get_active_profile_name

    profile_name = get_active_profile_name()
    generate_output = format_generate_verbose(
        profile_name, timing["total_ms"], prompt_tokens, completion_tokens
    )
    footer = format_footer(path, "accurate", timing["total_ms"], prompt_tokens, completion_tokens)
    suffix = "\n\n".join([generate_output, footer])

    return RunResult(content="\n".join(out_parts), verbose_suffix=suffix)

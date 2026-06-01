from pathlib import Path

from mm.cat_utils.base_utils import (
    CatOpts,
    RunResult,
)
from mm.cat_utils.extract_meta import extract_meta
from mm.cat_utils.run_encoder import run_encoder
from mm.pipelines.schema import PipelineSpec


def accurate_audio(path: Path, spec: PipelineSpec, opts: CatOpts) -> RunResult:
    """Audio extraction with transcription."""
    from mm.common.audio import transcribe_available
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

    return RunResult(content=extract_meta(path, "audio"))

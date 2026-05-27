from pathlib import Path

from mm.cat_utils.base_utils import (
    CatOpts,
    RunResult,
)
from mm.cat_utils.extract_meta import extract_meta
from mm.cat_utils.run_encoder import run_encoder
from mm.pipelines.schema import PipelineSpec


def accurate_video(path: Path, spec: PipelineSpec, opts: CatOpts) -> RunResult:
    """Video extraction with mode-aware mosaic + whisper + LLM pipeline."""
    from mm.ffmpeg import ffmpeg_available

    if not ffmpeg_available():
        return RunResult(content=f"[ffmpeg not found — cannot process {path.name}]")

    if spec.encode.strategy:
        return run_encoder(path, "video", spec, opts)

    if spec.generate is None:
        return RunResult(content=extract_meta(path, "video"))

    from mm.encoders.auto_strategy import auto_strategy

    spec.encode.strategy = auto_strategy(path)
    return run_encoder(path, "video", spec, opts)

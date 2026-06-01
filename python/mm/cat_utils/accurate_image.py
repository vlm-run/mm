from pathlib import Path

from mm.cat_utils.base_utils import (
    CatOpts,
    RunResult,
)
from mm.pipelines.schema import PipelineSpec


def accurate_image(path: Path, spec: PipelineSpec, opts: CatOpts) -> RunResult:
    """Image extraction with mode-specific LLM prompts."""
    from mm.cat_utils.run_encoder import run_encoder

    return run_encoder(path, "image", spec, opts)

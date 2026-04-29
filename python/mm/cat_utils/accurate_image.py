import time
from pathlib import Path

from mm.cat_utils.base_utils import CatOpts, format_footer, format_generate_verbose
from mm.cat_utils.run_encoder import run_encoder
from mm.pipelines.schema import PipelineSpec


def accurate_image(path: Path, spec: PipelineSpec, opts: CatOpts) -> str:
    """Image extraction with mode-specific LLM prompts."""
    if spec.encode.strategy:
        return run_encoder(path, "image", spec, opts)

    from mm.llm import LlmBackend, image_part
    from mm.profile import get_active_profile_name

    t0 = time.monotonic()
    llm = LlmBackend()
    parts = [image_part(path)]
    content = llm.generate(
        "image",
        "accurate",
        context={"filename": path.name},
        parts=parts,
        pipeline_spec=spec,
    )
    elapsed = (time.monotonic() - t0) * 1000
    u = llm.last_usage

    profile_name = get_active_profile_name()
    generate_output = format_generate_verbose(
        profile_name, elapsed, u.prompt_tokens, u.completion_tokens
    )
    footer = format_footer(path, "accurate", elapsed, u.prompt_tokens, u.completion_tokens)
    suffix_parts = [generate_output]
    if footer:
        suffix_parts.append(footer)
    opts._verbose_suffix = "\n\n".join(suffix_parts)
    return content

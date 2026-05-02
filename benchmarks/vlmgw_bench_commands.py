"""Internal benchmark for `mm cat` override surfaces against the vlmgw gateway.

Run with::

    mm bench ~/data/mmbench-tiny --bench-file benchmarks/vlmgw_bench_commands.py --dry-run
    mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py -r 1 -w 0

Each ``BenchCommand`` exercises the full override path shipped in PR #106:
Typer parsing -> ``apply_overrides`` deep-merge -> cache key -> ``LlmBackend``
-> openai SDK ``extra_body``. Every row pins ``--profile vlmgw`` so the
gateway model (``qwen/qwen3.5-0.8b``) is reachable without further setup.

Groups
------
A. image-prompt        ``--prompt`` overrides on a single image
B. model-alias         ``--model`` vs ``--generate.model`` equivalence
C. image-extra-body    deep-merge ``--generate.extra-body`` (image_resolution)
D. video-frame-sampling vlmrt video knobs (video_fps + video_max_frames)
E. cache               cold (``--no-cache``) vs warm cache hit
F. unavailable         models not loaded on this gateway (404 round-trip cost)
G. validation          CLI-side rejection paths (bad / non-object JSON)

Files: drives commands against ``~/data/mmbench-tiny`` (bakery.mp4, dogs.jpg,
1-vqa-car.jpg, invoice.jpg). The ``requires_kind`` / ``smallest`` selection
matches what the runner already does for the built-in matrix.
"""

from __future__ import annotations

import json

from mm.commands.bench_commands import BenchCommand

PROFILE = "vlmgw"
MODEL = "qwen/qwen3.5-0.8b"

_CAT = f"mm --profile {PROFILE} cat"
_ACCURATE_NOCACHE = "--mode accurate --no-cache --format json"


def _eb(payload: dict) -> str:
    """Render a JSON object as a single-quoted shell argument for ``--generate.extra-body``."""
    return "'" + json.dumps(payload, separators=(",", ":")) + "'"


# ── A. Image VQA: --prompt threads through ────────────────────────────
_A_IMAGE_PROMPT: list[BenchCommand] = [
    BenchCommand(
        name="cat <image> --prompt 'caption'",
        group="A. image-prompt",
        cmd_template=(
            f"{_CAT} {{file}} {_ACCURATE_NOCACHE} --prompt 'Describe this image in one sentence.'"
        ),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
    ),
    BenchCommand(
        name="cat <image> --prompt 'identify vehicle'",
        group="A. image-prompt",
        cmd_template=(
            f"{_CAT} {{file}} {_ACCURATE_NOCACHE} "
            "--prompt 'What kind of vehicle is in this image? Answer in 8 words.'"
        ),
        requires_kind="image",
        skip_reason="no image files",
    ),
]

# ── B. --model vs --generate.model alias equivalence ──────────────────
_B_MODEL_ALIAS: list[BenchCommand] = [
    BenchCommand(
        name="cat <image> --model qwen3.5",
        group="B. model-alias",
        cmd_template=(
            f"{_CAT} {{file}} {_ACCURATE_NOCACHE} "
            f"--model {MODEL} --prompt 'Caption this in 6 words.'"
        ),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
    ),
    BenchCommand(
        name="cat <image> --generate.model qwen3.5",
        group="B. model-alias",
        cmd_template=(
            f"{_CAT} {{file}} {_ACCURATE_NOCACHE} "
            f"--generate.model {MODEL} --prompt 'Caption this in 6 words.'"
        ),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
    ),
]

# ── C. --generate.extra-body deep-merges into the SDK ─────────────────
_C_IMAGE_EXTRA_BODY: list[BenchCommand] = [
    BenchCommand(
        name=f"cat <image> extra_body image_resolution={res}",
        group="C. image-extra-body",
        cmd_template=(
            f"{_CAT} {{file}} {_ACCURATE_NOCACHE} "
            "--prompt 'Describe the vehicle in 1 sentence.' "
            f"--generate.extra-body {_eb({'image_resolution': res})}"
        ),
        requires_kind="image",
        skip_reason="no image files",
    )
    for res in ("low", "medium", "high")
]

# ── D. Video frame-sampling knobs ─────────────────────────────────────
_D_VIDEO_FRAME_SAMPLING: list[BenchCommand] = [
    BenchCommand(
        name=f"cat <video> fps={fps} max={max_frames}",
        group="D. video-frame-sampling",
        cmd_template=(
            f"{_CAT} {{file}} {_ACCURATE_NOCACHE} "
            "--prompt 'Summarize what happens in this video in two sentences.' "
            f"--generate.extra-body {_eb({'video_fps': fps, 'video_max_frames': max_frames})}"
        ),
        requires_kind="video",
        skip_reason="no video files",
    )
    for fps, max_frames in ((0.5, 4), (1.0, 8), (2.0, 16))
]

# ── E. Cache invalidation: cold vs warm (same args) ───────────────────
_E_CACHE: list[BenchCommand] = [
    BenchCommand(
        name="cat <document> cold (--no-cache)",
        group="E. cache",
        cmd_template=(
            f"{_CAT} {{file}} --mode accurate --no-cache --format json "
            "--prompt 'Summarize this document in one sentence.'"
        ),
        requires_kind="document",
        smallest=True,
        skip_reason="no document files",
    ),
    BenchCommand(
        name="cat <document> warm (cache hit)",
        group="E. cache",
        cmd_template=(
            f"{_CAT} {{file}} --mode accurate --format json "
            "--prompt 'Summarize this document in one sentence.'"
        ),
        requires_kind="document",
        smallest=True,
        skip_reason="no document files",
    ),
]

# ── F. Models unavailable on this gateway (round-trip 404 cost) ───────
_F_UNAVAILABLE: list[BenchCommand] = [
    BenchCommand(
        name="cat <image> --model florence-2-base-ft (404)",
        group="F. unavailable",
        cmd_template=(
            f"{_CAT} {{file}} {_ACCURATE_NOCACHE} "
            "--model florence-2-base-ft "
            f"--generate.extra-body {_eb({'method': 'ocr'})}"
        ),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
    ),
    BenchCommand(
        name="cat <image> --model moondream2 (404)",
        group="F. unavailable",
        cmd_template=(
            f"{_CAT} {{file}} {_ACCURATE_NOCACHE} "
            "--model moondream2 "
            f"--generate.extra-body {_eb({'method': 'caption', 'method_params': {'length': 'short'}})}"
        ),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
    ),
    BenchCommand(
        name="cat <image> --model paddleocr-v5 (404)",
        group="F. unavailable",
        cmd_template=(
            f"{_CAT} {{file}} {_ACCURATE_NOCACHE} "
            "--model paddleocr-v5 "
            f"--generate.extra-body {_eb({'method': 'ocr', 'method_params': {'lang': 'en'}})}"
        ),
        requires_kind="image",
        skip_reason="no image files",
    ),
]

# ── G. CLI validation regression guards ──────────────────────────────
# These rows exercise rejection paths (--generate.extra-body parser) and
# exit non-zero before the gateway is hit. The bench harness is exit-code
# agnostic so they time as fast process-startup-cost rows.
_G_VALIDATION: list[BenchCommand] = [
    BenchCommand(
        name="cat <image> --generate.extra-body '{not json}' (rejected)",
        group="G. validation",
        cmd_template=(f"{_CAT} {{file}} {_ACCURATE_NOCACHE} --generate.extra-body '{{not json}}'"),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
    ),
    BenchCommand(
        name="cat <image> --generate.extra-body '[1,2,3]' (rejected)",
        group="G. validation",
        cmd_template=(f"{_CAT} {{file}} {_ACCURATE_NOCACHE} --generate.extra-body '[1,2,3]'"),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
    ),
]


COMMANDS: list[BenchCommand] = (
    _A_IMAGE_PROMPT
    + _B_MODEL_ALIAS
    + _C_IMAGE_EXTRA_BODY
    + _D_VIDEO_FRAME_SAMPLING
    + _E_CACHE
    + _F_UNAVAILABLE
    + _G_VALIDATION
)

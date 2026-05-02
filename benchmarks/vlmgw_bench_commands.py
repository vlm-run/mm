"""Internal benchmark for the vlmgw model gateway via ``mm cat``.

Run with::

    mm bench ~/data/mmbench-tiny --bench-file benchmarks/vlmgw_bench_commands.py --dry-run
    mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py -r 1 -w 0

Each row pins ``mm --profile vlmgw cat`` and exercises the override path
shipped in PR #106: Typer parsing -> ``apply_overrides`` deep-merge ->
cache key -> ``LlmBackend`` -> openai SDK ``extra_body``. The matrix
below mirrors the internal ``BenchSpec`` list used by other vlmgw
tooling so this benchfile tracks changes there with minimal drift.

Coverage groups (in display order):

* ``noop``        gateway round-trip cost (smallest payload)
* ``florence2``   Florence-2 caption/ocr/od
* ``moondream``   Moondream2 caption/detect, video caption, +llm post-proc
* ``qwen``        Qwen3.5 text/image/multi-image/video
* ``rfdetr``      RF-DETR detection / segmentation
* ``vitpose``     ViTPose pose estimation
* ``sam3``        SAM3 prompt-segment / segment-by-box / video tracking
* ``dots-ocr``    DOTS-OCR layout/parse/ocr/grounding
* ``paddleocr``   PP-OCRv5 OCR / detection
* ``smolvlm``     SmolVLM-256M caption
* ``smolvlm2``    SmolVLM2-256M-video & 500M-video on image+video
* ``cache``       cold (``--no-cache``) vs warm cache hit (mm-cat infra guard)
* ``validation``  CLI-side ``--generate.extra-body`` rejection (mm-cat infra guard)

Notes on the translation:

* ``mm cat`` requires a file argument. Specs with ``image=False`` and
  ``video=False`` (text-only, e.g. ``noop``, ``qwen/text``) attach the
  smallest available image — vision-encode overhead is constant across
  those rows so trends remain interpretable.
* ``num_images > 1`` becomes ``mm cat <file1> <file2> ...`` (``batch=N``).
  Each file produces a separate request to the gateway, so the timing
  measures sequential multi-image throughput rather than a single-chat
  multi-image conversation.
* ``fps`` / ``max_frames`` / ``video_resolution`` are folded into
  ``--generate.extra-body`` as ``video_fps`` / ``video_max_frames`` /
  ``video_resolution`` keys, alongside any ``method`` / ``method_params``
  the spec declares (the deep-merge in ``apply_overrides`` handles the
  combination).
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from typing import Any

from mm.commands.bench_commands import BenchCommand

PROFILE = "vlmgw"
_CAT = f"mm --profile {PROFILE} cat"


# ── BenchSpec → BenchCommand translation ─────────────────────────────


@dataclass(frozen=True)
class BenchSpec:
    """Higher-level spec mirroring the internal vlmgw matrix shape.

    Translated to a ``BenchCommand`` by :func:`_to_command` below. Keeping
    the spec layer intentionally close to the source matrix means a paste
    from the upstream tool just works after running ``ruff format``.
    """

    model: str
    name: str
    prompt: str | None = None
    image: bool = False
    video: bool = False
    num_images: int = 1
    fps: float | None = None
    max_frames: int | None = None
    video_resolution: str | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)


def _to_command(spec: BenchSpec) -> BenchCommand:
    """Render a :class:`BenchSpec` into a runnable :class:`BenchCommand`."""
    # Pick {file} vs {files}; for text-only specs we fall back to the
    # smallest image since `mm cat` requires a file argument.
    if spec.video:
        requires, placeholder, batch = "video", "{file}", 0
    elif spec.image and spec.num_images > 1:
        requires, placeholder, batch = "image", "{files}", spec.num_images
    else:
        requires, placeholder, batch = "image", "{file}", 0

    # Merge spec.extra_body with translated video knobs. Fold in this order
    # so explicit spec.extra_body keys win over derived defaults.
    eb: dict[str, Any] = {}
    if spec.fps is not None:
        eb["video_fps"] = spec.fps
    if spec.max_frames is not None:
        eb["video_max_frames"] = spec.max_frames
    if spec.video_resolution is not None:
        eb["video_resolution"] = spec.video_resolution
    eb.update(spec.extra_body)

    parts: list[str] = [
        _CAT,
        placeholder,
        "--mode",
        "accurate",
        "--no-cache",
        "--format",
        "json",
        "--model",
        shlex.quote(spec.model),
    ]
    if spec.prompt is not None:
        parts += ["--prompt", shlex.quote(spec.prompt)]
    if eb:
        parts += [
            "--generate.extra-body",
            shlex.quote(json.dumps(eb, separators=(",", ":"))),
        ]

    group, _, display = spec.name.partition("/")
    display = display or group

    return BenchCommand(
        name=display,
        group=group,
        cmd_template=" ".join(parts),
        requires_kind=requires,
        batch=batch,
        smallest=True,
        skip_reason=f"no {requires} files",
    )


# ── Spec matrix (mirrors the internal vlmgw BenchSpec list) ──────────


SPECS: list[BenchSpec] = [
    # noop -- gateway round-trip cost only.
    BenchSpec("noop", "noop/ping", prompt="ping"),
    # Florence-2
    BenchSpec(
        "florence-2-base-ft",
        "florence2/caption",
        image=True,
        extra_body={"method": "caption"},
    ),
    BenchSpec("florence-2-base-ft", "florence2/ocr", image=True, extra_body={"method": "ocr"}),
    BenchSpec("florence-2-base-ft", "florence2/od", image=True, extra_body={"method": "od"}),
    # Moondream2
    BenchSpec("moondream2", "moondream/caption", image=True, extra_body={"method": "caption"}),
    BenchSpec(
        "moondream2",
        "moondream/detect",
        image=True,
        extra_body={"method": "detect", "method_params": {"object": "bench"}},
    ),
    # Moondream2 on video — 8 frames spread across the clip (fps=0.4 →
    # ~2.5 s per frame on a 20 s soccer-juggling clip) at 448x336 so the
    # video_resolution knob is exercised by default.
    BenchSpec(
        "moondream2",
        "moondream/video-caption",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        extra_body={"method": "caption"},
    ),
    # Qwen3.5 (text, image, multi-image, video)
    BenchSpec("qwen3.5-0.8b", "qwen/text", prompt="What is 2+2? Reply in one word."),
    BenchSpec(
        "qwen3.5-0.8b",
        "qwen/image",
        image=True,
        prompt="Describe this image briefly.",
    ),
    BenchSpec(
        "qwen3.5-0.8b",
        "qwen/multi-image",
        image=True,
        num_images=2,
        prompt="Compare these two images.",
    ),
    BenchSpec(
        "qwen3.5-0.8b",
        "qwen/video",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        prompt="Summarise what happens in this video in one sentence.",
    ),
    # RF-DETR detection
    BenchSpec("rfdetr-nano", "rfdetr/detect", image=True, extra_body={"method": "detect"}),
    # RF-DETR segmentation
    BenchSpec(
        "rfdetr-seg-nano",
        "rfdetr-seg/segment",
        image=True,
        extra_body={"method": "segment"},
    ),
    # ViTPose pose estimation
    BenchSpec("vitpose-s", "vitpose/pose", image=True, extra_body={"method": "pose"}),
    # SAM3 — promptable segmentation + video tracking
    BenchSpec(
        "sam3",
        "sam3/segment",
        image=True,
        extra_body={"method": "segment", "method_params": {"prompt": "soccer ball"}},
    ),
    BenchSpec(
        "sam3",
        "sam3/segment_box",
        image=True,
        extra_body={"method": "segment_box", "method_params": {"box": [50, 50, 400, 400]}},
    ),
    BenchSpec(
        "sam3",
        "sam3/track",
        video=True,
        fps=2.0,
        max_frames=30,
        extra_body={
            "method": "track",
            "method_params": {"prompt": "soccer ball", "skip": 1, "max_frames": 30},
        },
    ),
    # DOTS-OCR — document layout + OCR
    BenchSpec(
        "dots-ocr",
        "dots-ocr/parse_layout",
        image=True,
        extra_body={"method": "parse_layout"},
    ),
    BenchSpec(
        "dots-ocr",
        "dots-ocr/parse_layout_only",
        image=True,
        extra_body={"method": "parse_layout_only"},
    ),
    BenchSpec("dots-ocr", "dots-ocr/ocr", image=True, extra_body={"method": "ocr"}),
    BenchSpec(
        "dots-ocr",
        "dots-ocr/grounding_ocr",
        image=True,
        extra_body={"method": "grounding_ocr", "method_params": {"box": [120, 200, 900, 400]}},
    ),
    # PP-OCRv5 — scene text recognition
    BenchSpec("paddleocr-v5", "paddleocr/ocr", image=True, extra_body={"method": "ocr"}),
    BenchSpec("paddleocr-v5", "paddleocr/detect", image=True, extra_body={"method": "detect"}),
    # SmolVLM family (llama.cpp GGUF; only the preferred quantization is
    # measured — F16 variants exist in the manifest but are excluded).
    BenchSpec(
        "smolvlm-256m",
        "smolvlm/256m-caption",
        image=True,
        prompt="Describe this image briefly.",
    ),
    BenchSpec(
        "smolvlm2-256m-video",
        "smolvlm2/256m-image",
        image=True,
        prompt="What is in this image?",
    ),
    BenchSpec(
        "smolvlm2-256m-video",
        "smolvlm2/256m-video",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        prompt="Summarise the video in one sentence.",
    ),
    BenchSpec(
        "smolvlm2-500m-video",
        "smolvlm2/500m-image",
        image=True,
        prompt="Describe this image briefly.",
    ),
    BenchSpec(
        "smolvlm2-500m-video",
        "smolvlm2/500m-video",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        prompt="Summarise the video in one sentence.",
    ),
    # Moondream2 + LLM post-processing (cross-model pipeline via extra_body)
    BenchSpec(
        "moondream2",
        "moondream/caption+llm",
        image=True,
        extra_body={"method": "caption", "llm": "qwen3.5-0.8b"},
    ),
]


# ── Supplemental mm-cat infrastructure guards ────────────────────────


_INFRA_COMMANDS: list[BenchCommand] = [
    # cache: cold (--no-cache) vs warm hit on the same prompt+model+file.
    BenchCommand(
        name="cold (--no-cache)",
        group="cache",
        cmd_template=(
            f"{_CAT} {{file}} --mode accurate --no-cache --format json "
            "--prompt 'Summarize this document in one sentence.'"
        ),
        requires_kind="document",
        smallest=True,
        skip_reason="no document files",
    ),
    BenchCommand(
        name="warm (cache hit)",
        group="cache",
        cmd_template=(
            f"{_CAT} {{file}} --mode accurate --format json "
            "--prompt 'Summarize this document in one sentence.'"
        ),
        requires_kind="document",
        smallest=True,
        skip_reason="no document files",
    ),
    # validation: --generate.extra-body parser rejection paths. These exit
    # non-zero before the gateway is contacted; the harness is exit-code
    # agnostic so they time as fast process-startup-cost rows.
    BenchCommand(
        name="bad json: '{not json}'",
        group="validation",
        cmd_template=(
            f"{_CAT} {{file}} --mode accurate --no-cache --format json "
            "--generate.extra-body '{not json}'"
        ),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
    ),
    BenchCommand(
        name="non-object json: '[1,2,3]'",
        group="validation",
        cmd_template=(
            f"{_CAT} {{file}} --mode accurate --no-cache --format json "
            "--generate.extra-body '[1,2,3]'"
        ),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
    ),
]


COMMANDS: list[BenchCommand] = [_to_command(s) for s in SPECS] + _INFRA_COMMANDS

"""Internal benchmark for the vlmgw model gateway via ``mm cat``.

Run with::

    mm bench ~/data/mmbench-tiny --bench-file benchmarks/vlmgw_bench_commands.py --dry-run
    mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py -r 1 -w 0

Every row pins ``mm --profile vlmgw cat`` and exercises the override
path shipped in PR #106: Typer parsing -> ``apply_overrides`` deep-merge
-> cache key -> ``LlmBackend`` -> openai SDK ``extra_body``.

The matrix is organised into six groups, each surfaced as a ``Group``
column section in the bench table. ``model`` and ``extra_body`` are
declared via :attr:`BenchCommand.tags` so the renderer adds them as
extra columns automatically:

* ``model`` (29 rows) — every model × variant. ``model`` and
  ``extra_body`` tags carry the configuration so each row is
  self-describing in the table.
* ``image-res`` (3 rows) — ``image_resolution`` sweep on
  ``qwen3.5-0.8b``: low / medium / high.
* ``video-frames`` (3 rows) — ``video_fps`` × ``video_max_frames``
  sweep on ``qwen3.5-0.8b``.
* ``cache`` (2 rows) — cold (``--no-cache``) vs warm cache hit on
  the same prompt+model+file.
* ``404`` (3 rows) — guaranteed-unavailable model names to measure
  the gateway's failure round-trip cost.
* ``validation`` (2 rows) — CLI-side ``--generate.extra-body``
  rejection paths (bad / non-object JSON).

Translation notes:

* ``mm cat`` requires a file argument. Specs with neither ``image``
  nor ``video`` (text-only — ``noop``, ``qwen/text``) attach the
  smallest available image; vision-encode overhead is constant across
  those rows so trends remain interpretable.
* ``num_images > 1`` becomes ``mm cat <file1> <file2> ...``
  (``batch=N``). Each file produces a separate gateway request, so
  the timing measures sequential multi-image throughput rather than a
  single multi-image conversation.
* ``fps`` / ``max_frames`` / ``video_resolution`` are folded into
  ``--generate.extra-body`` as ``video_fps`` / ``video_max_frames`` /
  ``video_resolution`` keys, alongside any ``method`` /
  ``method_params`` the spec declares.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from typing import Any

from mm.commands.bench_commands import BenchCommand

PROFILE = "vlmgw"
QWEN = "qwen3.5-0.8b"
_CAT = f"mm --profile {PROFILE} cat"
_BASE_FLAGS = "--mode accurate --no-cache --format json"


# ── BenchSpec → BenchCommand translation ─────────────────────────────


@dataclass(frozen=True)
class BenchSpec:
    """Higher-level spec mirroring the internal vlmgw matrix shape.

    Translated to a ``BenchCommand`` by :func:`_to_command` below.
    Keeping this layer close to the upstream source matrix means a
    paste of the canonical spec list works after a ``ruff format``.

    The ``name`` is the variant identifier (e.g. ``florence2/caption``
    or ``qwen/multi-image``) shown in the ``Command`` column. The
    ``Group`` column is always ``"model"`` for spec-derived rows; the
    family is conveyed via the ``model`` tag instead.
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


def _eb_for(spec: BenchSpec) -> dict[str, Any]:
    """Compose the final ``extra_body`` dict from spec attributes."""
    eb: dict[str, Any] = {}
    if spec.fps is not None:
        eb["video_fps"] = spec.fps
    if spec.max_frames is not None:
        eb["video_max_frames"] = spec.max_frames
    if spec.video_resolution is not None:
        eb["video_resolution"] = spec.video_resolution
    eb.update(spec.extra_body)
    return eb


def _to_command(spec: BenchSpec) -> BenchCommand:
    """Render a :class:`BenchSpec` into a runnable :class:`BenchCommand`."""
    if spec.video:
        requires, placeholder, batch = "video", "{file}", 0
    elif spec.image and spec.num_images > 1:
        requires, placeholder, batch = "image", "{files}", spec.num_images
    else:
        requires, placeholder, batch = "image", "{file}", 0

    eb = _eb_for(spec)

    parts: list[str] = [
        _CAT,
        placeholder,
        _BASE_FLAGS,
        f"--model {shlex.quote(spec.model)}",
    ]
    if spec.prompt is not None:
        parts.append(f"--prompt {shlex.quote(spec.prompt)}")
    if eb:
        parts.append(f"--generate.extra-body {shlex.quote(json.dumps(eb, separators=(',', ':')))}")

    return BenchCommand(
        name=spec.name,
        group="model",
        cmd_template=" ".join(parts),
        requires_kind=requires,
        batch=batch,
        smallest=True,
        skip_reason=f"no {requires} files",
        tags={
            "model": spec.model,
            "extra_body": json.dumps(eb, separators=(",", ":")) if eb else "",
        },
    )


# ── Spec matrix (mirrors the internal vlmgw BenchSpec list) ──────────
# ALL 29 variants from the canonical list — covered exhaustively below.
# See the module docstring for grouping semantics.


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
    # Moondream2 -- image
    BenchSpec("moondream2", "moondream/caption", image=True, extra_body={"method": "caption"}),
    BenchSpec(
        "moondream2",
        "moondream/detect",
        image=True,
        extra_body={"method": "detect", "method_params": {"object": "bench"}},
    ),
    # Moondream2 -- 8 frames spread across the clip (fps=0.4 ~= 2.5s
    # per frame on a 20s soccer-juggling clip) at 448x336 so the
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
    BenchSpec(QWEN, "qwen/text", prompt="What is 2+2? Reply in one word."),
    BenchSpec(QWEN, "qwen/image", image=True, prompt="Describe this image briefly."),
    BenchSpec(
        QWEN,
        "qwen/multi-image",
        image=True,
        num_images=2,
        prompt="Compare these two images.",
    ),
    BenchSpec(
        QWEN,
        "qwen/video",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        prompt="Summarise what happens in this video in one sentence.",
    ),
    # RF-DETR detection / segmentation
    BenchSpec("rfdetr-nano", "rfdetr/detect", image=True, extra_body={"method": "detect"}),
    BenchSpec(
        "rfdetr-seg-nano",
        "rfdetr-seg/segment",
        image=True,
        extra_body={"method": "segment"},
    ),
    # ViTPose pose estimation
    BenchSpec("vitpose-s", "vitpose/pose", image=True, extra_body={"method": "pose"}),
    # SAM3 -- promptable segmentation + video tracking
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
    # DOTS-OCR -- document layout + OCR
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
    # PP-OCRv5 -- scene text recognition
    BenchSpec("paddleocr-v5", "paddleocr/ocr", image=True, extra_body={"method": "ocr"}),
    BenchSpec("paddleocr-v5", "paddleocr/detect", image=True, extra_body={"method": "detect"}),
    # SmolVLM family (llama.cpp GGUF; only the preferred quantization is
    # measured -- F16 variants exist in the manifest but are excluded).
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
        extra_body={"method": "caption", "llm": QWEN},
    ),
]


# ── image-res: image_resolution sweep on qwen3.5-0.8b ────────────────


_IMAGE_RES: list[BenchCommand] = [
    BenchCommand(
        name=f"image_resolution={res}",
        group="image-res",
        cmd_template=(
            f"{_CAT} {{file}} {_BASE_FLAGS} --model {QWEN} "
            "--prompt 'Describe the vehicle in 1 sentence.' "
            f'--generate.extra-body \'{{"image_resolution":"{res}"}}\''
        ),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
        tags={
            "model": QWEN,
            "extra_body": json.dumps({"image_resolution": res}, separators=(",", ":")),
        },
    )
    for res in ("low", "medium", "high")
]


# ── video-frames: fps × max_frames sweep on qwen3.5-0.8b ─────────────


_VIDEO_FRAMES: list[BenchCommand] = [
    BenchCommand(
        name=f"fps={fps} max={max_frames}",
        group="video-frames",
        cmd_template=(
            f"{_CAT} {{file}} {_BASE_FLAGS} --model {QWEN} "
            "--prompt 'Summarise what happens in this video in one sentence.' "
            f"--generate.extra-body {shlex.quote(json.dumps({'video_fps': fps, 'video_max_frames': max_frames}, separators=(',', ':')))}"
        ),
        requires_kind="video",
        skip_reason="no video files",
        tags={
            "model": QWEN,
            "extra_body": json.dumps(
                {"video_fps": fps, "video_max_frames": max_frames},
                separators=(",", ":"),
            ),
        },
    )
    for fps, max_frames in ((0.5, 4), (1.0, 8), (2.0, 16))
]


# ── cache: cold (--no-cache) vs warm hit ─────────────────────────────


_CACHE: list[BenchCommand] = [
    BenchCommand(
        name="cold (--no-cache)",
        group="cache",
        cmd_template=(
            f"{_CAT} {{file}} --mode accurate --no-cache --format json --model {QWEN} "
            "--prompt 'Summarize this document in one sentence.'"
        ),
        requires_kind="document",
        smallest=True,
        skip_reason="no document files",
        tags={"model": QWEN, "extra_body": ""},
    ),
    BenchCommand(
        name="warm (cache hit)",
        group="cache",
        cmd_template=(
            f"{_CAT} {{file}} --mode accurate --format json --model {QWEN} "
            "--prompt 'Summarize this document in one sentence.'"
        ),
        requires_kind="document",
        smallest=True,
        skip_reason="no document files",
        tags={"model": QWEN, "extra_body": ""},
    ),
]


# ── 404: guaranteed-unavailable model names ──────────────────────────
# These model names are intentionally bogus so the row reliably 404s
# regardless of which models are actually loaded on the gateway. The
# bench harness is exit-code agnostic; the row times the round-trip
# cost of a "model not found" failure.


_UNAVAILABLE: list[BenchCommand] = [
    BenchCommand(
        name=f"--model {fake}",
        group="404",
        cmd_template=(f"{_CAT} {{file}} {_BASE_FLAGS} --model {fake}"),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
        tags={"model": fake, "extra_body": ""},
    )
    for fake in ("nonexistent-v0", "florence-2-NONEXISTENT", "paddleocr-v999")
]


# ── validation: CLI-side --generate.extra-body rejection ─────────────
# These exit non-zero before the gateway is contacted. The bench harness
# is exit-code agnostic so they time as fast process-startup-cost rows
# and serve as regression guards on the override-parser.


_VALIDATION: list[BenchCommand] = [
    BenchCommand(
        name="bad json: '{not json}'",
        group="validation",
        cmd_template=(f"{_CAT} {{file}} {_BASE_FLAGS} --generate.extra-body '{{not json}}'"),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
        tags={"model": "(default)", "extra_body": "{not json}"},
    ),
    BenchCommand(
        name="non-object json: '[1,2,3]'",
        group="validation",
        cmd_template=(f"{_CAT} {{file}} {_BASE_FLAGS} --generate.extra-body '[1,2,3]'"),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
        tags={"model": "(default)", "extra_body": "[1,2,3]"},
    ),
]


COMMANDS: list[BenchCommand] = (
    [_to_command(s) for s in SPECS]
    + _IMAGE_RES
    + _VIDEO_FRAMES
    + _CACHE
    + _UNAVAILABLE
    + _VALIDATION
)

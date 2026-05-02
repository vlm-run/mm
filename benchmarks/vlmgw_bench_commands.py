"""Internal benchmark for the vlmgw model gateway via ``mm cat``.

Run with::

    mm bench ~/data/mmbench-tiny --bench-file benchmarks/vlmgw_bench_commands.py --dry-run
    mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py -r 1 -w 0

Every row pins ``mm --profile vlmgw cat`` and exercises the override
path shipped in PR #106: Typer parsing -> ``apply_overrides`` deep-merge
-> cache key -> ``LlmBackend`` -> openai SDK ``extra_body``.

Display contract
----------------

The table renders ``Group | Model | Command | <metrics...>``. The
``Command`` cell holds the **fully resolved** ``mm cat ...`` shell
invocation (with absolute file paths shortened to basenames), so each
row is self-describing -- ``--model``, ``--prompt``,
``--generate.extra-body`` and ``--encode.strategy_opts`` are inlined
in the cell rather than spread across separate columns. Only ``model``
is surfaced as its own dedicated column (via :attr:`BenchCommand.tags`),
because grouping by model is the most common slice and the model name
otherwise drowns in the longer flag soup.

Model names follow the ``<org>/<model-name>`` convention everywhere
(both in the displayed ``Model`` column and in the actual ``--model``
flag passed to the gateway). The vlmgw gateway is OpenAI-compatible
and accepts both bare and namespaced model names; using the namespaced
form keeps benchmark output unambiguous for cross-provider comparisons.

Group layout
------------

The matrix is organised into eight groups, surfaced as ``Group``
column section breaks in the bench table:

* ``noop`` (3 rows) -- gateway round-trip cost. ``ping`` measures
  the smallest possible payload (text prompt only, no image content);
  ``image-512`` / ``image-1024`` measure passthrough cost at two
  client-side encoder resolutions. Image resize happens via
  ``--encode.strategy_opts max_width=N`` (PIL/Rust encoder downsamples
  the bytes BEFORE upload), not via a server-side ``image_resolution``
  knob, so each row's network payload size is predictable and the
  measurement isolates encode-side cost from model-side cost.
* ``model`` (29 rows) -- every single-model variant from the
  upstream BenchSpec list. The ``Model`` tag carries the namespaced
  ``<org>/<model-name>`` so each row is self-describing.
* ``model+llm`` (1 row) -- cross-model pipelines (e.g.
  ``moondream/caption+llm``) where a vision model's output is
  post-processed by an LLM via ``extra_body.llm``. Any spec that
  declares an ``llm`` key in ``extra_body`` is routed here
  automatically so timing for compound pipelines is grouped
  separately from atomic model calls.
* ``image-res`` (3 rows) -- client-side image-resolution sweep on
  ``qwen/qwen3.5-0.8b``: 512 / 1024 / 1536 px. Same encoder mechanism
  as the ``noop/image-*`` rows so timing differences here isolate the
  model-side scaling cost from constant-cost encode overhead.
* ``video-frames`` (3 rows) -- ``video_fps`` x ``video_max_frames``
  sweep on ``qwen/qwen3.5-0.8b``.
* ``cache`` (2 rows) -- cold (``--no-cache``) vs warm cache hit on
  the same prompt+model+file.
* ``404`` (3 rows) -- guaranteed-unavailable model names to measure
  the gateway's failure round-trip cost.
* ``validation`` (2 rows) -- CLI-side ``--generate.extra-body``
  rejection paths (bad / non-object JSON).

Translation notes
-----------------

* ``mm cat`` requires a file argument. Specs with neither ``image``
  nor ``video`` (text-only -- ``noop``, ``qwen/text``) attach the
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
* ``encode_max_width`` (when set) maps to
  ``--encode.strategy_opts max_width=N`` -- a *client-side* encoder
  flag that downsamples the image with PIL/Rust before upload.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from typing import Any

from mm.commands.bench_commands import BenchCommand

PROFILE = "vlmgw"

# ── Canonical model names (<org>/<model-name>) ───────────────────────
# The vlmgw gateway is OpenAI-compatible and accepts namespaced model
# names. Hard-coded here -- we don't enumerate `/v1/models` at import
# time so the benchfile loads offline and produces a stable matrix.
NOOP = "vlm-run/noop"
FLORENCE2 = "microsoft/florence-2-base-ft"
MOONDREAM2 = "vikhyatk/moondream2"
QWEN = "qwen/qwen3.5-0.8b"
RFDETR = "roboflow/rfdetr-nano"
RFDETR_SEG = "roboflow/rfdetr-seg-nano"
VITPOSE = "usyd-community/vitpose-plus-small"
SAM3 = "facebook/sam3"
DOTS_OCR = "rednote-hilab/dots.ocr"
PADDLEOCR = "paddleocr/pp-ocrv5"
GLINER = "fastino/gliner2-multi-v1"
SMOLVLM_256M = "ggml-org/smolvlm-256m-instruct-gguf"
SMOLVLM2_256M_VIDEO = "ggml-org/smolvlm2-256m-video-instruct-gguf"
SMOLVLM2_500M_VIDEO = "ggml-org/smolvlm2-500m-video-instruct-gguf"

_CAT = f"mm --profile {PROFILE} cat"
_BASE_FLAGS = "--mode fast --no-cache --format json"


# ── BenchSpec → BenchCommand translation ─────────────────────────────


@dataclass(frozen=True)
class BenchSpec:
    """Higher-level spec mirroring the internal vlmgw matrix shape.

    Translated to a ``BenchCommand`` by :func:`_to_command` below.
    Keeping this layer close to the upstream source matrix means a
    paste of the canonical spec list works after a ``ruff format``.

    The ``name`` is the variant identifier (e.g. ``florence2/caption``
    or ``qwen/multi-image``) and is used as the ``--command`` filter
    key, NOT for display -- the rendered Command cell shows the full
    resolved ``mm cat ...`` shell invocation. By default spec rows
    land in ``group="model"``; specs declaring an ``llm`` key inside
    ``extra_body`` are routed to ``group="model+llm"`` (cross-model
    pipelines deserve their own timing bucket). Callers can also pin
    a custom group via :func:`_to_command`'s ``group`` argument
    (e.g. the ``noop`` round-trip rows). The model family is conveyed
    via the ``model`` tag column.

    ``encode_max_width`` (when set) is *client-side*: it surfaces as
    ``--encode.strategy_opts max_width=N`` and downsamples the image
    with PIL/Rust before upload. This is distinct from server-side
    ``extra_body.image_resolution`` knobs that some providers expose.
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
    encode_max_width: int | None = None
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


def _to_command(spec: BenchSpec, *, group: str | None = None) -> BenchCommand:
    """Render a :class:`BenchSpec` into a runnable :class:`BenchCommand`.

    ``group`` overrides the auto-derived label. By default we pick
    ``"model+llm"`` when ``extra_body`` declares an ``llm`` key (cross-
    model post-processing pipelines) and ``"model"`` otherwise. Callers
    building auxiliary spec lists (e.g. the ``noop`` round-trip rows)
    can pin a custom group such as ``"noop"``.
    """
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
    if spec.encode_max_width is not None:
        parts.append(f"--encode.strategy_opts max_width={spec.encode_max_width}")
    if eb:
        parts.append(f"--generate.extra-body {shlex.quote(json.dumps(eb, separators=(',', ':')))}")

    if group is None:
        # Default routing: cross-model pipelines (vision model + LLM
        # post-processor) get their own bucket so their timing isn't
        # mixed in with atomic single-model calls.
        group = "model+llm" if "llm" in eb else "model"

    return BenchCommand(
        name=spec.name,
        group=group,
        cmd_template=" ".join(parts),
        requires_kind=requires,
        batch=batch,
        smallest=True,
        skip_reason=f"no {requires} files",
        # Only ``model`` is surfaced as a dedicated column; everything
        # else (prompt, extra_body, encode flags) is inlined in the
        # resolved ``Command`` cell and filterable via ``--command``.
        tags={"model": spec.model},
    )


# ── noop: gateway round-trip cost ────────────────────────────────────
# Three variants: a text-only ping (smallest possible payload) and two
# image passthrough rows at distinct client-side encoder resolutions.
# The noop "model" on the gateway is a passthrough that returns
# immediately, so timing differences between these rows isolate the
# vision-encode pipeline (PIL resize + base64 + HTTP upload) from the
# model itself.


NOOP_SPECS: list[BenchSpec] = [
    BenchSpec(NOOP, "noop/ping", prompt="ping"),
    BenchSpec(NOOP, "noop/image-512", image=True, encode_max_width=512),
    BenchSpec(NOOP, "noop/image-1024", image=True, encode_max_width=1024),
]


# ── Model matrix (mirrors the internal vlmgw BenchSpec list) ─────────
# All 28 variants from the canonical list -- covered exhaustively
# below. The noop family lives in NOOP_SPECS above.


SPECS: list[BenchSpec] = [
    # Florence-2
    BenchSpec(
        FLORENCE2,
        "florence2/caption",
        image=True,
        extra_body={"method": "caption"},
    ),
    BenchSpec(FLORENCE2, "florence2/ocr", image=True, extra_body={"method": "ocr"}),
    BenchSpec(FLORENCE2, "florence2/od", image=True, extra_body={"method": "od"}),
    # Moondream2 -- image
    BenchSpec(MOONDREAM2, "moondream/caption", image=True, extra_body={"method": "caption"}),
    BenchSpec(
        MOONDREAM2,
        "moondream/detect",
        image=True,
        extra_body={"method": "detect", "method_params": {"object": "bench"}},
    ),
    # Moondream2 -- 8 frames spread across the clip (fps=0.4 ~= 2.5s
    # per frame on a 20s soccer-juggling clip) at 448x336 so the
    # video_resolution knob is exercised by default.
    BenchSpec(
        MOONDREAM2,
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
    BenchSpec(RFDETR, "rfdetr/detect", image=True, extra_body={"method": "detect"}),
    BenchSpec(
        RFDETR_SEG,
        "rfdetr-seg/segment",
        image=True,
        extra_body={"method": "segment"},
    ),
    # ViTPose pose estimation
    BenchSpec(VITPOSE, "vitpose/pose", image=True, extra_body={"method": "pose"}),
    # SAM3 -- promptable segmentation + video tracking
    BenchSpec(
        SAM3,
        "sam3/segment",
        image=True,
        extra_body={"method": "segment", "method_params": {"prompt": "soccer ball"}},
    ),
    BenchSpec(
        SAM3,
        "sam3/segment_box",
        image=True,
        extra_body={"method": "segment_box", "method_params": {"box": [50, 50, 400, 400]}},
    ),
    BenchSpec(
        SAM3,
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
        DOTS_OCR,
        "dots-ocr/parse_layout",
        image=True,
        extra_body={"method": "parse_layout"},
    ),
    BenchSpec(
        DOTS_OCR,
        "dots-ocr/parse_layout_only",
        image=True,
        extra_body={"method": "parse_layout_only"},
    ),
    BenchSpec(DOTS_OCR, "dots-ocr/ocr", image=True, extra_body={"method": "ocr"}),
    BenchSpec(
        DOTS_OCR,
        "dots-ocr/grounding_ocr",
        image=True,
        extra_body={"method": "grounding_ocr", "method_params": {"box": [120, 200, 900, 400]}},
    ),
    # PP-OCRv5 -- scene text recognition
    BenchSpec(PADDLEOCR, "paddleocr/ocr", image=True, extra_body={"method": "ocr"}),
    BenchSpec(PADDLEOCR, "paddleocr/detect", image=True, extra_body={"method": "detect"}),
    # GLiNER2 -- text-only NER / classification / JSON extraction.
    # ``mm cat`` requires a file argument so the smallest available
    # image is attached as a no-op carrier; the model ignores it.
    BenchSpec(
        GLINER,
        "gliner/extract_entities",
        prompt="Vlm Run is hiring engineers in San Francisco.",
        extra_body={"method": "extract_entities"},
    ),
    BenchSpec(
        GLINER,
        "gliner/classify_text",
        prompt="The fourth quarter earnings exceeded analyst expectations.",
        extra_body={"method": "classify_text"},
    ),
    # SmolVLM family (llama.cpp GGUF; only the preferred quantization is
    # measured -- F16 variants exist in the manifest but are excluded).
    BenchSpec(
        SMOLVLM_256M,
        "smolvlm/256m-caption",
        image=True,
        prompt="Describe this image briefly.",
    ),
    BenchSpec(
        SMOLVLM2_256M_VIDEO,
        "smolvlm2/256m-image",
        image=True,
        prompt="What is in this image?",
    ),
    BenchSpec(
        SMOLVLM2_256M_VIDEO,
        "smolvlm2/256m-video",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        prompt="Summarise the video in one sentence.",
    ),
    BenchSpec(
        SMOLVLM2_500M_VIDEO,
        "smolvlm2/500m-image",
        image=True,
        prompt="Describe this image briefly.",
    ),
    BenchSpec(
        SMOLVLM2_500M_VIDEO,
        "smolvlm2/500m-video",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        prompt="Summarise the video in one sentence.",
    ),
    # Moondream2 + LLM post-processing -- cross-model pipeline. Routed
    # to group="model+llm" by `_to_command` because extra_body declares
    # an `llm` key. The LLM post-processor is referenced by namespaced
    # name to mirror the convention used everywhere else in this file.
    BenchSpec(
        MOONDREAM2,
        "moondream/caption+llm",
        image=True,
        extra_body={"method": "caption", "llm": QWEN},
    ),
]


# ── image-res: client-side image-resolution sweep on qwen ────────────
# Same `--encode.strategy_opts max_width=N` mechanism as `noop/image-*`
# but with a real model on the other end so we can attribute timing
# delta to model-side scaling rather than constant-cost encode overhead.

_IMAGE_RES: list[BenchCommand] = [
    BenchCommand(
        name=f"qwen/image-{px}",
        group="image-res",
        cmd_template=(
            f"{_CAT} {{file}} {_BASE_FLAGS} --model {shlex.quote(QWEN)} "
            f"--prompt 'Describe the image in 1 sentence.' "
            f"--encode.strategy_opts max_width={px}"
        ),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
        tags={"model": QWEN},
    )
    for px in (512, 1024, 1536)
]


# ── video-frames: fps × max_frames sweep on qwen ─────────────────────


_VIDEO_FRAMES: list[BenchCommand] = [
    BenchCommand(
        name=f"qwen/video-fps={fps}-max={max_frames}",
        group="video-frames",
        cmd_template=(
            f"{_CAT} {{file}} {_BASE_FLAGS} --model {shlex.quote(QWEN)} "
            "--prompt 'Summarise what happens in this video in one sentence.' "
            f"--generate.extra-body {shlex.quote(json.dumps({'video_fps': fps, 'video_max_frames': max_frames}, separators=(',', ':')))}"
        ),
        requires_kind="video",
        skip_reason="no video files",
        tags={"model": QWEN},
    )
    for fps, max_frames in ((0.5, 4), (1.0, 8), (2.0, 16))
]


# ── cache: cold (--no-cache) vs warm hit ─────────────────────────────


_CACHE: list[BenchCommand] = [
    BenchCommand(
        name="cache/cold",
        group="cache",
        cmd_template=(
            f"{_CAT} {{file}} --mode fast --no-cache --format json "
            f"--model {shlex.quote(QWEN)} "
            "--prompt 'Summarize this document in one sentence.'"
        ),
        requires_kind="document",
        smallest=True,
        skip_reason="no document files",
        tags={"model": QWEN},
    ),
    BenchCommand(
        name="cache/warm",
        group="cache",
        cmd_template=(
            f"{_CAT} {{file}} --mode fast --format json "
            f"--model {shlex.quote(QWEN)} "
            "--prompt 'Summarize this document in one sentence.'"
        ),
        requires_kind="document",
        smallest=True,
        skip_reason="no document files",
        tags={"model": QWEN},
    ),
]


# ── 404: guaranteed-unavailable model names ──────────────────────────
# These model names are intentionally bogus so the row reliably 404s
# regardless of which models are actually loaded on the gateway. The
# bench harness is exit-code agnostic; the row times the round-trip
# cost of a "model not found" failure.


_UNAVAILABLE: list[BenchCommand] = [
    BenchCommand(
        name=f"404/{fake.split('/')[-1]}",
        group="404",
        cmd_template=(f"{_CAT} {{file}} {_BASE_FLAGS} --model {shlex.quote(fake)}"),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
        tags={"model": fake},
    )
    for fake in (
        "vlm-run/nonexistent-v0",
        "microsoft/florence-2-NONEXISTENT",
        "paddlepaddle/paddleocr-v999",
    )
]


# ── validation: CLI-side --generate.extra-body rejection ─────────────
# These exit non-zero before the gateway is contacted. The bench harness
# is exit-code agnostic so they time as fast process-startup-cost rows
# and serve as regression guards on the override-parser.


_VALIDATION: list[BenchCommand] = [
    BenchCommand(
        name="validation/bad-json",
        group="validation",
        cmd_template=(f"{_CAT} {{file}} {_BASE_FLAGS} --generate.extra-body '{{not json}}'"),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
        tags={"model": "(default)"},
    ),
    BenchCommand(
        name="validation/non-object-json",
        group="validation",
        cmd_template=(f"{_CAT} {{file}} {_BASE_FLAGS} --generate.extra-body '[1,2,3]'"),
        requires_kind="image",
        smallest=True,
        skip_reason="no image files",
        tags={"model": "(default)"},
    ),
]


COMMANDS: list[BenchCommand] = (
    [_to_command(s, group="noop") for s in NOOP_SPECS]
    + [_to_command(s) for s in SPECS]
    + _IMAGE_RES
    + _VIDEO_FRAMES
    + _CACHE
    + _UNAVAILABLE
    + _VALIDATION
)

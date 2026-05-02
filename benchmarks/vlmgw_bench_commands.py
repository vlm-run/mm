"""Internal benchmark for the vlmgw model gateway via ``mm cat``.

Run with::

    mm bench ~/data/mmbench-tiny --bench-file benchmarks/vlmgw_bench_commands.py --dry-run
    mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py -r 1 -w 0

Every row pins ``mm --profile vlmgw cat`` and exercises the override
path shipped in PR #106: Typer parsing -> ``apply_overrides`` deep-merge
-> cache key -> ``LlmBackend`` -> openai SDK ``extra_body``.

Display contract
----------------

The table renders
``Group | Model | Task | Base Command | Extra Args | <metrics>``.
The ``Base Command`` cell holds the **fully resolved** ``mm cat ...``
shell invocation (with absolute file paths shortened to ``<img>`` /
``<vid>`` / ``<file>`` placeholders), so each row is self-describing.
``--prompt``, ``--generate.extra-body`` and ``--encode.strategy_opts``
land in ``Extra Args``. ``model`` and ``task`` are surfaced as their
own dedicated columns (via :attr:`BenchCommand.tags`) because slicing
by either is the most common interrogation pattern -- ``--model
qwen/...`` for a single deployment, ``--task ocr`` for a capability
class across deployments.

Task taxonomy
-------------

Every row carries a ``task`` tag from the closed set ``cap`` /
``ocr`` / ``det`` / ``seg`` / ``llm`` / ``pose`` / ``track`` /
``noop``:

* ``cap``  -- captioning / description (image, video, multi-image,
  doc-summary).
* ``ocr``  -- text recognition + document layout (florence2/ocr,
  dots-ocr/*, paddleocr/*).
* ``det``  -- object / box detection (florence2/od, moondream/detect,
  rfdetr/detect).
* ``seg``  -- mask / region segmentation (rfdetr-seg/segment, sam3/
  segment{,_box}).
* ``llm``  -- text-only generation (qwen/text math Q&A, gliner/*
  NER+classify, cache/* document summarisation).
* ``pose`` -- keypoint estimation (vitpose/pose).
* ``track`` -- video object tracking (sam3/track).
* ``noop`` -- gateway round-trip with no real inference (vlm-run/
  noop passthrough).

The ``404/*`` and ``validation/*`` rows test infrastructure failure
paths rather than workloads, so they intentionally carry no ``task``
tag and stay invisible to ``--task`` filtering -- use ``--group 404``
/ ``--group validation`` to scope to those.

Model names follow the ``<org>/<model-name>`` convention everywhere
(both in the displayed ``Model`` column and in the actual ``--model``
flag passed to the gateway). The vlmgw gateway is OpenAI-compatible
and accepts both bare and namespaced model names; using the namespaced
form keeps benchmark output unambiguous for cross-provider comparisons.

Disabled rows
-------------

Specs whose upstream deployment is currently broken (sam3, dots-ocr,
paddleocr, gliner, smolvlm2-video, moondream/caption+llm,
moondream/caption+llm) carry ``disabled=True``. They render in the
table with ``skipped: disabled`` in the metrics column and full-row
dim styling, so the matrix coverage stays visible without polluting
timing data. Flip back to ``False`` once the deployment is healthy.

Pinned-file rows
----------------

OCR and pose specs override the harness's ``{file}`` placeholder by
hard-coding an absolute path to a domain-appropriate image: an
OCR-bearing scan for the OCR specs, and a tennis player for ViTPose.
The harness's bench-directory pre-scan is bypassed for these rows
(``requires_kind=None``), so the throughput cells render as ``-`` —
time metrics are accurate, but ``MB/s`` / ``bps`` are not, since the
external file isn't part of the bench dir's byte accounting.

Group layout
------------

The matrix is organised into eight groups, surfaced as ``Group``
column section breaks in the bench table:

* ``noop`` (3 rows, all disabled) -- gateway round-trip cost
  measurements. Disabled by default because the ``vlm-run/noop``
  passthrough model isn't currently deployed; flip back on once it
  lands.
* ``model`` (28 rows) -- every single-model variant from the
  upstream BenchSpec list. Includes ``qwen/multi-image``, which
  fires ``mm cat <file1> <file2>`` (two sequential single-image
  chats) -- not a true multi-image API call. Some rows are
  ``disabled=True`` (sam3/*, dots-ocr/*, paddleocr/*, gliner/*,
  smolvlm2-video, qwen/text) pending deployment fixes or because
  the test isn't representative.
* ``model+llm`` (1 row) -- cross-model pipelines (e.g.
  ``moondream/caption+llm``) where a vision model's output is
  post-processed by an LLM via ``extra_body.llm``. Currently
  disabled (Internal Server Error from the gateway).
* ``image-res`` (3 rows) -- client-side image-resolution sweep on
  ``qwen/qwen3.5-0.8b``: 512 / 1024 / 1536 px.
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
  nor ``video`` (text-only -- the disabled ``noop/ping`` and
  ``qwen/text`` rows, plus ``gliner/*``) attach the smallest
  available image; vision-encode overhead is constant across those
  rows so trends remain interpretable.
* ``num_images > 1`` translates to ``mm cat <file1> <file2>`` --
  ``mm cat`` iterates client-side and fires N independent gateway
  requests, so the timing reflects the sum of N sequential
  one-image chats rather than a single multi-image conversation.
  This matches how multi-file ``mm cat`` is normally invoked in
  the wild.
* ``fps`` / ``max_frames`` / ``video_resolution`` are folded into
  ``--generate.extra-body`` as ``video_fps`` / ``video_max_frames`` /
  ``video_resolution`` keys, alongside any ``method`` /
  ``method_params`` the spec declares.
* ``encode_max_width`` (when set) maps to
  ``--encode.strategy_opts max_width=N`` -- a *client-side* encoder
  flag that downsamples the image with PIL/Rust before upload.
* ``pinned_file`` (when set) replaces the harness's ``{file}``
  placeholder with an absolute path; the row's input is fixed
  rather than scanned from the bench directory.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
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

# ── Domain-appropriate pinned inputs (~/data/1-demo) ─────────────────
# OCR rows need an image with actual text; pose rows need a person in
# motion. The bench harness's own scan dir (``~/data/mmbench-tiny``)
# is curated for media-kind coverage, not domain content -- pinning
# keeps each row exercising what its model is meant to do, even if
# the row is currently disabled (so re-enabling later "just works").
_OCR_IMG = Path("~/data/1-demo/image-ocr.jpg").expanduser()
_POSE_IMG = Path("~/data/1-demo/2.1-detect-count-tennis.jpg").expanduser()


# ── BenchSpec → BenchCommand translation ─────────────────────────────


@dataclass(frozen=True)
class BenchSpec:
    """Higher-level spec mirroring the internal vlmgw matrix shape.

    Translated to a ``BenchCommand`` by :func:`_to_command` below.
    Keeping this layer close to the upstream source matrix means a
    paste of the canonical spec list works after a ``ruff format``.

    The ``name`` is the variant identifier (e.g. ``florence2/caption``
    or ``qwen/multi-image``) and is used as the ``--command`` filter
    key, NOT for display. By default spec rows land in
    ``group="model"``; specs declaring an ``llm`` key inside
    ``extra_body`` are routed to ``group="model+llm"``. Callers can
    also pin a custom group via :func:`_to_command`'s ``group``
    argument (e.g. the ``noop`` round-trip rows). The model family
    and task class are conveyed via the ``model`` / ``task`` tag
    columns; ``task`` is required at the spec level (closed taxonomy:
    ``cap`` / ``ocr`` / ``det`` / ``seg`` / ``llm`` / ``pose`` /
    ``track`` / ``noop``) so every row is filterable by capability.

    ``encode_max_width`` (when set) is *client-side*: it surfaces as
    ``--encode.strategy_opts max_width=N`` and downsamples the image
    with PIL/Rust before upload. This is distinct from server-side
    ``extra_body.image_resolution`` knobs that some providers expose.

    ``pinned_file`` (when set) hard-codes the row's input image path,
    bypassing the harness's bench-directory file scan. The ``{file}``
    placeholder is omitted from the resulting cmd_template. Used for
    OCR / pose specs that need domain-specific imagery rather than
    whatever happens to be in the bench dir.

    ``disabled`` (when True) flags the row as render-only: it appears
    in the table (dimmed, with ``skipped: disabled`` in the metrics
    column) but the harness never invokes its argv. Used to keep
    matrix coverage of variants whose upstream deployment is
    currently broken without polluting timing data.
    """

    model: str
    name: str
    task: str
    prompt: str | None = None
    image: bool = False
    video: bool = False
    num_images: int = 1
    fps: float | None = None
    max_frames: int | None = None
    video_resolution: str | None = None
    encode_max_width: int | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)
    pinned_file: Path | None = None
    disabled: bool = False


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
    model post-processing pipelines) and ``"model"`` otherwise.
    """
    if spec.pinned_file is not None:
        # Hard-coded path: bake into the template, no {file} placeholder
        # and no requires_kind. The harness's file scan / skip-logic /
        # byte accounting is bypassed; throughput cells render as ``-``
        # but the time metrics are accurate. The displayed Base Command
        # still shows ``<file>`` because ``_replace_paths`` falls back to
        # its legacy "any abs path -> placeholder" mode when the row's
        # ``data_file_paths`` is empty.
        path_token = shlex.quote(str(spec.pinned_file))
        requires: str | None = None
        placeholder = path_token
        batch = 0
    elif spec.video:
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
        smallest=requires is not None,
        skip_reason=f"no {requires} files" if requires else "not applicable",
        # ``model`` + ``task`` are surfaced as dedicated columns; the
        # rest of the row's variation (prompt, extra_body, encode
        # flags) is inlined in the resolved ``Command`` cell and
        # filterable via ``--command``.
        tags={"model": spec.model, "task": spec.task},
        disabled=spec.disabled,
    )


# ── noop: gateway round-trip cost (currently disabled) ───────────────
# Three variants: a text-only ping (smallest possible payload) and two
# image passthrough rows at distinct client-side encoder resolutions.
# All three are disabled because the ``vlm-run/noop`` passthrough
# model isn't currently deployed on the gateway -- the rows still
# show up in the matrix so re-enabling is a one-flag flip once the
# deployment is restored.


NOOP_SPECS: list[BenchSpec] = [
    BenchSpec(NOOP, "noop/ping", task="noop", prompt="ping", disabled=True),
    BenchSpec(NOOP, "noop/image-512", task="noop", image=True, encode_max_width=512, disabled=True),
    BenchSpec(
        NOOP, "noop/image-1024", task="noop", image=True, encode_max_width=1024, disabled=True
    ),
]


# ── Model matrix (mirrors the internal vlmgw BenchSpec list) ─────────
# 28 single-call variants here including ``qwen/multi-image`` (which
# is ``mm cat <file1> <file2>`` -- two sequential one-image chats,
# not a true multi-image API call). The noop family lives in
# NOOP_SPECS above and ``moondream/caption+llm`` lands in
# ``group="model+llm"`` automatically because its ``extra_body``
# declares an ``llm`` key.


SPECS: list[BenchSpec] = [
    # Florence-2 -- caption / OCR / object detection.
    BenchSpec(
        FLORENCE2,
        "florence2/caption",
        task="cap",
        image=True,
        extra_body={"method": "caption"},
    ),
    BenchSpec(
        FLORENCE2,
        "florence2/ocr",
        task="ocr",
        pinned_file=_OCR_IMG,
        extra_body={"method": "ocr"},
    ),
    BenchSpec(FLORENCE2, "florence2/od", task="det", image=True, extra_body={"method": "od"}),
    # Moondream2 -- image. Video support was removed in the gateway
    # (the server now rejects multi-frame requests with a
    # capability_violation), so no moondream/video-caption row.
    BenchSpec(
        MOONDREAM2, "moondream/caption", task="cap", image=True, extra_body={"method": "caption"}
    ),
    BenchSpec(
        MOONDREAM2,
        "moondream/detect",
        task="det",
        image=True,
        extra_body={"method": "detect", "method_params": {"object": "bench"}},
    ),
    # Qwen3.5 (text, image, video, multi-image). The multi-image row
    # uses ``num_images=2`` so it resolves to ``mm cat <f1> <f2>`` --
    # two sequential one-image chats, not a single multi-image API
    # call. ``qwen/text`` is disabled because the "What is 2+2?" prompt
    # isn't representative of any real usage pattern; the row stays for
    # reference.
    BenchSpec(
        QWEN,
        "qwen/text",
        task="llm",
        prompt="What is 2+2? Reply in one word.",
        disabled=True,
    ),
    BenchSpec(QWEN, "qwen/image", task="cap", image=True, prompt="Describe this image briefly."),
    BenchSpec(
        QWEN,
        "qwen/video",
        task="cap",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        prompt="Summarise what happens in this video in one sentence.",
    ),
    BenchSpec(
        QWEN,
        "qwen/multi-image",
        task="cap",
        image=True,
        num_images=2,
        prompt="Compare these two images.",
    ),
    # RF-DETR detection / segmentation
    BenchSpec(RFDETR, "rfdetr/detect", task="det", image=True, extra_body={"method": "detect"}),
    BenchSpec(
        RFDETR_SEG,
        "rfdetr-seg/segment",
        task="seg",
        image=True,
        extra_body={"method": "segment"},
    ),
    # ViTPose pose estimation -- pinned to a tennis player so the
    # pose model has actual keypoints to find rather than the bench
    # dir's default car photo.
    BenchSpec(
        VITPOSE,
        "vitpose/pose",
        task="pose",
        pinned_file=_POSE_IMG,
        extra_body={"method": "pose"},
    ),
    # SAM3 -- promptable segmentation + video tracking. All three
    # are disabled because the ``facebook/sam3`` deployment is
    # currently down (Deployment unavailable / multi-image rejection).
    BenchSpec(
        SAM3,
        "sam3/segment",
        task="seg",
        image=True,
        extra_body={"method": "segment", "method_params": {"prompt": "soccer ball"}},
        disabled=True,
    ),
    BenchSpec(
        SAM3,
        "sam3/segment_box",
        task="seg",
        image=True,
        extra_body={"method": "segment_box", "method_params": {"box": [50, 50, 400, 400]}},
        disabled=True,
    ),
    BenchSpec(
        SAM3,
        "sam3/track",
        task="track",
        video=True,
        fps=2.0,
        max_frames=30,
        extra_body={
            "method": "track",
            "method_params": {"prompt": "soccer ball", "skip": 1, "max_frames": 30},
        },
        disabled=True,
    ),
    # DOTS-OCR -- document layout + OCR. All four disabled because
    # ``rednote-hilab/dots.ocr`` deployment is currently down. Pinned
    # to an OCR-bearing image so re-enabling works correctly.
    BenchSpec(
        DOTS_OCR,
        "dots-ocr/parse_layout",
        task="ocr",
        pinned_file=_OCR_IMG,
        extra_body={"method": "parse_layout"},
        disabled=True,
    ),
    BenchSpec(
        DOTS_OCR,
        "dots-ocr/parse_layout_only",
        task="ocr",
        pinned_file=_OCR_IMG,
        extra_body={"method": "parse_layout_only"},
        disabled=True,
    ),
    BenchSpec(
        DOTS_OCR,
        "dots-ocr/ocr",
        task="ocr",
        pinned_file=_OCR_IMG,
        extra_body={"method": "ocr"},
        disabled=True,
    ),
    BenchSpec(
        DOTS_OCR,
        "dots-ocr/grounding_ocr",
        task="ocr",
        pinned_file=_OCR_IMG,
        extra_body={"method": "grounding_ocr", "method_params": {"box": [120, 200, 900, 400]}},
        disabled=True,
    ),
    # PP-OCRv5 -- scene text recognition. Both disabled (Internal
    # Server Error from the gateway). ``paddleocr/detect`` is text-
    # bounding-box detection within the OCR pipeline; tagged ``ocr``
    # rather than ``det`` so ``--task ocr`` returns the full OCR
    # family in one go.
    BenchSpec(
        PADDLEOCR,
        "paddleocr/ocr",
        task="ocr",
        pinned_file=_OCR_IMG,
        extra_body={"method": "ocr"},
        disabled=True,
    ),
    BenchSpec(
        PADDLEOCR,
        "paddleocr/detect",
        task="ocr",
        pinned_file=_OCR_IMG,
        extra_body={"method": "detect"},
        disabled=True,
    ),
    # GLiNER2 -- text-only NER / classification. Both disabled
    # because the gateway rejects images on text-only models, and
    # ``mm cat`` always attaches its file argument to the request
    # (no way to send pure text via ``mm cat``). Tagged ``llm``
    # because the workload is text-only structured generation; if
    # we ever re-classify NER as detection-of-text-spans, flip to
    # ``det``.
    BenchSpec(
        GLINER,
        "gliner/extract_entities",
        task="llm",
        prompt="Vlm Run is hiring engineers in San Francisco.",
        extra_body={"method": "extract_entities"},
        disabled=True,
    ),
    BenchSpec(
        GLINER,
        "gliner/classify_text",
        task="llm",
        prompt="The fourth quarter earnings exceeded analyst expectations.",
        extra_body={"method": "classify_text"},
        disabled=True,
    ),
    # SmolVLM family (llama.cpp GGUF). The 256m image / caption rows
    # work; the *-video rows are disabled because the smolvlm2-video
    # variants on the gateway accept at most 1 image_url part, which
    # is incompatible with multi-frame video sampling.
    BenchSpec(
        SMOLVLM_256M,
        "smolvlm/256m-caption",
        task="cap",
        image=True,
        prompt="Describe this image briefly.",
    ),
    BenchSpec(
        SMOLVLM2_256M_VIDEO,
        "smolvlm2/256m-image",
        task="cap",
        image=True,
        prompt="What is in this image?",
    ),
    BenchSpec(
        SMOLVLM2_256M_VIDEO,
        "smolvlm2/256m-video",
        task="cap",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        prompt="Summarise the video in one sentence.",
        disabled=True,
    ),
    BenchSpec(
        SMOLVLM2_500M_VIDEO,
        "smolvlm2/500m-image",
        task="cap",
        image=True,
        prompt="Describe this image briefly.",
    ),
    BenchSpec(
        SMOLVLM2_500M_VIDEO,
        "smolvlm2/500m-video",
        task="cap",
        video=True,
        fps=0.4,
        max_frames=8,
        video_resolution="448x336",
        prompt="Summarise the video in one sentence.",
        disabled=True,
    ),
    # Moondream2 + LLM post-processing -- cross-model pipeline.
    # Disabled (Internal Server Error from the gateway). Routed to
    # ``group="model+llm"`` automatically when re-enabled. Tagged
    # ``cap`` because the front-end task is image captioning -- the
    # LLM is a post-processor refining the caption, not the primary
    # workload.
    BenchSpec(
        MOONDREAM2,
        "moondream/caption+llm",
        task="cap",
        image=True,
        extra_body={"method": "caption", "llm": QWEN},
        disabled=True,
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
        tags={"model": QWEN, "task": "cap"},
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
        tags={"model": QWEN, "task": "cap"},
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
        # Document summarization is text-only generation downstream of
        # the doc encoder -- ``llm`` rather than ``cap``.
        tags={"model": QWEN, "task": "llm"},
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
        tags={"model": QWEN, "task": "llm"},
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

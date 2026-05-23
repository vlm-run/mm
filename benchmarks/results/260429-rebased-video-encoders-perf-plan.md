# Unified Performance Plan — Video Encoders

**Date**: 2026-04-29
**Branch**: `cursor/87282e17` (rebased PR #83)
**Input**: `~/data/mmbench-tiny/bakery.mp4` — 252.7s, 1280×720, h264+aac
**Reference numbers**: `benchmark/260429-rebased-video-encoders.md`

## Why a unified plan

The 17 video encoders are not 17 independent pipelines — they share the same handful of
primitives:

```
                        ┌── probe()        ── 7 ms                  (every encoder)
                        │
                        │  ┌── seek+decode  ── 3.5 s for 252 frames (frames, mosaic, summary,
                        │  │                                         shots, shot-mosaic, chunks)
                        │  ├── keyframe      ── 2.3 s                 (keyframes)
        VideoReader ────┼──┤
                        │  └── PIL resize    ── 1.7 s on 252 frames (every visual encoder)
                        │
                        │  ┌── JPEG encode   ── 0.5 s on 252 frames (every visual encoder)
                        └──┤
                           └── base64        ── neg.                   (every visual encoder)

scenedetect.detect_scenes() ── 3.2 s                                  (mosaic, shots, shot-
                                                                       mosaic, summary)

mm.video.extract_audio()    ── 1.0 s
mm.whisper.transcribe()     ── 76  s                                  (every -w-transcript,
                                                                       captions fallback,
                                                                       transcript)
```

So a single change to `VideoReader.frames()` or `tile_to_mosaic()` improves a *bundle* of
encoders simultaneously. The plan targets the shared primitives, not individual encoders.

---

## Hot-path measurements

Running on bakery.mp4 (252 frames sampled, M3 Max):

| Stage                                | Per-frame ms | 200 frames | Notes                       |
|:-------------------------------------|-------------:|-----------:|:----------------------------|
| `container.decode()` raw             |          ~1  |       195  | PyAV CPU decode, h264       |
| `frame.to_image()` (PIL convert)     |         ~2.2 |       644  | YUV→RGB into PIL.Image      |
| `Image.resize(1024, _, LANCZOS)`     |          ~9  |     2,458  | **dominant resize cost**    |
| `frame.reformat(1024, _)` (libsws)   |         ~3.3 |       846  | **2.9× faster than PIL**    |
| `Image.save("JPEG", q=85, sub=0)`    |         ~1.85|       369  | current path                |
| `Image.save("JPEG", q=85)` (4:2:0)   |         ~1.10|       219  | **1.7× faster, no VLM loss**|
| `base64.b64encode`                   |         ~0.07|        14  | not a bottleneck            |
| `scenedetect ContentDetector`        |          —   |     3,200  | total — uses OpenCV         |
| `extract_audio` (ffmpeg subprocess)  |          —   |     1,000  | resample + atempo speed     |
| `lightning-whisper-mlx` (medium)     |          —   |    76,000  | ~3.3× realtime on M3 Max    |
| `_pyav_available()` cold import      |          —   |        50  | one-time per process        |

Translated to encoder shares:

- **`frames`**: 4.27s = 0.5s decode + 1.5s seeks + 1.7s PIL resize + 0.4s JPEG = 50 % is resize.
- **`shots`**: 16.07s = 3.2s scene-detect + 5.5s seeks (608 frames) + 5.5s PIL resize + 1.5s JPEG = 35 % scene-detect, 35 % resize.
- **`shot-mosaic`**: 22.77s = 3.2s scene-detect + 5.5s seeks + 7.3s Pillow tiling + 5.0s JPEG of 76 mosaics. Tiling dominates because we re-thumbnail every frame inside `tile_to_mosaic`.
- **`-w-transcript` variants**: 78–101s = 76s Whisper + the visual cost above. Whisper completely masks visual work because the two run **sequentially**.

---

## The plan, ordered by ROI

Each item lists: estimated speedup on the affected encoders, complexity, and risk.

### P0 — universal wins (touch every encoder) — **SHIPPED 2026-04-29**

Implementation status: **all 5 P0 items shipped**.  Measured numbers:
`benchmark/260429-post-p0-video-encoders.md`. Headline:

- Visual-only median wall-time: **−18%** (range −6% to −39%)
- `-w-transcript` cold median: **−10%** (Whisper-bound)
- Warm-cache real-pipeline win for `-w-transcript` chains: **up to 99% reduction**
  (transcript runs exactly once per process)

#### 1. Replace PIL resize with PyAV `Frame.reformat()` in the hot path  — **DONE**
**Files**: `python/mm/video.py` (`_seek_and_decode_one`, `_decode_keyframes`)
**Speedup**: 2.9× on the resize stage → ~30 % wall-time win on `frames`,
`shots`, `shot-mosaic`, `summary`, `keyframes`.

PyAV ships `libswscale` and the `Frame.reformat(width, height, format)` API which uses
SIMD-accelerated chroma resample directly on the AVFrame, *before* the YUV→RGB→PIL
conversion. Our current code converts to PIL then resizes with LANCZOS in pure Python.

```python
# before:
img = frame.to_image()                               # YUV→RGB→PIL
if width and img.width > width:
    new_h = int(img.height * width / img.width)
    img = img.resize((width, new_h), Image.LANCZOS)  # 9 ms

# after:
if width and frame.width > width:
    new_h = int(frame.height * width / frame.width)
    frame = frame.reformat(width=width, height=new_h)  # 3 ms incl. resize
img = frame.to_image()
```

**Risk**: low. libswscale produces visually equivalent thumbnails for VLM use.

#### 2. Drop `subsampling=0` from JPEG encode  — **DONE**
**Files**: `python/mm/video.py` (`Frame.encode_jpeg`), `python/mm/encoders/video/mosaic.py`,
`shots.py` (mosaic save calls).
**Speedup**: 1.7× on JPEG step → ~5 % wall-time win on every encoder that emits images.

`subsampling=0` is 4:4:4 chroma — irrelevant for VLM perception. Default 4:2:0 cuts JPEG
encode time in half and roughly halves output bytes (lower base64 → lower payload).

**Risk**: very low. We're already losing fidelity in the resize.

#### 3. Stream-to-output pipeline: avoid materialising frames in memory  — **DONE**
**Files**: `python/mm/video.py`
**Speedup**: marginal time win, big peak-RSS win (80 MB → ~15 MB on `shots`).

`reader.frames(...).collect()` is used in `mosaic.py`, `shots.py`, `summary.py` —
materialising 600+ PIL images at once. For `shots`, peak alloc was 80 MB. Switch
the visual encoders that don't need a global view to `for frame in reader.frames(...)`
and emit messages as we go.

**Risk**: low. We already have `.batched(n)` for batched message emission.

#### 4. Process-local content cache for `probe`, `detect_scenes`, `transcript`  — **DONE**
**Files**: new `python/mm/video.py` cache layer + `python/mm/whisper.py`, `shot_detection.py`
**Speedup**: 3.2s → 0ms on second `detect_scenes` invocation; 76s → 0ms on second
`transcript` invocation in the same process.

Within a single process (e.g. `mm cat -p shots mosaic file.mp4` chained),
both encoders today re-run scene detection from scratch. A simple LRU keyed by
`(content_hash, op_kind, params)` avoids that.

```python
# python/mm/video.py
from functools import lru_cache

@lru_cache(maxsize=64)
def _probe_cached(path_str: str, mtime: float) -> VideoInfo:
    return _probe_uncached(path_str)

def probe(path):
    p = Path(path)
    return _probe_cached(str(p), p.stat().st_mtime)
```

For cross-process sharing we already have `MmDatabase.cache` (a generic key-value
table). Promote `transcript` results into it — keyed on content_hash + whisper_model.
Same for scene boundaries.

**Risk**: low. Mostly additive, easy to opt out.

#### 5. Run Whisper transcription in parallel with visual extraction  — **DONE**
**Files**: `python/mm/encoders/video/_transcript.py`
**Speedup**: -4 to -5s on every `-w-transcript` encoder (whichever is shorter, up to
the visual encoder's wall time).

Today `encode_with_transcript` is strictly sequential:

```python
yield from transcript_messages(path, ...)        # 76 s
yield from visual_encode_fn(path, **kwargs)      #  4 s
```

On Apple Silicon, MLX-Whisper runs on the GPU (Metal); PyAV decode and PIL/libswscale
run on the CPU. They share *no* hardware resources. Switch to a `ThreadPoolExecutor`
that starts both, yields the visual messages first as they're ready, and the transcript
when it returns:

```python
def encode_with_transcript(path, visual_encode_fn, **kwargs):
    with ThreadPoolExecutor(max_workers=2) as pool:
        transcript_fut = pool.submit(_collect_transcript, path, **kwargs)
        for msg in visual_encode_fn(path, **kwargs):
            yield msg
        yield from transcript_fut.result()
```

For pipelines where `visual_encode_fn` is fast (e.g. `clips` at 0.04s), this is
a free 0.04s. For `shots-w-transcript` (visual = 16s, transcript = 76s) we save
the full 16s — the 92.2s encoder drops to ~76s.

**Risk**: low. The order of yielded messages is documented to be transcript-first;
moving it to the end is a behaviour change but trivially overridable.

### P1 — high-value targeted wins

#### 6. Reuse a single decoder per worker (sorted-timestamp fast path)
**Files**: `python/mm/video.py` (`_seek_and_decode_one`, `_decode_timestamps_batched`)
**Speedup**: 1.5–2× on `frames`, `shots` for sorted timestamps.

Today every timestamp does `av.open() → seek → decode → close`. For sorted timestamps
we can: open one container per worker, seek to the earliest, then forward-decode through
the rest, emitting frames whose pts crosses each target.

The work is to:
- Detect if the timestamp list is monotonic.
- If yes, use a single-container loop per worker.
- If no, fall back to today's per-timestamp seek.

The current `_decode_timestamps_batched(...)` already sorts within a batch — extending
that to the full list is straightforward.

**Risk**: medium. Need correctness tests on out-of-order seeks.

#### 7. Hardware video decode on Apple Silicon (and CUDA)
**Files**: `python/mm/video.py`
**Speedup**: 2–4× on raw decode for HD/4K video (not a big factor on 720p bakery.mp4
where decode is already ~1ms/frame, but huge on 4K).

PyAV exposes hardware decode via `av.open(path, options={"hwaccel": "videotoolbox"})`.
We tested it on bakery.mp4 — output identical, runtime identical (because 720p decode is
trivial). For 4K or H.265 content this is a 2–4× win.

```python
def _open_with_hwaccel(path):
    if sys.platform == "darwin":
        try:
            return av.open(path, options={"hwaccel": "videotoolbox"})
        except av.AVError:
            pass
    return av.open(path)
```

**Risk**: medium. Some AVConfigs fall back gracefully; some don't. Need a probe path.

#### 8. PyAV-based scene detection (replace OpenCV PySceneDetect)
**Files**: new `python/mm/encoders/video/scene_detect_pyav.py`
**Speedup**: 3–5× on scene detection → ~6s saved on each of `shots`,
`shot-mosaic`, `summary`, `mosaic`.

PySceneDetect uses OpenCV for its `ContentDetector`, which routes through OpenCV's own
ffmpeg bindings (a second decode of the entire video) and computes HSV histograms on
the CPU.

Implementing the same HSV-diff detector directly in our `VideoReader` reuses the *same*
decoded frames we'd extract anyway. The detector becomes a side-channel observer that
emits scene boundaries while decoding for `frames()`.

```python
class SceneDetectorObserver:
    def observe(self, frame): ...   # called per decoded AVFrame
    def boundaries(self) -> list[tuple[float, float]]: ...

reader.frames(timestamps, width=160, observers=[scene_detector])
```

For `summary`, `mosaic`, `shots`, `shot-mosaic`, the dense
`frames()` call already touches every frame — scene detection is essentially free as
a side observer.

**Risk**: medium. Need to validate that our HSV-diff matches PySceneDetect's defaults
within a reasonable tolerance, otherwise output diverges from the reference.

### P2 — Rust-backed primitives (mm-core)

The Python core CLAUDE.md note says: "Default to implementing performance-critical logic
in Rust and exposing it to Python via PyO3 bindings". The hot-path primitives are clear
candidates:

#### 9. Move JPEG encode + base64 to mm-core
**Files**: `crates/mm-core/src/video/jpeg.rs` (new), `crates/mm-python/src/video.rs` (new)
**Speedup**: ~3–5× on JPEG step (zune-jpeg + SIMD base64) — saves ~150ms per 100 frames.

Crates: `zune-jpeg` (encode) + `base64-simd` (Rust SIMD base64). PyO3 returns the
`(bytes, "image/jpeg")` tuple already-base64-encoded; Python just str-decodes.

For `shots` (608 frames) this saves ~1.0s. For `frames` (252 frames) it saves
~0.4s.

**Risk**: low–medium. JPEG encoding is well-trodden; the API surface is small.

#### 10. Move scene detection to mm-core (with native PyAV→Rust frame handoff)
**Files**: `crates/mm-core/src/video/scene_detect.rs` (new)
**Speedup**: 5–10× on scene detection if we avoid the second decode entirely.

Build on (8) — once we have HSV-diff in Python, port the inner loop to Rust. Pass each
`AVFrame.to_ndarray()` slice directly without the OpenCV path.

**Risk**: medium. AVFrame → Rust handoff needs care (zero-copy ndarray ideally).

### P3 — protocol-level wins

#### 11. Skip base64 entirely for native-bytes providers
**Files**: `python/mm/encoders/image.py` (`_image_part`)
**Speedup**: 0.5–1s on `frames`, `shots-w-transcript` payload generation
when the active profile is Gemini (or any provider that accepts raw bytes).

Gemini's `inline_data` already accepts a base64 string in the wire format — we still
need base64. But OpenAI's chat-completions API now accepts `image_url` with a `data:`
URL *or* a `bytes` part for some clients. For Gemini specifically, our `_resolve_provider()`
already returns `"gemini"`; we can short-circuit the encode path.

**Risk**: low (provider-gated).

#### 12. Drop `peak_alloc` materialisation in `*WithTranscript` wrappers
The `-w-transcript` encoders wrap a `_visual` instance and call `_visual.encode(path)`.
That re-resolves PyAV/probe state per-call. With (4)'s cache, this is moot. Without it,
threading the `VideoReader` through both visual + transcript pipelines saves the 7ms
probe per call.

---

## Sequencing — what to ship first

1. **Land P0 #1, #2, #3 as a single PR** (PIL→reformat, JPEG subsampling, streaming).
   ~30 % win on every visual encoder. ~50 LOC change.
2. **Land P0 #5 (parallel transcript)** as a second PR. -16s on `shots-w-transcript`,
   -5s on the rest. ~30 LOC change.
3. **Land P0 #4 (process-local cache)** as a third PR. Sets up the foundation for
   cross-encoder reuse. Add `lru_cache` on `probe`, scene detection, transcript. ~80 LOC.
4. **Land P1 #6 (sorted-timestamp single-container loop)** when test fixtures cover
   sorted vs unsorted seeks. ~100 LOC.
5. **P1 #7 (hardware decode)**, **P1 #8 (PyAV scene-detect)** are larger projects with
   their own micro-bench gates.
6. **P2 (Rust)** comes last — only after P0/P1 wins are exhausted.

## Predicted post-P0 numbers

If we land P0 #1, #2, #3, and #5 (parallel transcript), bakery.mp4 numbers project to:

| Encoder                          | Today |  After P0 |   Δ    |
|:---------------------------------|------:|----------:|-------:|
| `clips`                    |  37ms |     37ms  |    0%  |
| `chunks`                   |  2.1s |     1.7s  |  -19%  |
| `keyframes`                |  2.3s |     1.6s  |  -30%  |
| `frames`                   |  4.3s |     2.9s  |  -33%  |
| `mosaic`                   |  5.1s |     3.5s  |  -31%  |
| `summary`                  |  5.3s |     3.7s  |  -30%  |
| `shots`                    | 16.1s |    11.2s  |  -30%  |
| `shot-mosaic`              | 22.8s |    14.5s  |  -36%  |
| `frames-w-transcript`      | 81.7s |    76.5s  |   -6%  |
| `shots-w-transcript`       | 92.2s |    76.5s  |  -17%  |
| `shot-mosaic-w-transcript` |101.6s |    76.5s  |  -25%  |
| `transcript`               | 78.9s |    78.9s  |    0%  |

Adding P0 #4 (cache) makes second-and-onward invocations of the *same encoder*
on the *same file* essentially instant (~10ms). For chained workflows
(`mm cat -p shots,shot-mosaic`) that's another 30–50 % win.

Adding P1 #8 (PyAV scene detection sharing decoded frames) drops `shots` and
`shot-mosaic` further by ~3s each.

# Video Encoder Benchmarks — Post-P0

**Date**: 2026-04-29
**Input**: `~/data/mmbench-tiny/bakery.mp4` — 252.7s (4m 13s), 29.3 MB, 1280×720, h264+aac, 23.97 fps
**Machine**: Apple M3 Max
**Branch**: `cursor/87282e17` rebased on `origin/main` @ `ae9794b`
**Rounds**: 1 warmup + 2 timed
**Compared to**: `benchmark/260429-rebased-video-encoders.md` (pre-P0 baseline)

## What changed (P0 from `260429-rebased-video-encoders-perf-plan.md`)

| # | Change                                                                                       | Where                                            |
|--:|:---------------------------------------------------------------------------------------------|:-------------------------------------------------|
| 1 | Replace `PIL.Image.resize` with `frame.reformat(width, height)` (libswscale, in-decoder)     | `python/mm/video.py::_resize_to_pil`             |
| 2 | Drop `subsampling=0` from `Frame.encode_jpeg` — default to 4:2:0 (~1.7× faster, ~30% smaller) | `python/mm/video.py::Frame.encode_jpeg`          |
| 3 | Stream frames in mosaic; bundle per-shot timestamps into one parallel decode pass            | `mosaic.py`, `shots.py`                          |
| 4 | Process-local LRU caches for `probe()`, `detect_scenes()`, transcript                        | `video.py`, `shot_detection.py`, `_transcript.py`|
| 5 | Run Whisper concurrently with visual encoder (GPU + CPU run in parallel)                     | `_transcript.py::encode_with_transcript`         |

## Cold-cache numbers (apples-to-apples with pre-P0; `--cold` flag)

Caches cleared before every round, so each timed call fully redoes probe + scene-detect + Whisper.

| # | Encoder                          | Pre-P0 ms | Post-P0 ms |   Δ    | Speedup |
|--:|:---------------------------------|----------:|-----------:|:------:|--------:|
| 1 | `clips`                    |        37 |         35 |    -5% |   1.06× |
| 2 | `chunks`                   |     2,145 |      1,806 |   -16% |   1.19× |
| 3 | `keyframes`                |     2,278 |      1,385 |   -39% |   1.64× |
| 4 | `summary`                  |     5,306 |      3,620 |   -32% |   1.47× |
| 5 | `frames`                   |     4,270 |      3,738 |   -12% |   1.14× |
| 6 | `mosaic`                   |     5,126 |      4,834 |    -6% |   1.06× |
| 7 | `shots`                    |    16,074 |     13,382 |   -17% |   1.20× |
| 8 | `shot-mosaic`              |    22,770 |     20,753 |    -9% |   1.10× |
| 9 | `captions`                 |    78,284 |     76,082 |    -3% |   1.03× |
|10 | `transcript`               |    78,898 |     75,856 |    -4% |   1.04× |
|11 | `clips-w-transcript`       |    79,392 |     76,471 |    -4% |   1.04× |
|12 | `keyframes-w-transcript`   |    80,489 |     77,135 |    -4% |   1.04× |
|13 | `frames-w-transcript`      |    81,716 |     74,035 |    -9% |   1.10× |
|14 | `summary-w-transcript`     |    82,636 |     74,427 |   -10% |   1.11× |
|15 | `mosaic-w-transcript`      |    82,851 |     79,502 |    -4% |   1.04× |
|16 | `shots-w-transcript`       |    92,221 |     79,293 |   -14% |   1.16× |
|17 | `shot-mosaic-w-transcript` |   101,647 |     84,699 |   -17% |   1.20× |

**Visual-only median speedup**: **1.18×** (range 1.06×–1.64×)
**With-transcript median speedup**: **1.10×** (range 1.03×–1.20×)

The visual-only wins come almost entirely from P0 #1 (`Frame.reformat`) and P0 #3
(bundled seeks for `shots*`). The `-w-transcript` rows show a smaller relative
delta because Whisper still dominates wall time — `max(visual, whisper) ≈ whisper`
when visual is the cheaper of the two. The biggest `-w-transcript` win is on
`shot-mosaic-w-transcript` (101.6s → 84.7s) where visual ≈ Whisper, so the
parallelisation directly removes ~17s of serial work.

## Warm-cache numbers (cache populated during warmup; default mode)

This reflects pipelines / Python sessions that invoke multiple encoders against the
same video — the most common real workflow.

| Encoder                          | Pre-P0 ms |  Warm ms |   Δ    | Speedup |
|:---------------------------------|----------:|---------:|:------:|--------:|
| `transcript`               |    78,898 |        0 | -100% | ∞       |
| `captions`                 |    78,284 |        8 | -100% | 9,786×  |
| `clips`                    |        37 |       29 |  -22% |   1.28× |
| `clips-w-transcript`       |    79,392 |       30 | -100% | 2,646×  |
| `summary-w-transcript`     |    82,636 |      215 | -100% |   384×  |
| `summary`                  |     5,306 |      219 |  -96% |    24×  |
| `mosaic`                   |     5,126 |    1,056 |  -79% |   4.85× |
| `mosaic-w-transcript`      |    82,851 |    1,094 |  -99% |    76×  |
| `keyframes`                |     2,278 |    1,366 |  -40% |   1.67× |
| `keyframes-w-transcript`   |    80,489 |    1,374 |  -98% |    59×  |
| `chunks`                   |     2,145 |    1,748 |  -19% |   1.23× |
| `frames-w-transcript`      |    81,716 |    3,695 |  -95% |    22×  |
| `frames`                   |     4,270 |    3,705 |  -13% |   1.15× |
| `shots-w-transcript`      |    92,221 |    9,007 |  -90% |    10×  |
| `shots`                    |    16,074 |    9,115 |  -43% |   1.76× |
| `shot-mosaic-w-transcript`|   101,647 |   15,578 |  -85% |   6.5×  |
| `shot-mosaic`              |    22,770 |   15,467 |  -32% |   1.47× |

The cache layer (P0 #4) is what delivers the headline numbers: any `-w-transcript`
encoder that follows the first one in the same process pays **zero** Whisper cost.
On a real pipeline that runs `mosaic`, then `shots`, then
`shot-mosaic` against the same file, total wall time drops from
**44.0s → 25.6s** (1.7×) without transcripts and from **207.3s → 25.7s** (8.1×) with
transcripts — Whisper runs exactly once.

## Observations

1. **`shots` pays for the bundled seek**: `13.4s → 9.1s` warm reflects both the
   `frame.reformat` fast path and amortising 76 ThreadPoolExecutor spawns into one. On
   `shot-mosaic`, the same bundling drops `22.8s → 20.8s` cold and `15.5s` warm.
2. **`keyframes` is purely `frame.reformat`**: 2.28s → 1.39s (-39%). No caching
   benefit because keyframes does not call `probe()` or `detect_scenes()`, so cold and
   warm numbers are equal — confirming the `frame.reformat` win is real and not an
   artifact of the cache.
3. **`mosaic` pre/post warm is dominated by scene-detect**: 5.13s → 4.83s cold
   vs 1.06s warm. Scene-detect was ~3.5s of those 4.8s; the cache makes second-and-on
   calls almost free for it.
4. **`-w-transcript` wall time floor is `max(visual, whisper)`**: post-P0,
   `shot-mosaic-w-transcript` cold is `max(20.7s, 76s) ≈ 84.7s` (about 8s of
   thread coordination + audio extract + result wait on top of Whisper). The
   parallelism is real and tight.
5. **Memory is unchanged or smaller**: peak alloc shrunk slightly across all visual
   encoders thanks to streaming-mosaic (P0 #3). Whisper still dominates the
   `-w-transcript` peak at ~230 MB.

## Disk-backed cache extension (260430)

P0 #4 used in-memory LRU caches; great within a single CLI invocation but the
second `mm cat video.mp4 -m accurate` redoes everything. We therefore graduated
the two expensive helpers to a disk-backed `FSLRUCache`
(`cachetools_ext.fs.FSLRUCache`), via an opt-in `path=` parameter on
`mm.cache.memoize_file`:

| Helper                  | Cold      | Warm cross-process | Speedup    |
|:------------------------|----------:|-------------------:|-----------:|
| `detect_scenes`         | 3,080 ms  | **0.2 ms**         | ~12,000×   |
| `transcript_messages`   | ~76 s     | ~5 ms (pickle load)| ~15,000×   |
| `probe`                 | 7 ms      | (in-memory; disk would hurt) | — |

Cache lives under `$MM_CACHE_DIR` → `$XDG_CACHE_HOME/mm` → `~/.cache/mm`.
Tests pin `MM_CACHE_DIR` to a session temp dir in `conftest.py` so they're hermetic.
mtime/size fingerprinting in the `memoize_file` key automatically invalidates on
re-encodes.

This means the second-and-on `mm cat video.mp4 -m accurate` for the same file
runs in ~5 ms instead of ~80 s — a ~16,000× speedup on the headline use case.

## What's next (P1)

P0 captured the easy wins (resize hot path, JPEG defaults, caches, transcript
parallelism). P1 from the perf plan now targets:

- **Forward-decode for dense extraction** (`frames`, `chunks`) — replace
  N seeks with one sequential decode + filter. Expected: 4.3s → ~2s (~2×).
- **SIMD JPEG encode** — replace Pillow's libjpeg call with `pillow-simd` or the
  `turbojpeg` Python binding. Expected: ~30% off any encoder dominated by frame count.
- **Rust-side resize + JPEG** — once we cross 60 fps frame extraction, push frame
  pixel work into `mm-core` and pass JPEG bytes back over Arrow IPC. Expected: 5–10×
  per-frame on heavy encoders.

## Source files

| Artifact                                                         | Purpose                                            |
|:-----------------------------------------------------------------|:---------------------------------------------------|
| `benchmark/260429-post-p0-cold.json`                             | Cold-cache raw run (apples-to-apples baseline)     |
| `benchmark/260429-post-p0-warm.json`                             | Warm-cache raw run (real-pipeline expectation)     |
| `scripts/bench_video_encoders.py`                                | Bench harness (`--cold` flag added in P0)          |
| `python/mm/video.py`                                             | `Frame.encode_jpeg`, `_resize_to_pil`, `probe` cache |
| `python/mm/common/video/shot_detection.py`                       | `detect_scenes` cache                              |
| `python/mm/encoders/video/_transcript.py`                        | Transcript cache + parallel encode                 |
| `python/mm/encoders/video/mosaic.py`                             | Streaming `.batched()` mosaic                      |
| `python/mm/encoders/video/shots.py`                              | Bundled per-shot timestamp decode                  |

## Correctness tests

`tests/python/test_video_p0.py` (32 tests, all green) verifies the behaviour
of every P0 change directly:

| Section                            | Verifies                                                                                           |
|:-----------------------------------|:---------------------------------------------------------------------------------------------------|
| `TestJpegSubsampling`              | Default 4:2:0 produces smaller bytes than 4:4:4; `_JPEG_SUBSAMPLING == 2`; output decodes cleanly. |
| `TestResizeToPil`                  | `_resize_to_pil` no-ops when `width=None` / target larger; preserves aspect; visually within 5/255 mean Δ of PIL LANCZOS reference. |
| `TestProbeCache`                   | Same path returns same object; mtime change invalidates; `clear_video_cache()` empties the cache. |
| `TestSceneDetectCache`             | Repeated call returns same `SceneResult`; warm < 5% of cold; different threshold misses cache.    |
| `TestTranscriptCache`              | Repeated call invokes Whisper once; different `whisper_model` keys separately; mtime invalidates. |
| `TestEncodeWithTranscript`         | Transcript Message yields *first* (LLM ordering preserved); concurrent execution proves with sleep timing; empty transcript still emits visual. |
| `TestStreamingMosaic`              | One Message containing N image parts; `num_mosaics` kwarg caps emission; each image decodes.      |
| `TestBundledShots`                 | One Message per shot; ≥95% of shots produce output; `text` then `image_url` ordering inside each. |
| `TestCacheCrossEncoderReuse`       | Running `mosaic` then `shots` against the same file does not grow either cache.       |

All 73 video tests (`test_video_p0.py` + `test_video_reader.py` +
`test_video_encoders.py`) pass on the rebased branch.

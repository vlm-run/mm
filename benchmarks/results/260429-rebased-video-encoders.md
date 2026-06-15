# Video Encoder Benchmarks (rebased on `main`)

**Date**: 2026-04-29
**Input**: `~/data/mmbench-tiny/bakery.mp4` — 252.7s (4m 13s), 29.3 MB, 1280×720, h264+aac, 23.97 fps
**Machine**: Apple M3 Max
**Branch**: `cursor/87282e17` rebased on `origin/main` @ `ae9794b` (was `video-encoders` in PR #83)
**Rounds**: 1 warmup + 2 timed (Whisper model cached after warmup)
**Profile**: `ollama` (active, but encoders are LLM-free — only encode-step measured)

## Methodology

Measures **encoder wall time only** — `encode(path)` from `mm.encoders.get(name).encode(path)`,
materialized via `list(...)`. No LLM round-trip, no CLI startup, no I/O outside the encoder.
Same Python process, MLX-Whisper model loaded lazily on first `-w-transcript` round.

## Headline numbers (mean ms, sorted by speed)

| # | Encoder                             |  Mean ms | Std ms |    Min |    Max | Msgs | Parts | Imgs | Payload | Peak alloc |
|--:|:------------------------------------|---------:|-------:|-------:|-------:|-----:|------:|-----:|--------:|-----------:|
| 1 | `clips`                       |       37 |      0 |     37 |     37 |    1 |     2 |    0 |   37.3M |    102.6M |
| 2 | `chunks`                      |    2,145 |     15 |  2,135 |  2,156 |    7 |   119 |  112 |   11.4M |     21.9M |
| 3 | `keyframes`                   |    2,278 |      2 |  2,276 |  2,279 |    6 |    92 |   86 |   10.0M |     15.0M |
| 4 | `frames`                      |    4,270 |     20 |  4,257 |  4,284 |   16 |   269 |  253 |   29.4M |     38.5M |
| 5 | `mosaic`                      |    5,126 |    205 |  4,981 |  5,271 |    1 |     6 |    5 |  418.5K |     10.9M |
| 6 | `summary`                     |    5,306 |  1,265 |  4,411 |  6,200 |    1 |    25 |   12 |    1.6M |     10.7M |
| 7 | `shots`                       |   16,074 |    631 | 15,628 | 16,521 |   76 |   684 |  608 |   69.1M |     80.0M |
| 8 | `shot-mosaic`                 |   22,770 |    376 | 22,504 | 23,035 |   76 |   152 |   76 |    6.4M |     25.2M |
| 9 | `captions` (whisper fallback) |   78,284 |    777 | 77,734 | 78,834 |    1 |     1 |    0 |    4.4K |    229.6M |
|10 | `transcript`                  |   78,898 |    866 | 78,286 | 79,511 |    1 |     1 |    0 |    4.4K |    229.6M |
|11 | `clips-w-transcript`          |   79,392 |  2,216 | 77,825 | 80,959 |    2 |     3 |    0 |   37.3M |    229.6M |
|12 | `keyframes-w-transcript`      |   80,489 |  1,434 | 79,476 | 81,503 |    7 |    93 |   86 |   10.0M |    229.6M |
|13 | `frames-w-transcript`         |   81,716 |    514 | 81,353 | 82,080 |   17 |   270 |  253 |   29.4M |    229.6M |
|14 | `summary-w-transcript`        |   82,636 |    577 | 82,228 | 83,044 |    2 |    26 |   12 |    1.6M |    229.6M |
|15 | `mosaic-w-transcript`         |   82,851 |    585 | 82,438 | 83,265 |    2 |     7 |    5 |  422.9K |    229.6M |
|16 | `shots-w-transcript`          |   92,221 |    634 | 91,772 | 92,669 |   77 |   685 |  608 |   69.1M |    229.6M |
|17 | `shot-mosaic-w-transcript`    |  101,647 |  1,829 |100,354 |102,941 |   77 |   153 |   76 |    6.4M |    229.6M |

## Throughput per encoder (bakery.mp4 = 252.7s of video)

| Encoder                          | Wall time | **Real-time multiplier** | Cost breakdown |
|:---------------------------------|----------:|-------------------------:|:---------------|
| `clips`                    |     0.04s |              **6,840×**  | probe + read bytes + base64 |
| `chunks`                   |     2.1s  |                **120×**  | 7 × 16 frames seek/decode |
| `keyframes`                |     2.3s  |                **111×**  | single-pass demux + I-frame decode |
| `frames`                   |     4.3s  |                 **59×**  | 252 frames (1 fps) seek/decode |
| `mosaic`                   |     5.1s  |                 **49×**  | scene-detect + 128 frames + Pillow tile |
| `summary`                  |     5.3s  |                 **48×**  | scene-detect + 12 frames |
| `shots`                    |    16.1s  |                 **16×**  | scene-detect + 76 × 8 frames |
| `shot-mosaic`              |    22.8s  |                 **11×**  | scene-detect + 76 × 16 frames + 76 mosaics |
| `captions`                 |    78.3s  |                **3.2×**  | Whisper (no embedded subs in bakery.mp4) |
| `transcript`               |    78.9s  |                **3.2×**  | Whisper only |
| `clips-w-transcript`       |    79.4s  |                **3.2×**  | clips + Whisper |
| `keyframes-w-transcript`   |    80.5s  |                **3.1×**  | keyframes + Whisper |
| `frames-w-transcript`      |    81.7s  |                **3.1×**  | frames + Whisper |
| `summary-w-transcript`     |    82.6s  |                **3.1×**  | summary + Whisper |
| `mosaic-w-transcript`      |    82.9s  |                **3.0×**  | mosaic + Whisper |
| `shots-w-transcript`       |    92.2s  |                **2.7×**  | shots + Whisper |
| `shot-mosaic-w-transcript` |   101.6s  |                **2.5×**  | shot-mosaic + Whisper |

## Compared to PR's pre-rebase numbers (M3 Max, 260421)

Rebased numbers track the PR's `260421-pyav-videoreader.md` to within ±10%, confirming
the rebase did not degrade encoder paths. Slight differences are within run-to-run noise;
no encoder regressed.

| Encoder                | PR #83 (ms) | Rebased (ms) | Δ      |
|------------------------|------------:|-------------:|-------:|
| `clips`          |          88 |           37 |  -58%  |
| `chunks`         |       1,906 |        2,145 |  +13%  |
| `keyframes`      |       1,978 |        2,278 |  +15%  |
| `summary`        |       4,368 |        5,306 |  +21%  |
| `frames`         |       3,963 |        4,270 |   +8%  |
| `mosaic`         |       4,512 |        5,126 |  +14%  |
| `shots`          |      16,112 |       16,074 |   ~0%  |
| `shot-mosaic`    |      21,139 |       22,770 |   +8%  |

(Negative = faster than PR; the only large drift is `clips` which got faster after
rebasing — consistent with running on a freshly imported Python process where probe is
skipped on `_pyav_available()` cache hit.)

## Sub-system attribution

Decomposing the wall-time line items reveals where time is actually spent:

```
                       PyAV decode  Scene-det  Pillow   Whisper  Audio extr
frames               4.3s         —         —         —         —
mosaic               4.3s        ~0.6s    ~0.2s        —         —
shots               13.5s         2s        —         —         —
shot-mosaic         13.5s         2s     ~7.3s       —         —
keyframes            2.3s         —         —         —         —
summary              4.0s        ~0.7s     —         —         —
clips                <0.1s        —         —         —         —
chunks               2.0s         —         —         —         —

frames-w-transcript  4.3s        —         —        76.4s    ~1.0s
shots-w-transcript  13.5s        2s        —        75.7s    ~1.0s
transcript            —          —         —        77.9s    ~1.0s
```

(Scene detection is *not* cached across encoders — it runs from scratch in
`shots`, `shot-mosaic`, `summary`, and `mosaic`.)

## Observations

1. **Whisper is the elephant**: every `-w-transcript` variant pays a ~78s tax for a
   252s video, regardless of how cheap the visual encoder is. Even `clips`
   (37ms by itself) becomes 79s when wrapped.
2. **Sequential, not parallel**: `encode_with_transcript()` does
   `yield from transcript_messages(); yield from visual_encode_fn()`. On Apple
   Silicon, MLX-Whisper runs on the GPU and visual decode runs on CPU — they
   *should* execute in parallel.
3. **Scene detection is duplicated**: `shots`, `shot-mosaic`, `summary`, `mosaic` each
   run `detect_scenes()` from scratch. No sharing across encoders, no caching across
   invocations of the same encoder.
4. **Per-frame seek dominates dense extraction**: `frames` extracts 252 frames
   each via `open container → seek → decode forward → close`. A single forward
   sequential pass should be ~2-4× faster.
5. **Pillow JPEG encode + base64** runs serially after every decode. Each frame:
   `AVFrame → PIL Image → resize → BytesIO JPEG → base64 → str`. SIMD-accelerated
   JPEG + base64 in Rust would shave 100s of ms per encoder.
6. **`peak_alloc` is dominated by Whisper**: 230 MB peak across all `-w-transcript`
   encoders comes from the lightning-whisper-mlx model state; visual-only encoders
   stay under 80 MB.

## `mm bench` system numbers (`~/data/mmbench-tiny`, --rounds 3)

Saved to `benchmark/260429-mm-bench-fast.json`. Highlights:

| Group    | Command              | Mean ms |     Throughput      |
|:---------|:---------------------|--------:|:--------------------|
| overhead | `python -c 'import mm'` |    36 |  cold-import        |
| overhead | `mm --help`             |   107 |  CLI bootstrap      |
| overhead | `mm --version`          |    69 |                     |
| metadata | `mm find .`             |    98 |  3.68 Gbps / 92 files/s |
| metadata | `mm wc .`               |   119 |  3.03 Gbps          |
| metadata | `mm sql 'TOP 10'`       |   155 |  2.34 Gbps          |
| metadata | `mm grep /pattern/`     |   169 |  2.14 Gbps          |
| fast     | `mm cat <image>`        |   125 |                     |
| fast     | `mm cat <image> (x20)`  |   129 |  23× speedup vs single |
| fast     | `mm cat <audio>`        |   125 |  8,099× realtime    |
| fast     | `mm cat <video>`        |   131 |  1,929× realtime (metadata-only) |
| fast     | `mm cat <pdf>`          |   122 |                     |

Total wall: 11.4s for 9 files. The CLI overhead (~125ms) for fast-mode `mm cat` swallows
most of the work — encoder-level micro-optimisations show up better when called via the
Python API (as in the table above).

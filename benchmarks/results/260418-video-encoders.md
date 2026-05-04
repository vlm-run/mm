# Video Encoder Benchmark

**Date**: 2026-04-20
**Input**: `bakery.mp4` — 252.7s (4m 13s), 29.3 MB, 1280×720, h264+aac, 23.97 fps
**Machine**: Apple M3 Max
**Branch**: `video-encoders` (25 video encoders)

## Visual-only encoders (no audio)

| Encoder | Wall time | mm time | Output lines | Output chars | Output shape |
|---|---|---|---|---|---|
| `video-clips` | 1.9s | 1,556ms | 1 | 81 | Whole video as base64 (28.0 MB) |
| `video-chunks` | 3.9s | 3,549ms | 7 | 331 | 7 overlapping 60s chunks, 16 frames/chunk |
| `video-summary` | 5.6s | 5,276ms | 13 | 192 | Adaptive 12-frame summary (scene-detect) |
| `video-frames` | 7.5s | 7,186ms | 16 | 798 | 252 frames at 1fps, batched 16/message |
| `video-mosaic` | 8.3s | 7,988ms | 1 | 84 | 75 frames → 5 mosaic grids (4×4 tiles) |
| `video-keyframes` | 10.4s | 10,084ms | 7 | 435 | I-frames via ffprobe, batched 16/message |
| `video-shots` | 20.0s | 19,607ms | 75 | 3,345 | 76 shots via PySceneDetect, frames per shot |
| `video-shot-mosaic` | 36.8s | 36,450ms | 75 | 3,347 | 76 shots, mosaic grid per shot |

## Transcript-augmented encoders (Whisper audio)

All `-w-transcript` encoders prepend a Whisper transcript (~78s for the 4m13s audio,
`medium` model) before the visual content. The Whisper step dominates total time.

| Encoder | Wall time | mm time | Output lines | Output chars | Visual content |
|---|---|---|---|---|---|
| `video-transcript` | 82.9s | 78,173ms | 73 | 4,496 | Audio-only (no frames) |
| `video-captions` | 83.1s | 78,516ms | 73 | 4,496 | Whisper fallback (no embedded subs) |
| `video-clips-w-transcript` | 83.8s | 78,704ms | 74 | 4,548 | Transcript + base64 whole video |
| `video-summary-w-transcript` | 90.8s | 79,542ms | 86 | 4,660 | Transcript + 12-frame summary |
| `video-mosaic-w-transcript` | 94.3s | 79,522ms | 74 | 4,552 | Transcript + 5 mosaic grids |
| `video-frames-w-transcript` | 95.1s | 78,832ms | 89 | 5,266 | Transcript + 252 frames batched |
| `video-keyframes-w-transcript` | 96.2s | 80,099ms | 80 | 4,902 | Transcript + I-frame batches |
| `video-shots-w-transcript` | 118.0s | 79,167ms | 148 | 7,813 | Transcript + 76 shot frames |
| `video-shot-mosaic-w-transcript` | 161.8s | 82,765ms | 148 | 7,813 | Transcript + 76 shot mosaics |

## Full pipeline (accurate mode)

| Mode | Wall time | Output lines | Output chars | Output |
|---|---|---|---|---|
| **accurate** (mosaic + Whisper + LLM) | 89.8s | 6 | 5,258 | `## Summary` / `## Tags` / `## Scenes` / `## Transcript` |

## Observations

### Speed tiers

1. **Sub-2s** — `video-clips` (1.9s): Just reads and base64-encodes the file. No frame extraction.
2. **3–6s** — `video-chunks` (3.9s), `video-summary` (5.6s): Minimal frame extraction.
3. **7–11s** — `video-frames` (7.5s), `video-mosaic` (8.3s), `video-keyframes` (10.4s): Moderate frame extraction via ffmpeg.
4. **20–37s** — `video-shots` (20.0s), `video-shot-mosaic` (36.8s): Scene detection + per-shot extraction.
5. **83–162s** — All `-w-transcript` variants: Whisper dominates at ~78s for 252.7s audio.

### Key findings

- **Fastest visual encoder**: `video-clips` at 1.9s — sends raw video bytes, useful for models with native video support.
- **Best balance**: `video-summary` at 5.6s — scene-aware 12-frame summary, compact output.
- **Compact visual**: `video-mosaic` at 8.3s — 75 frames in 5 grid images, single message output.
- **Scene-aware**: `video-keyframes` (10.4s) is 2× faster than `video-shots` (20.0s) for finding visual boundaries — I-frames from the bitstream vs PySceneDetect.
- **Whisper cost**: ~78s fixed cost for 252.7s audio (0.31× realtime on M3 Max). This cost is identical across all `-w-transcript` variants — the difference in wall time is purely the visual encoder on top.
- **Captions fallback**: `video-captions` (83.1s) correctly falls back to Whisper when no embedded subtitle streams exist.
- **Accurate mode**: 89.8s total — mosaic + Whisper + LLM inference produces a structured 5,258-char document.

### Recommended usage

| Use case | Recommended encoder | Why |
|---|---|---|
| Quick visual overview | `video-summary` | 12 representative frames in 5.6s |
| Compact visual context | `video-mosaic` | 5 tiled grid images, 8.3s |
| Native video models | `video-clips` | Raw base64, 1.9s |
| Audio-first content | `video-transcript` | Audio-only, no frame overhead |
| Full understanding | `video-frames-w-transcript` | Frames + transcript, 95s |
| Scene-level analysis | `video-shots-w-transcript` | Per-shot frames + transcript |
| Maximum quality | `accurate` mode | Structured summary via LLM |

## CLI commands

```bash
# Visual-only encoders
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-clips        --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-chunks       --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-summary      --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-frames       --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-mosaic       --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-keyframes    --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-shots        --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-shot-mosaic  --no-cache

# Transcript-augmented encoders
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-transcript             --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-captions               --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-clips-w-transcript     --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-summary-w-transcript   --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-mosaic-w-transcript    --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-frames-w-transcript    --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-keyframes-w-transcript --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-shots-w-transcript     --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-shot-mosaic-w-transcript --no-cache

# Full pipeline
mm cat ~/data/mmbench-tiny/bakery.mp4 -m accurate --no-cache
```

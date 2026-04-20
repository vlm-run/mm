# Video Encoder Benchmark

**Date**: 2026-04-18
**Input**: `bakery.mp4` — 252.7s (4m 13s), 28.0 MB, 1280×720, h264+aac, 23.97 fps
**Profile**: `ollama` → gemma4:e2b (Gemma 4, effective 2B)
**Machine**: Apple M3 Max

## Results

| Encoder | Time | Throughput | Extracts | Output shape |
|---|---|---|---|---|
| `video-chunk` | 3.3s | 8.4 MB/s | 7 overlapping 60s chunks (20s overlap), 16 frames/chunk | `Video chunk 0 (0s – 60s)` × 7 |
| `frame-sample` | 5.6s | 5.0 MB/s | 252 frames at 1 fps, batched 16/message | `Video frames from bakery.mp4 (0.0s – 15.0s)` × 16 |
| `mosaic` | 7.0s | 4.0 MB/s | 75 frames → 5 mosaic grids (4×4 tiles) | `bakery.mp4 (4m13s) — 5 mosaic(s), 4×4 grid, 75 frames` |
| `shot-frames` | 18.0s | 1.6 MB/s | 76 shots via PySceneDetect, frames per shot | `Shot 1/76 of bakery.mp4 (0.0s – 6.8s)` × 76 |
| `shot-mosaic` | 33.1s | 866 KB/s | 76 shots, mosaic grid per shot | `Shot 1/76 of bakery.mp4 (0.0s – 6.8s)` × 76 |
| `video-frames-transcript` | 91.0s | 315 KB/s | Whisper transcript (72 segments, 598 words, 77s) + 16 frame batches | transcript + frames |
| **accurate** (mosaic + Whisper + LLM) | 83.0s | 345 KB/s | Full pipeline → structured summary, tags, scenes, transcript (869 words) | `## Summary` / `## Tags` / `## Scenes` / `## Transcript` |

## Observations

- **Fastest**: `video-chunk` at 3.3s — splits the timeline with minimal frame extraction.
- **Best visual coverage**: `shot-frames` / `shot-mosaic` detect 76 scene boundaries but cost 3–6× more than uniform sampling.
- **Whisper dominates transcript variants**: ~77s of the 91s `video-frames-transcript` time is Whisper transcription on the 4m 13s video.
- **Accurate mode** runs mosaic + Whisper + LLM inference in 83s total, producing a structured 869-word document with summary, tags, scene breakdown, and full transcript.
- `mosaic` is the sweet spot for encode-only: 75 frames compressed into 5 grid images in 7s.

## CLI commands used

```bash
mm profile use ollama

# Encode-only (no LLM) — each encoder
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-chunks     --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-frames      --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-mosaic      --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-shots       --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-shot-mosaic --no-cache
mm cat ~/data/mmbench-tiny/bakery.mp4 -p video-frames-w-transcript --no-cache

# Full pipeline (encode + Whisper + LLM)
mm cat ~/data/mmbench-tiny/bakery.mp4 -m accurate --no-cache
```

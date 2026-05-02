# PyAV VideoReader Migration Benchmark

**Date**: 2026-04-21
**Input**: `bakery.mp4` — 252.7s (4m 13s), 29.3 MB, 1280×720, h264+aac, 23.97 fps
**Machine**: Apple M3 Max
**Branch**: `video-encoders` (PyAV migration)
**Change**: Replaced all `ffmpeg`/`ffprobe` subprocess calls with in-process PyAV decoding

## Micro-benchmarks (pytest-benchmark, 3+ rounds)

Isolated comparison of individual video operations, PyAV vs ffmpeg subprocess.

| Operation | PyAV (ms) | ffmpeg CLI (ms) | Speedup |
|---|---:|---:|---:|
| **Probe duration** | 6.5 | 48.6 | **7.4×** |
| **16 frames extract** | 254.0 | 316.1 | **1.24×** |
| **16 frames + base64** | 308.2 | 466.1 | **1.51×** |
| **128 frame mosaic** | 1,684 | 3,254 | **1.93×** |
| **252 frames (1fps)** | 3,541 | 6,120 | **1.73×** |
| **Keyframes (all I-frames)** | 1,722 | — | (no subprocess baseline) |

Probe is **7.4× faster** because PyAV reads the container header in-process vs spawning
a `ffprobe` subprocess. Frame extraction is **1.2–1.9× faster** due to eliminating
subprocess overhead, temp file I/O, and JPEG re-encoding.

## Encoder-level benchmarks

End-to-end encoder wall times. Measured via direct Python API calls
(not CLI, to avoid TTY overhead). Each encoder produces the same output
format and content quality as before.

### Visual-only encoders (no audio)

| Encoder | Before (ms) | After (ms) | Speedup | Notes |
|---|---:|---:|---:|---|
| `video-clips` | 1,556 | 88 | **17.7×** | Just reads file; probe replaced with PyAV |
| `video-chunks` | 3,549 | 1,906 | **1.86×** | 7 chunks, 16 frames each (probe + frame extract) |
| `video-keyframes` | 10,084 | 1,978 | **5.10×** | Single-pass codec-level skip replaces ffprobe+ffmpeg |
| `video-summary` | 5,276 | 4,368 | **1.21×** | Scene detection + 12 frames |
| `video-frames` | 7,186 | 3,963 | **1.81×** | 252 frames at 1fps |
| `video-mosaic` | 7,988 | 4,512 | **1.77×** | 128 frames → Pillow tiling (was ffmpeg) |
| `video-shots` | 19,607 | 16,112 | **1.22×** | 76 shots × 8 frames (scene detection dominates) |
| `video-shot-mosaic` | 36,450 | 21,139 | **1.72×** | 76 shots × 16 frames + mosaic tiling |

### Transcript-augmented encoders

Whisper transcription (~78s) dominates all `-w-transcript` encoders. The visual
speedup from PyAV is masked by the fixed Whisper cost:

| Encoder | Before (ms) | After (ms) | Visual savings |
|---|---:|---:|---|
| `video-captions` | 78,516 | 79,878 | ~same (Whisper fallback, probing negligible) |
| `video-transcript` | 78,173 | — | No change (audio-only, no frame extraction) |
| All `-w-transcript` | ~79–83K | ~80–84K | Visual portion 1.2–5× faster, masked by Whisper |

## Architecture changes

### What changed

| Component | Before | After |
|---|---|---|
| **Metadata probe** | `ffprobe` subprocess (JSON parse) | `av.open()` container header read |
| **Frame extraction** | `ffmpeg -ss -i` per-frame subprocess | PyAV parallel seek+decode (ThreadPoolExecutor) |
| **Keyframe detection** | `ffprobe -show_frames` JSON parse → ffmpeg extract | `skip_frame='NONKEY'` single-pass decode |
| **Mosaic tiling** | `ffmpeg -filter_complex tile` subprocess | `Pillow Image.paste()` in-memory |
| **Subtitle probe** | `ffprobe -select_streams s` subprocess | `av.open()` stream type inspection |
| **Audio extraction** | ffmpeg subprocess (stream copy) | Kept as ffmpeg subprocess (stream-copy fastest) |
| **Segment extraction** | ffmpeg `-c copy` subprocess | Kept as ffmpeg subprocess (stream-copy fastest) |

### Why audio/segment stayed as subprocess

PyAV re-encoding is slower than ffmpeg's `-c copy` stream-copy for audio extraction
and segment cutting. These operations don't benefit from in-process decoding because
they don't decode individual frames — they just remux container bytes.

### Memory model

The new `FrameStream` API supports three consumption patterns to prevent OOM:

```python
# Iterate one frame at a time (constant memory)
for frame in reader.frames(timestamps, width=1024):
    process(frame)

# Materialize to list (bounded extractions)
frames = reader.frames(timestamps, width=1024).collect()

# Batch for encoder messages
for batch in reader.frames(timestamps, width=1024).batched(16):
    yield build_message(batch)
```

Internal batching (workers × 4 frames) bounds peak memory regardless of
total timestamp count.

## Files changed

| File | Change |
|---|---|
| `python/mm/video.py` | **New**: `VideoReader`, `Frame`, `FrameStream`, `VideoInfo`, `probe()`, `tile_to_mosaic()`, `extract_audio()`, `extract_segment()`, `probe_subtitle_streams()` |
| `pyproject.toml` | Added `av>=13.0` dependency |
| `python/mm/encoders/video/frames.py` | Migrated from `mm.ffmpeg` → `mm.video.VideoReader` |
| `python/mm/encoders/video/mosaic.py` | Migrated from `mm.ffmpeg` → `mm.video.VideoReader` + `tile_to_mosaic` |
| `python/mm/encoders/video/shots.py` | Migrated from `mm.ffmpeg` → `mm.video.VideoReader` |
| `python/mm/encoders/video/keyframes.py` | Migrated from ffprobe+ffmpeg → `VideoReader.keyframes()` |
| `python/mm/encoders/video/summary.py` | Migrated from `mm.ffmpeg` → `mm.video.VideoReader` |
| `python/mm/encoders/video/native.py` | Migrated probe → `mm.video.probe()`, kept `extract_segment` |
| `python/mm/encoders/video/captions.py` | Migrated subtitle probe → `mm.video.probe_subtitle_streams()` |
| `python/mm/encoders/video/_transcript.py` | Migrated `extract_audio` → `mm.video.extract_audio` |
| `python/mm/encoders/video/__init__.py` | Migrated `VideoFrameSample`, `VideoChunk` → `mm.video.VideoReader` |
| `python/mm/encoders/video/shot.py` | Thin delegate to new `shots.py` |
| `python/mm/encoders/video/frame_sample_transcript.py` | Thin delegate to new `frames.py` |
| `python/mm/encoders/gemini.py` | Migrated probe + segment → `mm.video` |
| `python/mm/encoders/audio.py` | Migrated `extract_audio`, probe → `mm.video` |
| `python/mm/commands/cat.py` | Migrated accurate video pipeline → `mm.video` |
| `python/mm/store/embed.py` | Migrated probe + segment → `mm.video` |
| `tests/python/test_video_reader.py` | **New**: 24 unit tests + 11 benchmark tests |
| `tests/python/test_video_encoders.py` | Updated for new API (`Frame.encode_jpeg`) |

## Summary

- **Zero `mm.ffmpeg` imports remaining** — all video processing routes through `mm.video`
- **Probe: 7.4× faster** (6.5ms vs 49ms)
- **Keyframes: 5.1× faster** (2.0s vs 10.1s) — biggest win from codec-level skip
- **Clips: 17.7× faster** (88ms vs 1,556ms) — probe-only path, no frame extraction
- **Frame extraction: 1.2–1.9× faster** across all encoders
- **Mosaic tiling: 1.7–1.9× faster** — Pillow in-memory vs ffmpeg subprocess
- **No temp files** for frame extraction — PIL Images stay in memory
- **All 21 encoders** registered and working, including legacy aliases
- **30 tests passing** (24 unit + 6 encoder registration)

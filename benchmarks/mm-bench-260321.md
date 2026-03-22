# Benchmark: 2026-03-21

**Dataset**: ~/data/mmbench-mini (45 files, 588MB)
**System**: macOS, Apple Silicon, Ollama qwen3.5:0.8b, MLX whisper tiny
**Config**: beam_size=1 (greedy), audio_speed=2.0, mosaic 1500px

## Video L2 Pipeline (--mode fast)

| Video | Duration | Total | Realtime | VLM | Transcription | Frames |
|---|---|---|---|---|---|---|
| gemini_intro.mp4 | 2m 52s | 4.0s | 43x | 3.7s | 1.2s | 301ms |
| bakery.mp4 | 4m 13s | 4.8s | 53x | 4.3s | 1.6s | 430ms |
| how_to_build_an_mvp.mp4 | 16m 53s | 5.0s | 203x | 2.9s | 3.1s | 332ms |
| google_next_2025_keynote.mp4 | 100m 4s | 25.5s | 235x | 8.2s | 20.5s | 408ms |

Architecture: `(visual → VLM) ∥ (audio → transcription)`, concat output.

## Optimization History

| Step | Total (17min video) | Realtime | Change |
|---|---|---|---|
| Baseline (CTranslate2 CPU, beam=5, sequential) | 39.8s | 25x | — |
| + greedy beam=1 | 28.1s | 36x | 1.5x faster decoding |
| + MLX Metal GPU | 10.5s | 97x | 5.9x faster transcription |
| + parallel visual ∥ audio | 9.9s | 102x | overlap extraction |
| + decoupled VLM (no transcript in prompt) | 5.0s | 203x | full parallelism |

## Image L2

| Mode | Latency | Tokens (prompt→completion) |
|---|---|---|
| fast | ~2.3s | 364→50 |
| accurate | ~2.6s | 364→200 |

## L0 Metadata (45 files, 588MB)

| Command | Latency | Throughput |
|---|---|---|
| find . | 4.8ms | 1.03 Tbps |
| wc . | 3.9ms | 1.28 Tbps |
| sql GROUP BY kind | 11.2ms | 441 Gbps |

## L1 Content Extraction

| Command | Latency | Throughput |
|---|---|---|
| cat \<image\> | 0.09ms | 13.1 Gbps |
| cat \<image\> (x20) | 2.4ms | 33.4 Gbps |
| cat \<audio\> (441MB) | 43.9ms | 80.3 Gbps |
| cat \<video\> (35.6MB) | 60ms | 4.98 Gbps |
| cat \<pdf\> (x10) | 700ms | 173 Mbps |

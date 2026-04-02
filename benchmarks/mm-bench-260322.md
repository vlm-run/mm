# Benchmark: mm-bench-260322

**Dataset**: ~/data/mmbench-mini (47 files, 1.1GB)
**System**: macOS Apple Silicon, Ollama qwen3.5:0.8b, MLX whisper tiny
**Config**: beam_size=1, audio_speed=2.0, mosaic 1500px, parallel VLM ∥ whisper

## L0 — Metadata (Rust parallel scan)

| Command | Latency | Throughput |
|---|---|---|
| find . | 3.8ms | 2.36 Tbps |
| wc . | 3.5ms | 2.62 Tbps |
| sql GROUP BY kind | 11.1ms | 812 Gbps |
| sql SUM(size) BY kind | 10.8ms | 834 Gbps |
| sql TOP 10 largest | 10.4ms | 866 Gbps |
| sql GROUP BY ext | 11.1ms | 815 Gbps |
| find --kind image | 3.6ms | 2.53 Tbps |
| find --kind audio | 4.3ms | 2.08 Tbps |
| find --kind document | 3.8ms | 2.37 Tbps |

## L1 — Content Extraction

| Command | Latency | Throughput |
|---|---|---|
| cat \<image\> | 0.1ms | 12.0 Gbps |
| cat \<image\> (x20) | 2.3ms | 33.4 Gbps |
| cat \<audio\> | 43.6ms | 81.0 Gbps |
| cat \<video\> | 649ms | 6.3 Gbps |
| cat \<pdf\> | 62.3ms | 200 Mbps |
| cat \<pdf\> (x10) | 695ms | 174 Mbps |
| grep /pattern/ | 257ms | 484 Mbps |

## L2 — Semantic (LLM/VLM)

| Command | Latency | Throughput | Tokens (in→out) |
|---|---|---|---|
| cat \<image\> fast | 1.1s | 1.09 Mbps | 2032→68 |
| cat \<image\> accurate | 9.6s | 124 kbps | 2065→359 |
| cat \<video\> fast | 30.0s | 136 Mbps | 1329→178 |
| cat \<video\> accurate | 282s | 14.5 Mbps | 9953→2048 |
| cat \<audio\> fast | 14.5s | 243 Mbps | 854→109 |
| cat \<audio\> accurate | 79.0s | 44.7 Mbps | 3401→231 |

## Changes from mm-bench-260321

- Token metrics now captured for all L2 commands
- Audio L2 benchmarks use smallest audio file (Palantir 61MB/43min) instead of Lex Fridman (441MB/5hr) to avoid Metal GPU timeout
- Global LlmUsage tracker wired into bench pipeline
- Benchmark naming: `mm-bench-YYYYMMDD` convention

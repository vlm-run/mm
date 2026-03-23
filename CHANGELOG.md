# Changelog

## [Unreleased]

### Performance
- Video L2 fast: 203x realtime (17min video in 5.0s) on Apple Silicon
- 100min Google Next keynote: 235x realtime (25.5s)
- Whisper MLX Metal: 5.9x faster than CTranslate2 CPU
- Greedy decoding (beam=1): 1.5x faster than beam=5, no quality loss
- Parallel pipeline: (visual → VLM) ∥ (audio → transcription)
- Benchmark mm-bench-260321: 24 commands on mmbench-mini (47 files, 1.1GB)
  - See `benchmarks/mm-bench-260321.md`

### Added
- `--mode fast|accurate` for per-modality L2 extraction strategies
- Image: fast (10 words + 5 tags) / accurate (200 words + 10 tags + objects)
- Video: parallel mosaic (4x4 @ 1500px) + audio transcription → VLM + transcript concat
- Audio: ffmpeg 2x speed + whisper tiny (MLX Metal GPU on macOS)
- Document: docling PDF/DOCX/PPTX → markdown with pypdfium2 fallback
- Whisper backend auto-select: MLX Metal GPU > CTranslate2 CPU/CUDA
- `~/.config/mm/mm.toml` config with `[mode.fast]` / `[mode.accurate]` sections
- `beam_size` config (fast=1 greedy, accurate=5 beam search)
- Token metrics (prompt→completion) in LLM/VLM output footers
- `mm bench` with 24 commands (L0×10, L1×8, L2×6), bits/s throughput
- `sysinfo.py` — system capability detection (ffmpeg, GPU, optional deps)
- `scenes.py` — PySceneDetect wrapper with uniform scene sampling
- `docling_extract.py` — docling document conversion wrapper
- 271 Python tests (44 new for modal extraction)

### Changed
- Mosaic resolution: 160px → 375px per tile (1500px wide mosaic)
- Config path: `~/.mm/config.toml` → `~/.config/mm/mm.toml` (XDG, legacy supported)
- `--json` flag → `--format json|tsv|csv` across all commands
- `whisper_transcription_ms` → `audio_transcription_ms` in timing output
- File kind `"pdf"` → `"document"` (includes DOCX, PPTX)

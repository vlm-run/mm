# Changelog

## [Unreleased]

## [0.14.0] - 2026-07-15

### Breaking changes
- **Encoder renames (no backward-compat aliases):** the following encoder names
  were renamed for cross-modality consistency. Custom pipelines referencing the
  old names by `strategy:` will now raise `KeyError` — update to the new names.
  - `base64` → `native` (audio)
  - `gemini` → `gemini-native` (audio, video, document)
  The shipped default pipelines (`fast.yaml` / `accurate.yaml`) are unaffected.
- **New `native` video encoder:** base64 `video_url` passthrough — the
  OpenAI-compatible counterpart to `gemini-native`.

### Added
- `--stream` flag on `cat` for token-by-token LLM output to stdout (#158)
- Global `--debug` flag enabling Python `mm` logger (DEBUG) + Rust `RUST_LOG=debug` tracing (#168)
- `mm config doctor` environment health check (ffmpeg, config, db, profile endpoint, Whisper, Python) (#169)
- Disk-backed cache for `detect_scenes` + `transcript_messages` via
  `mm.cache.memoize_file(path=...)` (`FSLRUCache` under `$MM_CACHE_DIR`).
  `detect_scenes`: 3,080 ms cold → 0.2 ms warm cross-process (~12,000×);
  `transcript_messages`: ~76 s cold → ~5 ms warm. mtime/size fingerprint
  invalidation; 9 new `TestDiskBackedCache` tests.
- `memoize_file` added to auto-strategy (#160)
- Centralized cache/storage/db paths via pydantic-settings for test/benchmark isolation (#163)

### Changed
- Video encoder P0 speedups across all 17 video encoders (#177):
  `Frame.reformat()` (libswscale) replaces `PIL.Image.resize` (2.9× per-frame);
  JPEG default subsampling 4:4:4 → 4:2:0 (1.7× encode, ~30% smaller);
  `mosaic` streams via `.batched()`; `shots*` bundle per-shot timestamps into
  one parallel decode pass; Whisper runs concurrently with visual extraction.
  Cold-cache median win: visual-only −18%, with-transcript −10%.
  Warm-cache chained `-w-transcript` calls drop >95%.
- Auto-strategy workflow cleanup: dedup, type coercion, dry-run label (#166)
- `httpx` declared as explicit dependency (#167)
- Documentation consolidated and grounded with code (#170, #161)
- OSS-readiness cleanup: scrubbed dev tunnel URL, local paths, stale bench data (#175)
- Removed stale `web/` and `benchmarks/results/` artefacts (#178)
- Added `CONTRIBUTING.md` for public contributors (#176)

### Performance
- **Disk-backed cache for `detect_scenes` + `transcript_messages` (260430)**:
  the slow steps in the accurate-mode video pipeline now persist across CLI
  invocations via `cachetools_ext.fs.FSLRUCache`. Implemented as an opt-in
  `path=` parameter on `mm.cache.memoize_file` so cheap helpers (`probe`)
  stay process-local while the expensive ones graduate to disk.
  - `detect_scenes`: 3,080 ms cold → **0.2 ms warm cross-process** (~12,000×).
  - `transcript_messages`: ~76 s cold → ~5 ms warm cross-process (Whisper
    pickle on bakery.mp4) — turns the second `mm cat video.mp4 -m accurate`
    into a near-instant operation.
  - mtime/size fingerprint invalidates entries automatically when the source
    file is re-encoded, so stale cache hits aren't possible.
  - Cache lives under `$MM_CACHE_DIR` → `$XDG_CACHE_HOME/mm` → `~/.cache/mm`.
    Tests pin `MM_CACHE_DIR` to a session temp dir via `conftest.py`.
  - Backed by 9 new `TestDiskBackedCache` tests in `test_cache.py` covering
    persistence across decorator instances, lazy `MM_CACHE_DIR` resolution,
    mtime invalidation on disk, and `cache_clear()` wiping the directory.
- **Video encoders P0 (260429)**: unified speedups across all 17 video encoders.
  See `benchmark/260429-post-p0-video-encoders.md`.
  - `Frame.reformat()` (libswscale) replaces `PIL.Image.resize` — 2.9× per-frame.
  - JPEG default subsampling 4:4:4 → 4:2:0 — 1.7× JPEG encode, ~30% smaller.
  - `mosaic` streams frames via `.batched()`; `shots*` bundle per-shot
    timestamps into one parallel decode pass (single ThreadPoolExecutor for all
    76 shots, was one per shot).
  - Process-local LRU caches for `probe()`, `detect_scenes()`, transcript —
    chained encoders against the same file pay each cost exactly once per process.
  - Whisper now runs concurrently with visual extraction (Metal GPU + CPU);
    `-w-transcript` wall time = `max(visual, whisper)` not sum.
  - Cold-cache median win: visual-only **−18%**, with-transcript **−10%**.
  - Warm-cache real-pipeline win: chained `-w-transcript` calls drop **>95%**
    (e.g. `keyframes-w-transcript` 80.5s → 1.4s when transcript cached).
  - Correctness covered by `tests/python/test_video_p0.py` (32 tests covering
    resize visual fidelity, JPEG subsampling, cache invalidation on mtime
    change, transcript-first message ordering, parallel-execution timing,
    and cross-encoder cache reuse).
- Video fast mode: 203x realtime (17min video in 5.0s) on Apple Silicon
- 100min Google Next keynote: 235x realtime (25.5s)
- Whisper MLX Metal: 5.9x faster than CTranslate2 CPU
- Greedy decoding (beam=1): 1.5x faster than beam=5, no quality loss
- Parallel pipeline: (visual → VLM) ∥ (audio → transcription)
- Benchmark mm-bench-260321: 24 commands on mmbench-mini (47 files, 1.1GB)
  - See `benchmarks/mm-bench-260321.md`

### Added
- `--mode fast|accurate` for per-modality extraction pipelines
- Image: fast (10 words + 5 tags) / accurate (200 words + 10 tags + objects)
- Video: parallel mosaic (4x4 @ 1500px) + audio transcription → VLM + transcript concat
- Audio: ffmpeg 2x speed + whisper tiny (MLX Metal GPU on macOS)
- Document: PDF text extraction via pypdfium2, DOCX/PPTX/XLSX via libreoffice-rs
- Whisper backend auto-select: MLX Metal GPU > CTranslate2 CPU/CUDA
- `~/.config/mm/mm.toml` config with `[mode.fast]` / `[mode.accurate]` sections
- `beam_size` config (fast=1 greedy, accurate=5 beam search)
- Token metrics (prompt→completion) in LLM/VLM output footers
- `mm bench` with 24 commands across metadata, fast, and accurate modes, bits/s throughput
- `sysinfo.py` — system capability detection (ffmpeg, GPU, optional deps)
- `scenes.py` — PySceneDetect wrapper with uniform scene sampling
- 271 Python tests (44 new for modal extraction)

### Changed
- Mosaic resolution: 160px → 375px per tile (1500px wide mosaic)
- Config path: `~/.mm/config.toml` → `~/.config/mm/mm.toml` (XDG, legacy supported)
- `--json` flag → `--format json|tsv|csv` across all commands
- `whisper_transcription_ms` → `audio_transcription_ms` in timing output
- File kind `"pdf"` → `"document"` (includes DOCX, PPTX)

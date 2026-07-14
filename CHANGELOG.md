# Changelog

## [Unreleased]

### Changed
- **Document accurate mode now uses gateway `glm-ocr` via `document_url`**:
  the `document/accurate` pipeline ships a new `document-url` encoder that sends
  the whole document to the VLM Run gateway as a single OpenAI-style
  `document_url` content part (base64 `data:` URI), pinned to the `glm-ocr`
  model for server-side OCR → markdown. This replaces the previous
  client-side `page-text` → generic-LLM markdown path and adds support for
  scanned/image-only PDFs that `page-text` cannot read. Office docs
  (`.docx`/`.pptx`/…) in accurate mode are converted to PDF first and follow
  the same path. Fast mode is unchanged (local `page-text`, no network).
  - New encoder `document-url` (`python/mm/encoders/document/document_url.py`),
    registered for `kind=document` and surfaced in `mm cat --list-encoders`.
  - `pipelines/document/accurate.yaml` now pins `encode.strategy: document-url`
    and `generate.model: glm-ocr`.
  - Covered by `TestDocumentUrlEncoder` in `tests/python/test_encoders.py`
    (part shape + accurate-default wiring).

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

# Changelog

## [Unreleased]

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
- Typed library result types in `mm.results`, re-exported from `mm`: `WcStats`, `GrepMatch`, `GrepResult`, `CatResult` (plus `FileMetadata`). Each has `to_dict()` for serialization.
- `Context.to_records()` — storage-agnostic export (one dict per file/item, `session_id`/`ref_id` when `refs=True`); the persistence-decoupling entry point.
- `test_library_surface.py` — CI guard asserting the public library surface stays fully implemented (no `NotImplementedError`), importable, and callable in both `Context` modes.

### Changed
- Mosaic resolution: 160px → 375px per tile (1500px wide mosaic)
- Config path: `~/.mm/config.toml` → `~/.config/mm/mm.toml` (XDG, legacy supported)
- `--json` flag → `--format json|tsv|csv` across all commands
- `whisper_transcription_ms` → `audio_transcription_ms` in timing output
- File kind `"pdf"` → `"document"` (includes DOCX, PPTX)
- **Library is now the source of truth; the CLI is a thin presentation surface.** All core computation lives in the library (`mm.stats.compute_wc`, `mm.peek.FileMetadata`, `mm.cat_utils.extract.extract`, `mm.search.search_content`, `Context.filter`/`print_tree` layouts); each command parses options → resolves stdin → calls the library → renders. Hot paths preserve perf via dependency injection (callers pass pre-built `scanner=`/`files=`/`regex=`).
- **Persistence is decoupled from the library.** `Context` has no `save()` method and no database awareness; callers export via `Context.to_records()` and own their storage backend. The mm CLI writes to its SQLite store via `MmDatabase().upsert_records(...)` as one such caller.
- `Context.resolve()` / the cross-session `Context.get(...)` classmethod were removed. `Context.get(ref)` now resolves in-memory role-aware refs only; cross-session lookup is caller-owned (e.g. `MmDatabase().resolve("<session>/<ref>")`).
- `Context.grep` now uses smart-case matching (shares the CLI's single code path); pass a precompiled `regex=` or include an uppercase char to force case-sensitive.

# vlmctx Spec

> High-performance multi-modal context management. Rust core, Python API, Unix CLI.

Legend: `[x]` implemented, `[ ]` roadmap, `[~]` partial/stubbed

```
vlmctx
├── L0 — Metadata (Rust core, ~0.02ms/file)
│   ├── [x] Parallel directory walk (ignore crate + per-thread batching, zero lock contention)
│   ├── [x] Gitignore-aware (.gitignore, .git/info/exclude, global)
│   ├── [x] 14-column Arrow schema (path, name, stem, ext, size, modified, created, mime, kind, is_binary, depth, parent, width, height)
│   ├── [x] 9 file kind variants (code, image, document, video, audio, data, config, text, other)
│   ├── [x] Extension-based classification (~100+ extensions mapped)
│   ├── [x] MIME inference via mime_guess
│   ├── [x] Binary detection (extension + kind heuristics)
│   ├── [x] Parallel image dimension enrichment (rayon, header-only reads)
│   ├── [x] CompactString for all string fields (SSO, no heap for short paths)
│   ├── [x] Arrow RecordBatch builder with typed column builders
│   ├── [x] Parquet I/O (ZSTD level 3 compression)
│   └── [x] Manifest-based incremental cache (mtime + size staleness check)
│
├── L1 — Content Extraction (Rust extractors + Python ffmpeg)
│   ├── Code / Text / Config
│   │   ├── [x] Line count, word count
│   │   ├── [x] Text preview (first 500 chars)
│   │   ├── [x] Content hash (xxh3, full file)
│   │   └── [x] Language detection (~30 languages from extension)
│   ├── Images
│   │   ├── [x] Dimensions (WxH, header-only via mmap)
│   │   ├── [x] Content hash (xxh3 via mmap, zero-copy)
│   │   ├── [x] Magic-byte MIME detection (infer crate)
│   │   └── [x] EXIF extraction (camera, date, GPS lat/lon, orientation)
│   ├── Video
│   │   ├── [x] Native MP4/MOV parsing (mp4parse crate, no subprocess)
│   │   ├── [x] Native MKV/WebM parsing (matroska crate, no subprocess)
│   │   ├── [x] Resolution, duration, FPS, codec, audio codec, has_audio
│   │   ├── [x] Content hash (xxh3 via mmap)
│   │   ├── [x] Keyframe mosaic extraction (ffmpeg -skip_frame nokey, single-pass, ~5000x realtime)
│   │   ├── [x] Scene-change mosaic extraction (ffmpeg select='gt(scene,T)', full decode)
│   │   ├── [x] Configurable tile grid (COLSxROWS), thumb width, JPEG quality
│   │   └── [ ] Optical flow / motion summary (mpdecimate)
│   ├── Audio
│   │   ├── [x] Audio extraction at Nx speed (atempo, chained for >2x)
│   │   ├── [x] Mono 16kHz PCM downmix (Whisper-optimized)
│   │   ├── [x] Configurable output format (wav, mp3, flac)
│   │   └── [ ] Pure-Rust audio metadata via symphonia (mp3, flac, ogg)
│   ├── Documents (PDF)
│   │   ├── [x] Text extraction via pypdfium2 (Python CLI side)
│   │   ├── [x] Page-by-page extraction
│   │   ├── [x] PDF page mosaic grids (pypdfium2 render → Pillow tile, ~10ms/page)
│   │   ├── [x] Configurable tile grid, thumbnail width, max pages, JPEG quality
│   │   └── [~] Rust-side PDF extraction (currently returns raw bytes, not text)
│   └── Hashing
│       ├── [x] fast_fingerprint — partial hash (first+last 64KB + size), ~33x faster on 10MB
│       ├── [x] full_hash_mmap — full xxh3 via mmap, zero-copy
│       └── [x] full_hash_read — streaming fallback for special files
│
├── L2 — Semantic Understanding (LLM-powered)
│   ├── [x] OpenAI-compatible API client (urllib, no deps)
│   ├── [x] Image captioning (base64 vision API)
│   ├── [x] File content description
│   ├── [x] Configurable via VLMCTX_LLM_BASE_URL / API_KEY / MODEL env vars
│   ├── [x] Graceful fallback to L1 when unconfigured
│   ├── [ ] Video understanding via keyframe mosaic + VLM (qwen3-2b inference)
│   ├── [ ] Audio transcription via Whisper on 2x-speed extraction
│   └── [ ] Embedding generation (SemanticAnalyzer trait defined, not implemented)
│
├── Python API (Context class)
│   ├── [x] L0 scan on construction (~5ms for 249 real files)
│   ├── [x] to_polars() — zero-copy Arrow → Polars
│   ├── [x] to_pandas() — Arrow → Pandas
│   ├── [x] to_arrow() — raw PyArrow Table
│   ├── [x] sql(query) — DuckDB SQL against 'files' table
│   ├── [x] filter(kind, ext, min_size, max_size) — chainable, returns new Context
│   ├── [x] cat(path, level) / head(path, n) / tail(path, n)
│   ├── [x] grep(pattern, kind) — regex search across file contents
│   ├── [x] show(limit, columns) — Rich table display
│   ├── [x] info() — Rich summary panel
│   └── [x] save() — persist to .vlmctx/index.parquet
│
├── CLI Commands (Typer, Unix-philosophy composability)
│   ├── [x] find     — find files by kind/ext/size/depth (like fd)
│   ├── [x] ls       — tabular listing with metadata (like eza)
│   ├── [x] cat      — semantic content display at L0/L1/L2 (like bat)
│   ├── [x] head     — first N lines/pages
│   ├── [x] tail     — last N lines/pages
│   ├── [x] grep     — content search with context lines (like rg)
│   ├── [x] sql      — DuckDB SQL on file index
│   ├── [x] describe — column schema introspection (like DESCRIBE TABLE)
│   ├── [x] info     — directory summary statistics panel
│   ├── [x] keyframes — video keyframe mosaic extraction (--strategy keyframe|scene)
│   ├── [x] audio    — audio extraction at Nx speed for transcription
│   ├── [x] wc       — count files, bytes, lines, estimated tokens (LLM budgeting)
│   ├── [x] tree     — hierarchical directory tree with sizes (like tree + du)
│   ├── [x] pages    — PDF page mosaic extraction (visual document snapshots)
│   └── [ ] context  — LLM-ready context payload builder (token budgeting)
│
├── Output Modes
│   ├── [x] TTY stdout → Rich formatted tables/panels with color
│   ├── [x] Piped stdout → plain TSV/text (machine-readable, no ANSI)
│   ├── [x] --json flag → JSON on any command
│   ├── [x] Piped stdin → read newline-delimited paths (composability)
│   └── [x] Pipe detection via select() (no blocking on empty stdin)
│
├── Data Transfer (Rust → Python)
│   ├── [x] Arrow IPC serialization (RecordBatch → bytes → pyarrow.ipc.open_stream)
│   ├── [x] Rust-native JSON (serde_json, bypasses Arrow+pyarrow for --json paths)
│   ├── [x] Rust-native filtered/sorted output (kind, ext, size, sort, limit — all in Rust)
│   ├── [x] Zero-copy to Polars (polars.from_arrow)
│   ├── [x] DuckDB in-process SQL on Arrow tables
│   └── [~] PyCapsule FFI (abandoned — compatibility issues with pyarrow)
│
├── Performance
│   ├── L0 walk: ~5ms / 1K files, ~16ms / 10K files
│   ├── L0 full pipeline: ~7ms / 1K mixed files (with image dims)
│   ├── L0 real data: ~5ms / 249 files (~/data/1-demo)
│   ├── CLI cold start: ~58ms (ls --json, find --json via Rust fast path)
│   ├── CLI cold start: ~66ms (ls/find with Rich TTY output)
│   ├── L1 code extraction: ~8μs/file
│   ├── L1 image extraction: ~18μs/file (mmap)
│   ├── L1 video metadata (native): ~10ms (6.4MB MP4, includes hash)
│   ├── Partial hash 10MB: ~19μs (vs 610μs full, 33x speedup)
│   ├── Keyframe mosaic (86min video): ~820ms → 5 mosaic grids
│   ├── PDF page mosaic (68 pages): ~280ms → 2 mosaic grids
│   └── Audio 2x (163s video): ~200ms → 2.5MB Whisper-ready WAV
│
├── Tests
│   ├── Rust: 65 tests (meta, walk, detect, schema, table, code, image, video, hash)
│   ├── Python: 132 tests (CLI, Context API, pipe, L0 metadata, L1 extraction, benchmarks)
│   ├── Criterion benchmarks: l0_walk, l0_index, hash_strategies, l1_extract
│   ├── pytest-benchmark: 11 benchmarks (L0, L1, ffmpeg, e2e)
│   └── hyperfine CLI: bench_cli.sh (find, ls, sql, cat, keyframes, audio)
│
└── Build & Tooling
    ├── [x] Maturin build backend (Rust → Python wheel)
    ├── [x] PyO3 stable ABI (abi3-py310)
    ├── [x] uv for all Python operations (venv, pip, run)
    ├── [x] Makefile targets (develop, test, bench, lint, fmt)
    ├── [x] Rust edition 2024, stable toolchain + clippy + rustfmt
    └── [x] Dev deps: ruff, mypy, pytest, pytest-benchmark, criterion
```

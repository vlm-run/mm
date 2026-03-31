# mm Spec

> High-performance multi-modal context management. Rust core, Python API, Unix CLI.

Legend: `[x]` implemented, `[ ]` roadmap, `[~]` partial/stubbed

```
mm
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
│   ├── [x] OpenAI Python SDK (openai>=1.0, any compatible API)
│   ├── [x] Image captioning (base64 vision API)
│   ├── [x] File content description
│   ├── [x] Video understanding via keyframe mosaic + LLM (auto at L2)
│   ├── [x] Audio description via metadata + LLM (auto at L2)
│   ├── [x] Configurable via profiles: mm config profile add/update/use
│   ├── [x] think=false + reasoning_effort="none" + temperature=0.1
│   ├── [x] L2 errors propagate directly (no silent fallback to L1)
│   ├── [x] --mode fast|accurate per-modality extraction strategies
│   ├── [x] Audio transcription via ffmpeg + whisper (2x speed, greedy beam=1)
│   ├── [x] Whisper backend auto-select: MLX Metal GPU > CTranslate2 CPU/CUDA
│   ├── [x] Parallel visual + audio extraction (ThreadPoolExecutor)
│   ├── [x] Video: mosaic (4x4 @ 1500px) + transcript → LLM markdown
│   ├── [x] Image: fast (10 words + 5 tags) / accurate (200 words + 10 tags + objects)
│   ├── [x] Document extraction via docling (PDF/DOCX/PPTX → markdown)
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
│   └── [x] save() — persist to .mm/index.parquet
│
├── CLI Commands (5 + config, Typer, Unix-philosophy composability)
│   ├── [x] find     — find/list files, tree view (--tree), schema (--schema), columns (--columns)
│   ├── [x] cat      — auto-detected content extraction at L0/L1/L2
│   │   ├── [x] head/tail via -n (replaces old head/tail commands)
│   │   ├── [x] --mode fast|accurate (L2 modal extraction)
│   │   ├── [x] video L2: parallel mosaic + whisper → LLM (102x realtime)
│   │   ├── [x] audio L2: ffmpeg 2x + whisper → LLM transcript summary
│   │   ├── [x] image L2: fast (10w+5tags) / accurate (200w+10tags+objects)
│   │   ├── [x] document L2: docling PDF/DOCX/PPTX → markdown → LLM
│   │   └── [x] --mosaic-*, --audio-* namespaced flags
│   ├── [x] grep     — content search with context lines (like rg)
│   ├── [x] sql      — DuckDB SQL on file index
│   ├── [x] wc       — count files, bytes, lines, estimated tokens
│   ├── [x] config   — LLM provider management (show, init, set)
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
│   ├── CLI cold start: ~58ms (find --format json via Rust fast path)
│   ├── CLI cold start: ~66ms (find with Rich TTY output)
│   ├── L1 code extraction: ~8μs/file
│   ├── L1 image extraction: ~18μs/file (mmap)
│   ├── L1 video metadata (native): ~10ms (6.4MB MP4, includes hash)
│   ├── Partial hash 10MB: ~19μs (vs 610μs full, 33x speedup)
│   ├── Keyframe mosaic (86min video): ~820ms → 5 mosaic grids
│   ├── PDF page mosaic (68 pages): ~280ms → 2 mosaic grids
│   ├── Audio 2x (163s video): ~200ms → 2.5MB Whisper-ready WAV
│   ├── L2 video (17min, fast mode): ~9.9s total = 102x realtime
│   │   ├── Visual: 16 frames + 4x4 mosaic @ 1500px — 375ms (parallel)
│   │   ├── Audio: ffmpeg 2x + whisper tiny MLX Metal — 3.0s (parallel)
│   │   ├── LLM: qwen3.5:0.8b mosaic+transcript → markdown — 5.2s
│   │   └── Optimization path: beam=5→1 (1.5x), CTranslate2→MLX (5.9x), parallel (6%)
│   ├── L2 image (fast): ~1.0s (qwen3.5:0.8b, Ollama local)
│   └── L2 image (accurate): ~2.6s (qwen3.5:0.8b, Ollama local)
│
├── Tests
│   ├── Rust: 65 tests (meta, walk, detect, schema, table, code, image, video, hash)
│   ├── Python: 271 tests (CLI, Context API, pipe, L0/L1/L2, config, whisper, scenes, docling, bench)
│   ├── Criterion benchmarks: l0_walk, l0_index, hash_strategies, l1_extract
│   ├── mm bench: 24 commands (L0×10, L1×8, L2×6) with bits/s throughput
│   └── pytest-benchmark: 11 benchmarks (L0, L1, ffmpeg, e2e)
│
└── Build & Tooling
    ├── [x] Maturin build backend (Rust → Python wheel)
    ├── [x] PyO3 stable ABI (abi3-py310)
    ├── [x] uv for all Python operations (venv, pip, run)
    ├── [x] Makefile targets (develop, test, bench, lint, fmt)
    ├── [x] Rust edition 2024, stable toolchain + clippy + rustfmt
    └── [x] Dev deps: ruff, mypy, pytest, pytest-benchmark, criterion
```


For each modality (image, video, documents like PDFs), I’d like to have a few different strategies to extract metadata/semantics with varying degrees of detail/mode. For example: 
- image: 
    - mode=fast -> describe the image in 10 words or less, and extract 5-keyword tags 
    - mode=accurate -> describe the image in detail (200 words) + extract up to 10-keyword tags + extract up to 10-objects/people/faces/logos in the image
- documents: (PDFs, Word documents, etc.)
    - simply consider using docling pdf/docx/pptx -> markdown for now
    - ignore image/video/audio as we have other ways to extract metadata/semantics for them (detailed extraction is not needed)
- audio: 
    - mode=fast
        - Audio transcription collected via ffmpeg + whisper tiny (with audio sped up by 2x)
    - mode=accurate
        - Audio transcription collected via ffmpeg + whisper medium (no speed up)
- video: 
    - mode=fast
        - If video is <5min: no shot detection, simply sample 16 keyframes uniformly across the video, create a single image mosaic (4x4) grid as an image and make a request with audio transcription collected via ffmpeg + whisper tiny (audio sped up by 2x)
        - 1hr: shot detection with pyscenedetect, uniformly sample 16 shots from the entire video, create a single image mosaic (4x4) + ffmpeg and whisper tiny based audio transcription (at 2x speed)
    - mode=accurate
        - Shot detection with pyscenedetect, uniformly sample 8*16=128 shots from the entire video, create 8 4x4 mosaic images and make a request with audio transcription collected via ffmpeg + whisper medium
    - collect (sys info, ffmpeg + GPU)

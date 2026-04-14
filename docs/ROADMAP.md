# mm Roadmap

> Make every multi-modal directory instantly queryable. Speed is the feature.

Design principle: **70-80% semantic coverage at 1000x the speed of full VLM inference.**
Same philosophy as `fast_fingerprint` — trade marginal precision for orders-of-magnitude speedup.

```
mm roadmap
│
├── P0 — Sub-100ms Everything (DX + Speed)
│   │
│   │   The goal: every CLI command feels instant. No command should take
│   │   longer than 100ms wall-clock for <10K files. Iteration speed is
│   │   the single biggest value-add over alternatives.
│   │
│   ├── Persistent index with incremental rebuild
│   │   ├── Write .mm/index.parquet on first scan (~already exists)
│   │   ├── On subsequent runs: stat() only changed files (mtime+size)
│   │   ├── Merge changed entries into existing RecordBatch (no full rescan)
│   │   ├── Target: <2ms for 1K files when nothing changed (vs 5ms full scan)
│   │   └── Invalidation: hash .gitignore mtime into manifest
│   │
│   ├── [DONE] JSON output in Rust (bypass pyarrow entirely)
│   │   ├── Scanner.to_json_fast() — serde_json with filtering/sorting in Rust
│   │   ├── Scanner.to_lines_fast() — newline-delimited paths, filtered in Rust
│   │   ├── Eliminated 35ms pyarrow import for --format=json and piped paths
│   │   ├── CLI find/ls with --format=json: ~60ms cold start (was 330ms, 5.5x speedup)
│   │   └── Arrow path preserved for DataFrame/SQL/Rich display use cases
│   │
│   ├── Parallel fast-mode batch extraction
│   │   ├── extract_fast_batch(paths) — rayon parallel across files
│   │   ├── All 17 demo videos: 5.1s sequential → <1s parallel
│   │   ├── 218 images: already fast, but batch hashing benefits from IO overlap
│   │   └── Return Vec<FastRecord> as Arrow RecordBatch (fast-mode schema)
│   │
│   ├── [DONE] mm wc — token counting for LLM budgeting
│   │   ├── Fast byte-level token estimator (~4 chars/token for text)
│   │   ├── Image token estimation via OpenAI-style tile counting
│   │   ├── Per-file, per-kind, total token counts (--by-kind)
│   │   ├── [ ] --budget 128K flag: show what fits in a context window
│   │   └── [ ] Optional tiktoken/cl100k for exact counts
│   │
│   ├── [DONE] mm tree — hierarchical directory view
│   │   ├── Size-annotated tree (file counts + sizes per directory)
│   │   ├── Kind-colored branches (ANSI: image yellow, video magenta, etc.)
│   │   ├── --depth, --kind filters, --size toggle
│   │   └── --format=json for programmatic consumption
│   │
│   ├── [DONE] Faster pipe composability
│   │   ├── Plain-text path output for piped find (via to_lines_fast)
│   │   ├── [ ] Streaming output for large result sets (don't buffer all rows)
│   │   └── [ ] --format tsv|csv|jsonl for one-row-at-a-time output
│   │
│   ├── Faster grep on document directories
│   │   ├── Current: fast-mode extraction on every file → 81s for 545 PDFs
│   │   ├── Pre-index text content in .mm/text_cache/ (one-time cost)
│   │   ├── Subsequent greps search the text cache (< 1s for 500 files)
│   │   ├── Rust-native regex search over cached text (bypass Python)
│   │   └── --no-cache flag for fresh extraction
│   │
│   └── info command fast path
│       ├── Current: 700ms (Arrow + pyarrow + Rich)
│       ├── Compute kind/ext/size stats in Rust from Vec<FileEntry>
│       └── Target: ~70ms (only import Rich for display)
│
├── P1 — Smart Extraction (80% Semantics, No VLM)
│   │
│   │   Extract the maximum possible signal from each file type using only
│   │   local, deterministic, sub-second operations. No network calls,
│   │   no GPU, no model weights. This is the smart local extraction layer.
│   │
│   ├── [DONE] PDF → visual snapshots (mm cat)
│   │   ├── Render pages to thumbnails via pypdfium2 + Pillow
│   │   ├── Tile into mosaic grids (4x4 default, configurable)
│   │   ├── Captures tables, charts, diagrams that text extraction misses
│   │   ├── 68-page PDF → 5 mosaics in 1.1s (~10ms/page)
│   │   ├── Single-page invoice → 5ms
│   │   └── mm cat <file/dir> --max-pages N --format=json
│   │
│   ├── Image perceptual fingerprint
│   │   ├── pHash (perceptual hash) — 64-bit, invariant to resize/compression (DONE)
│   │   ├── Average color histogram (dominant colors as hex triplet)
│   │   ├── Aspect ratio + orientation classification (portrait/landscape/square)
│   │   ├── Near-duplicate detection: hamming distance on pHash < 8 (DONE)
│   │   ├── Add to fast-mode record: phash, dominant_colors, aspect (DONE)
│   │   └── All in Rust via image crate (already a dep), ~1ms/image
│   │
│   ├── Document structure extraction
│   │   ├── Heading detection from PDF text (font-size heuristic via pypdfium2)
│   │   ├── Table detection (grid pattern in text layout)
│   │   ├── Table-of-contents extraction (outline/bookmark API in pypdfium2)
│   │   ├── Output: list of {page, type, text} structural elements
│   │   └── Enables "find me the table on page 12" without VLM
│   │
│   ├── Code semantic summary
│   │   ├── Function/class name extraction via tree-sitter (Rust bindings)
│   │   ├── Import graph (which modules does this file depend on)
│   │   ├── Complexity heuristic (line count × nesting depth)
│   │   ├── Languages: Python, Rust, JS/TS, Go, Java, C/C++
│   │   └── Add to fast-mode record: symbols, imports, complexity_score
│   │
│   ├── Video scene graph
│   │   ├── Scene boundary detection (already have scene-change mosaics)
│   │   ├── Per-scene: timestamp range, representative frame, dominant colors
│   │   ├── Temporal text overlay detection (ffmpeg OCR filter for burned-in text)
│   │   ├── Motion classification: static/pan/zoom/fast-motion per segment
│   │   └── Output: [{scene_id, start_s, end_s, thumbnail_path, motion_type}]
│   │
│   ├── Audio signal features
│   │   ├── Voice activity detection (energy threshold, zero-crossing rate)
│   │   ├── Speech vs music vs silence segmentation
│   │   ├── Dominant speaker diarization (simple energy-based, not neural)
│   │   └── Output: [{segment_type, start_s, end_s, confidence}]
│   │
│   └── Content deduplication
│       ├── Exact: xxh3 content hash (already done)
│       ├── Near-exact: fast_fingerprint for large file dedup
│       ├── Perceptual: pHash for image near-dupes (DONE)
│       ├── mm dedup — find and report duplicate clusters
│       └── --dry-run shows what would be removed, --symlink replaces dupes
│
├── P2 — VLM-in-the-Loop (Remaining 20%)
│   │
│   │   Use VLMs selectively where the smart local layer leaves gaps. Key insight: the smart
│   │   extraction layer provides enough structure to know WHICH files need
│   │   VLM attention and WHAT to ask about them. Targeted queries >> blind captioning.
│   │
│   ├── Keyframe mosaic → VLM video summary
│   │   ├── Feed mosaic grid(s) to qwen3-2b / llava for scene description
│   │   ├── describe_video() already implemented, needs CLI integration
│   │   ├── mm cat video.mp4 -m accurate → mosaic + VLM caption
│   │   ├── Batch: mm find --kind video | mm cat -m accurate --format=json
│   │   └── Output: {filename_suggestion, tags, summary, scenes}
│   │
│   ├── Audio transcription pipeline
│   │   ├── 2x audio extraction already done (Whisper-optimized WAV)
│   │   ├── Local Whisper via whisper.cpp or faster-whisper (Python)
│   │   ├── API-based: OpenAI Whisper API, Groq, Deepgram
│   │   ├── mm transcribe video.mp4 → timestamped transcript
│   │   ├── Speaker diarization as post-process on transcript
│   │   └── Cache transcripts in .mm/transcripts/{hash}.txt
│   │
│   ├── PDF visual understanding
│   │   ├── Page thumbnails (from P1) → VLM for table/chart extraction
│   │   ├── Targeted: only pages where text extraction returned <50 chars
│   │   ├── Output structured data: extracted tables as CSV, chart descriptions
│   │   └── mm cat scanned.pdf -m accurate → OCR + layout understanding
│   │
│   ├── Embedding generation
│   │   ├── SemanticAnalyzer.embed() trait already defined in Rust
│   │   ├── CLIP/SigLIP for images (via Python or ONNX Runtime)
│   │   ├── Text embeddings for code/documents (sentence-transformers)
│   │   ├── Store in .mm/embeddings.parquet (path, embedding vector)
│   │   └── Enable: mm search "sunset over mountains" --kind image
│   │
│   └── Semantic search
│       ├── mm search "query" — natural language search across all files
│       ├── Hybrid: keyword (grep) + vector (embedding cosine similarity)
│       ├── Cross-modal: text query → image/video/document results
│       └── Ranking: combine metadata, fast-mode features, accurate-mode embeddings
│
├── P3 — Context Builder (The Killer Feature)
│   │
│   │   This is what "mm" exists for: construct optimal LLM context
│   │   payloads from multi-modal directories. Given a token budget and a
│   │   task, select and format the most relevant content.
│   │
│   ├── mm context — LLM-ready payload builder
│   │   ├── --budget 128K: fit as much as possible in N tokens
│   │   ├── --task "describe the architecture": relevance-weighted selection
│   │   ├── --format markdown|xml|json: output format for LLM consumption
│   │   ├── Priority: code > docs > images (by default, configurable)
│   │   ├── Images: inline as base64 or reference mosaic thumbnails
│   │   ├── Videos: include keyframe mosaics + transcript excerpts
│   │   └── PDFs: include text + page thumbnails for visual content
│   │
│   ├── Smart token allocation
│   │   ├── Estimate tokens per file (wc --tokens from P0)
│   │   ├── Greedy knapsack: maximize coverage within budget
│   │   ├── File importance scoring: size, recency, kind, depth
│   │   ├── Truncation: head/tail for large files, page selection for PDFs
│   │   └── Show allocation: "12 files, 847 images, 102K tokens used"
│   │
│   ├── Incremental context updates
│   │   ├── Track which files were included in last context payload
│   │   ├── On re-run: only include changed/new files (diffing)
│   │   ├── Useful for long-running LLM conversations about a directory
│   │   └── --since "2h" flag: only files modified in last 2 hours
│   │
│   └── Context profiles
│       ├── .mm/profiles/code-review.toml — predefined configurations
│       ├── Profiles: code-review, bug-report, documentation, data-analysis
│       ├── Each profile defines: kinds, priorities, format, budget
│       └── mm context --profile code-review
│
├── P4 — Ecosystem & Integrations
│   │
│   ├── MCP server (Model Context Protocol)
│   │   ├── Expose mm as an MCP tool server
│   │   ├── Tools: scan, find, cat, grep, sql, keyframes, context
│   │   ├── Resources: directory index as MCP resource
│   │   ├── LLM agents can query file systems via mm natively
│   │   └── Zero-config: mm serve --mcp
│   │
│   ├── Watch mode
│   │   ├── mm watch — inotify/FSEvents file watcher
│   │   ├── Keep index hot in memory, update incrementally
│   │   ├── Emit events on file changes (for downstream consumers)
│   │   ├── WebSocket/SSE endpoint for real-time dashboards
│   │   └── Combined with MCP: always-fresh context for LLM agents
│   │
│   ├── mm diff — compare two directories
│   │   ├── Structural diff: files added, removed, modified, moved
│   │   ├── Content diff: changed hash, changed dimensions, etc.
│   │   ├── Semantic diff: different VLM captions (expensive, opt-in)
│   │   └── Output as enriched changelog for LLM consumption
│   │
│   ├── Cloud storage backends
│   │   ├── S3/GCS/Azure Blob as scan targets (list + head requests)
│   │   ├── Lazy download: only fetch content for fast-mode extraction when needed
│   │   └── Cache metadata locally in .mm/
│   │
│   └── Pre-built wheels + Homebrew
│       ├── CI/CD: maturin build for manylinux, macOS arm64/x86, Windows
│       ├── PyPI: pip install mm (no Rust toolchain needed)
│       ├── Homebrew: brew install mm (standalone binary)
│       └── Docker: ghcr.io/spillai/mm (with ffmpeg pre-installed)
│
└── Performance Targets
    │
    ├── Metadata scan
    │   ├── Current: 5ms / 249 files, 5.7ms / 1K files
    │   ├── With persistent index: <2ms / 1K files (no changes)
    │   └── Target: <50ms / 100K files
    │
    ├── CLI cold start
    │   ├── Current: 66ms (in-process), 116ms (with uv startup)
    │   ├── With Rust JSON: <30ms in-process for --format=json
    │   └── Target: <50ms wall-clock for any --format=json command
    │
    ├── Fast-mode batch extraction
    │   ├── Current: 5.1s for 17 videos (sequential)
    │   ├── Target: <1s for 17 videos (parallel)
    │   └── Target: <100ms for 200 images (parallel hash + dims)
    │
    ├── Smart local extraction
    │   ├── PDF page thumbnails: <20ms/page
    │   ├── Image pHash: <1ms/image (DONE)
    │   ├── Code symbol extraction: <5ms/file (tree-sitter)
    │   └── Video scene graph: <2s for 86min video
    │
    └── Context generation
        ├── mm context (metadata + fast mode): <200ms for 1K files
        ├── mm context -m accurate: depends on VLM latency
        └── Token estimation: <1ms/file (byte heuristic)
```

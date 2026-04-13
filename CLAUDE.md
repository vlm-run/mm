# CLAUDE.md — mm

## What this is

`mm` is a high-performance multi-modal context management library + CLI designed primarily for **AI agents** to understand file types that are not natively understood by LLMs — images, video, audio, PDFs, and other binary/media formats. Text files are already natively understood by LLMs and do not need `mm` processing.

Rust core for speed, Python for developer experience, Unix philosophy for composability.

## Core ideology

- Unix philosophy for composability.
- Speed, compression, devex is all what matters.
- Rust core for speed + Python for developer experience.
- Information-theoretical perspective on context
    - Input tok/img or tok/px: PDF/image content measured in toks (tok), dimensions in pixels (px).
    - Input tok/s: audio/video content measured in toks (tok), duration in seconds (s)
    - Input tok/MB: audio/video content, Mtok/MB.

## Libraries

**Python:**
- openai — chat/completions SDK (any OpenAI-compatible API: Ollama, vLLM, OpenAI)
- typer — CLI framework
- rich — terminal formatting (tables, panels, trees, syntax highlighting)
- polars — zero-copy DataFrame from Arrow
- pandas — DataFrame export
- sqlite-vec — SQLite + vector search (global DB at ~/.local/share/mm/mm.db)
- pyarrow — Arrow IPC deserialization (Rust → Python data transfer)
- google-genai — Gemini embedding generation (text, image, audio, video, document)
- pypdfium2 — PDF text extraction and page rendering
- Pillow — image mosaic tiling
- tomli — TOML config parsing (Python <3.11)
- pydantic — schema validation for YAML generation templates
- pyyaml — YAML template parsing

**Rust (mm-core):**
- arrow / parquet — Arrow RecordBatch + Parquet I/O
- pyo3 — Python bindings
- rayon — parallel iteration
- ignore — gitignore-aware directory walking
- mime_guess / infer — MIME detection
- xxhash-rust — xxh3 content hashing (mmap, zero-copy)
- image — image dimension extraction (header-only)
- kamadak-exif — EXIF metadata (camera, date, GPS)
- mp4parse / matroska — native video metadata (no ffmpeg for fast mode)
- memmap2 — memory-mapped file I/O
- serde / serde_json — JSON serialization (fast path)
- compact_str — SSO strings (no heap for short paths)

**System (optional):**
- ffmpeg — video keyframe mosaics for accurate mode, audio extraction

## Project layout

```
mm/
├── Cargo.toml                  # Rust workspace root (edition 2024)
├── pyproject.toml              # Python package (maturin build backend)
├── Makefile                    # Common dev targets (all via uv)
├── rust-toolchain.toml         # Pinned to stable + clippy/rustfmt
├── config/
│   └── profile.example.toml     # Sample LLM profile config
├── crates/
│   ├── mm-core/            # Rust core library
│   │   ├── src/
│   │   │   ├── lib.rs          # Re-exports all modules
│   │   │   ├── walk.rs         # Parallel directory scanning (ignore crate)
│   │   │   ├── meta.rs         # FileEntry, FileKind types
│   │   │   ├── detect.rs       # MIME / file kind classification
│   │   │   ├── schema.rs       # Arrow schema definitions
│   │   │   ├── table.rs        # Arrow RecordBatch + Parquet I/O
│   │   │   ├── extract.rs      # Content extraction trait + dispatcher
│   │   │   ├── extractors/     # Per-type extractors (code, image, video)
│   │   │   ├── hash.rs         # xxh3 hashing strategies (full, partial, mmap, directory_hash)
│   │   │   ├── cache.rs        # Manifest-based incremental re-indexing
│   │   │   └── format.rs       # Output formatting helpers
│   │   └── benches/            # Criterion benchmarks (l0_walk, l0_index, l1_extract, hash)
│   └── mm-python/          # PyO3 bindings (Scanner, L1Result)
│       └── src/lib.rs          # Arrow IPC transfer to Python
├── python/mm/              # Python package source
│   ├── __init__.py             # Public API re-exports
│   ├── _mm.pyi            # Type stubs for Rust bindings
│   ├── cli.py                  # Typer app — registers 6 commands + config
│   ├── context.py              # Context class (main Python API)
│   ├── config.py               # LLM provider config (~/.mm/config.toml)
│   ├── llm.py                  # LLM backend (OpenAI SDK, accurate mode)
│   ├── df.py                   # arrow_to_polars / arrow_to_pandas
│   ├── query.py                # SQLite-based SQL queries against Arrow tables
│   ├── display.py              # Rich formatting (tables, panels, format_size, format_number)
│   ├── pipe.py                 # stdin/stdout pipe detection (uses select())
│   ├── pdf.py                  # PDF page mosaic extraction (pypdfium2 + Pillow)
│   ├── ffmpeg.py               # ffmpeg wrappers (keyframe mosaics, audio/video segment extraction)
│   ├── video.py                # Video metadata helpers
│   ├── common/                 # Shared utilities
│   │   └── video/
│   │       └── shot_detection.py  # PySceneDetect wrapper (detect_scenes, sample_*)
│   ├── encoders/               # Media encoders (file → VLM-ready Messages)
│   │   ├── __init__.py         # Registry, @register_encoder, resolve_strategy, process_*
│   │   ├── audio.py            # transcribe (Whisper), audio-gemini
│   │   ├── document/
│   │   │   ├── __init__.py     # rasterize, rasterize-text (pypdfium2)
│   │   │   └── page_text.py    # page-text (text extraction per page)
│   │   ├── gemini.py           # video-gemini, video-gemini-chunked, document-gemini
│   │   ├── image/              # Image encoders
│   │   │   └── __init__.py     # resize, tile (overview + tile crops in one Message)
│   │   └── video/              # Video encoders
│   │       ├── __init__.py     # frame-sample, video-chunk (ffmpeg-based)
│   │       ├── frame_sample_transcript.py  # frames-transcript (frames + Whisper)
│   │       ├── mosaic.py       # mosaic (scene-aware frame extraction + tiled grids)
│   │       └── shot.py         # shot-frames + shot-mosaic (PySceneDetect-based)
│   ├── pipelines/              # YAML-based MLLM generation pipelines
│   │   ├── __init__.py         # Pipeline loading, caching, prompt rendering, overrides
│   │   ├── schema.py           # Pydantic schema (Encode, Generate, PipelineSpec)
│   │   ├── README.md           # Encoder reference table and authoring guide
│   │   ├── spec.yaml           # Reference YAML spec with all fields documented
│   │   ├── image/              # Image pipelines (fast.yaml, accurate.yaml)
│   │   ├── video/              # Video pipelines (fast.yaml, accurate.yaml)
│   │   ├── audio/              # Audio pipelines (fast.yaml, accurate.yaml)
│   │   └── document/           # Document pipelines (fast.yaml, accurate.yaml)
│   ├── store/                  # SQLite + sqlite-vec storage (metadata + embeddings)
│   │   ├── __init__.py         # Lazy re-exports
│   │   ├── schema.py           # SQL DDL + column enums (3 tables)
│   │   ├── db.py               # MmDatabase class (SQLite + sqlite-vec)
│   │   ├── util.py             # Content hashing (Rust) + shared DB instance
│   │   └── embed.py            # Embedding generation via Gemini (text, image, audio, video, doc)
│   └── commands/               # CLI subcommands (6 + config + profile)
│       ├── find.py             # mm find (--tree, --schema, --columns)
│       ├── cat.py              # mm cat (-n, --mode, auto-detect by type, accurate → embed)
│       ├── grep.py             # mm grep
│       ├── sql.py              # mm sql (all tables via SQLite)
│       ├── wc.py               # mm wc (--by-kind)
│       ├── bench.py            # mm bench (benchmark suite)
│       ├── config.py           # mm config (show, init, set, reset-db)
│       └── profile.py          # mm profile (list, add, update, use, remove)
├── tests/
│   └── python/                 # pytest suite
│       ├── conftest.py
│       ├── test_context.py
│       ├── test_cli.py
│       ├── test_l0_metadata.py
│       ├── test_l1_extraction.py
│       ├── test_pipe.py
│       └── test_benchmark.py
└── benchmarks/
    └── bench_cli.sh            # hyperfine CLI benchmarks
```

## Build & run (always use uv)

```bash
# First-time setup
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# Build Rust extension (required after any Rust code change)
uv run maturin develop --release

# Or use the Makefile shortcuts
make develop     # uv run maturin develop --release
make test        # cargo test + uv run pytest
make lint        # clippy + ruff + mypy
make bench       # cargo bench
make fmt         # cargo fmt + ruff format
```

**Important:** Always use `uv` — never bare `pip` or `maturin`. The Makefile wraps everything through `uv run`.

After modifying Rust code, you **must** re-run `make develop` before Python will see the changes.

## Running the CLI

```bash
# From the activated venv:
mm <command> [args]

# Or without activating:
uv run mm <command> [args]
```

## CLI commands (8 total)

| Command   | Purpose | Key flags |
|-----------|---------|-----------|
| `find`    | Find/list files, tree view, schema | `--name`, `--kind`, `--ext`, `--min-size`, `--max-size`, `--sort`, `--columns`, `--tree`, `--depth`, `--schema`, `--limit`, `--format` |
| `cat`     | Content extraction (auto-detected by file type × mode) | `--mode fast/accurate`, `-p` (pipeline), `-n` (head/tail), `--encode.*`, `--generate.*`, `--format` |
| `grep`    | Content search across files | `--kind`, `--ext`, `-C` (context), `--count`, `--format` |
| `sql`     | SQL on files, results, and chunks | `--dir`, `--format`, `--list-tables` |
| `wc`      | Count files, size, lines (est.), tokens (est.) | `--kind`, `--by-kind`, `--format` |
| `bench`   | Benchmark suite | `--format`, `--rounds` |
| `config`  | Extraction mode settings | `show`, `init`, `set`, `reset-db`, `reset-profiles`, `reset` |
| `profile` | Manage LLM provider profiles | `list`, `add`, `update`, `use`, `remove`, `--format` |

### Consolidated commands

The following commands were merged into the 5 core commands:

- `head` / `tail` → `cat -n 10` (head) / `cat -n -10` (tail)
- `keyframes` → `cat video.mp4 -m accurate` (auto-generates mosaic)
- `pages` → `cat document.pdf` (auto-extracts text)
- `audio` → `cat audio.mp3 -m accurate` (transcript → LLM summary)
- `ls` / `tree` / `describe` → `find` with `--tree`, `--schema`, `--columns`
- `info` → `wc` (default summary panel)

### find modes

- `mm find ~/data` — tabular listing (default)
- `mm find ~/data --name "test_.*\.py"` — filter by file name (string or regex)
- `mm find ~/data --tree --depth 2` — hierarchical tree view with sizes
- `mm find ~/data --schema` — column names, Arrow types, descriptions, sample values
- `mm find ~/data --columns name,size,kind` — custom column selection

### cat modes (auto-detected from file type × mode)

- `mm cat file` — text/metadata extraction (default, fast mode, <100ms)
- `mm cat file -n 20` — first 20 lines (head)
- `mm cat file -n -20` — last 20 lines (tail)
- `mm cat file -m accurate` — LLM-generated caption/description
- `mm cat video.mp4 -m accurate` — auto-generates keyframe mosaic → LLM description
- `mm cat photo.png -p resize` — encode with named encoder
- `mm cat photo.png -p my-pipeline.yaml` — custom pipeline YAML

### Schema and SQL

Use `mm find <dir> --schema` to see all available columns, their Arrow types, descriptions of what they contain, and a sample value.

`mm sql` auto-routes queries based on the table name in the `FROM` clause:
- `files` → scan directory + SQLite (ephemeral in-memory table)
- `l2_results` → SQLite direct (LLM-generated summaries)
- `chunks` → SQLite direct (chunked content + embeddings)

Use `mm sql --list-tables` to see available tables and row counts.

Columns (`files`): `uri`, `name`, `stem`, `ext`, `size`, `modified`, `created`, `mime`, `kind`, `is_binary`, `depth`, `parent`, `width`, `height`.

`kind` values: `image`, `video`, `document`, `code`, `audio`, `data`, `config`, `text`, `other`.

### Output modes (`--format`)

- **`rich`** (default in TTY): Rich formatted tables/panels
- **`tsv`** (default when piped): Tab-separated values, no ANSI
- **`csv`**: Comma-separated values
- **`json`**: Structured JSON (compact when piped, pretty in TTY)

## Processing modes

- **fast** (default): Local extraction, no LLM call. PDFs → text via pypdfium2. Images → resize/base64. Videos → mosaic grids. Audio → Whisper transcription. Code/text → raw passthrough (no pipeline). Pipeline-driven via `pipelines/{kind}/fast.yaml` for image, video, audio, document.
- **accurate**: LLM-powered descriptions via OpenAI-compatible API. Images → VLM caption. Videos → mosaic → VLM description. Audio → transcript → LLM summary. Documents → text → LLM structuring. Code/text → passed directly to LLM (no pipeline). Requires a configured profile (`mm profile add/update`). Pipeline-driven via `pipelines/{kind}/accurate.yaml`.

## Python API

```python
from mm import Context

ctx = Context("~/data/1-demo")         # Metadata scan happens here (~5ms for 249 files)

df = ctx.to_polars()                    # polars.DataFrame
df = ctx.to_pandas()                    # pandas.DataFrame
tbl = ctx.to_arrow()                    # pyarrow.Table

result = ctx.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC")

big_images = ctx.filter(kind="image", min_size="1MB")

text = ctx.cat("paper.pdf")
hits = ctx.grep("attention", kind="document")

ctx.show()   # Rich table
ctx.info()   # Rich summary panel
```

## Architecture notes

- **Rust → Python data path**: Arrow RecordBatch serialized to IPC bytes in Rust, deserialized via `pyarrow.ipc.open_stream` in Python. Not PyCapsule FFI (had compatibility issues with pyarrow).
- **Rust fast path**: `find --format json`, `wc --format json` bypass pyarrow entirely — serde_json in Rust, ~60ms cold start.
- **Parallel scanning**: `ignore` crate for gitignore-aware walking + `rayon` for parallelism.
- **Hashing**: xxh3 via `xxhash-rust` for fast content fingerprinting (full file via mmap). `directory_hash` hashes sorted file listings for SQL cache keys.
- **Storage**: Global SQLite database at `~/.local/share/mm/mm.db` with tables: `files` (metadata + content), `l2_results` (LLM summaries), `chunks` (content chunks), `chunks_vec` (sqlite-vec embeddings), `cache` (key-value cache). Schema defined in `python/mm/store/schema.py`.
- **Embeddings**: Generated via Gemini embedding API through the mm inference server (`/v1/embeddings`). Supports text, image, audio (chunked at 80s), video (chunked at 120s), and PDF. Stored in `chunks_vec` virtual table (sqlite-vec). Triggered automatically after accurate-mode extraction.
- **SQL routing**: `mm sql` auto-detects table from `FROM` clause. `files` → scan + in-memory SQLite. `l2_results`/`chunks` → persistent SQLite direct.
- **Video metadata (fast)**: Native MP4 parsing (mp4parse) and MKV/WebM parsing (matroska) in Rust. No ffmpeg in fast mode — metadata only, <100ms.
- **PDF text extraction**: `pypdfium2` on the Python CLI side (in `commands/cat.py`). Scanned/image-only PDFs return empty text.
- **Pipe detection**: `pipe.py` uses `select.select()` with zero timeout to avoid blocking when stdin is not a TTY but has no data.
- **LLM backend**: Uses the `openai` Python SDK for all chat/completions calls. Sends `think=false` and `reasoning_effort="none"` to suppress chain-of-thought. Temperature defaults to 0.1. All prompts and generation parameters are externalized into YAML pipelines (`python/mm/pipelines/{kind}/{mode}.yaml`) validated via Pydantic at load time. The single entry point is `LlmBackend.generate(kind, mode, *, context, parts, pipeline_spec)`.
- **Pipeline**: `encode` (file → LLM-ready parts via `mm/encoders/`) → `generate` (LLM call) → text output. Pipelines support `pyfunc` transforms (inline Python or `.py` file references) and CLI overrides (`--encode.strategy X --generate.max-tokens N`). Users can override built-in pipelines at `~/.config/mm/pipelines/` or load explicit YAMLs with `-p`.

## LLM configuration

Provider settings (base_url, api_key, model) are configured per-profile. Active profile is resolved as: `--profile` flag > `MM_PROFILE` env > `active_profile` in config file > `"default"`.

```bash
# Profile management
mm profile add openrouter --base-url https://openrouter.ai/api/v1 --model vlm-1
mm profile update openrouter --model qwen3-vl:8b              # update a field
mm profile use openrouter                                      # switch active profile
mm profile list                                            # list all profiles

# Per-command profile selection
mm --profile openrouter cat photo.png -m accurate
MM_PROFILE=openrouter mm cat photo.png -m accurate
```

## Testing

```bash
cargo test --workspace                                      # Rust tests
uv run pytest tests/python -v                               # Python tests
cargo bench --workspace                                     # Rust benchmarks (Criterion)
uv run pytest tests/python/test_benchmark.py --benchmark-only  # Python benchmarks
```

## Benchmarking

Run the integrated benchmark suite against a data directory:

```bash
# Full bench (fast + accurate) with Rich output
mm bench ~/data/mmbench-mini --format rich --rounds 3

# JSON output for archival
mm bench ~/data/mmbench-mini --format json --rounds 3 > benchmarks/mm-bench-YYYYMMDD.json

# Single-file video benchmark
mm cat video.mp4 --mode fast   # timing + token metrics in footer
```

### Saving benchmark results

After each benchmark run, save results to `benchmarks/` as flat files:
- `benchmarks/mm-bench-YYYYMMDD.json` — full `mm bench` JSON output
- `benchmarks/mm-bench-YYYYMMDD.md` — key numbers and comparison with previous runs

Naming: `mm-bench-YYYYMMDD` (e.g. `mm-bench-260322`).

### Key metrics to track

- **scan**: files/s, MB/s, bits/s (metadata scanning throughput)
- **fast**: per-file latency, MB/s (content extraction)
- **accurate**: total wall time, realtime multiplier, prompt→completion tokens
- **Video pipeline**: frame_extraction_ms, audio_extraction_ms, audio_transcription_ms, vlm_call_ms
- **Information-theoretic**: bits/s throughput at each level

### CHANGELOG.md

Every commit that changes performance numbers or adds/modifies benchmarks should update `CHANGELOG.md` with:
- The benchmark result (`benchmarks/mm-bench-YYYYMMDD.md`)
- What changed and the measured impact

## Keeping SPEC.md in sync

<!-- AUTO-SYNC: After any implementation change (new feature, bug fix, refactor, schema change,
     new/removed CLI flag, new extractor, perf improvement, dependency change), update SPEC.md
     to reflect the current state. Rules:
     - Toggle [x]/[ ]/[~] checkboxes to match what's actually implemented
     - Add new line items for new capabilities; remove items that were deleted
     - Update performance numbers only when re-measured
     - Update test counts when tests are added/removed
     - Keep it factual and terse — no prose, just the tree structure
     - Do NOT update SPEC.md for docs-only, test-only, or CI-only changes -->

## Known gaps / TODOs

- Python `Context.cat()` for PDFs uses Rust extractor (raw bytes) instead of pypdfium2. The CLI `cat` correctly uses pypdfium2.
- Accurate mode requires an external LLM server; no built-in model. Default: local Ollama with `gemma4:e2b`.
- Audio embedding fails for files >80s if sent as a single Part (Gemini limit). Use `audio_parts()` to auto-chunk.
- `upsert_files()` reads the full `files` table to preserve content columns — will need optimization at >100K files.
- sqlite-vec cold import is ~130ms. No daemon or sidecar cache needed.

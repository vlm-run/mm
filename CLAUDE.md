# CLAUDE.md — mm

## What this is

`mm` is a high-performance multi-modal context management library + CLI. Rust core for speed, Python for developer experience, Unix philosophy for composability.

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
- duckdb — in-process SQL on Arrow tables
- pyarrow — Arrow IPC deserialization (Rust → Python data transfer)
- pypdfium2 — PDF text extraction and page rendering
- Pillow — image mosaic tiling
- tomli — TOML config parsing (Python <3.11)

**Rust (mm-core):**
- arrow / parquet — Arrow RecordBatch + Parquet I/O
- pyo3 — Python bindings
- rayon — parallel iteration
- ignore — gitignore-aware directory walking
- mime_guess / infer — MIME detection
- xxhash-rust — xxh3 content hashing (mmap, zero-copy)
- image — image dimension extraction (header-only)
- kamadak-exif — EXIF metadata (camera, date, GPS)
- mp4parse / matroska — native video metadata (no ffmpeg for L1)
- memmap2 — memory-mapped file I/O
- serde / serde_json — JSON serialization (fast path)
- compact_str — SSO strings (no heap for short paths)

**System (optional):**
- ffmpeg — video keyframe mosaics at L2, audio extraction

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
│   │   │   ├── schema.rs       # Arrow schema definitions (L0, L1)
│   │   │   ├── table.rs        # Arrow RecordBatch + Parquet I/O
│   │   │   ├── extract.rs      # L1 extraction trait + dispatcher
│   │   │   ├── extractors/     # Per-type extractors (code, image, video)
│   │   │   ├── hash.rs         # xxh3 hashing strategies (full, partial, mmap)
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
│   ├── llm.py                  # LLM backend (OpenAI SDK, L2)
│   ├── df.py                   # arrow_to_polars / arrow_to_pandas
│   ├── duck.py                 # DuckDB query helper
│   ├── display.py              # Rich formatting (tables, panels, format_size, format_number)
│   ├── pipe.py                 # stdin/stdout pipe detection (uses select())
│   ├── pdf.py                  # PDF page mosaic extraction (pypdfium2 + Pillow)
│   ├── ffmpeg.py               # ffmpeg wrappers (keyframe mosaics, audio extraction)
│   ├── video.py                # Video metadata helpers
│   └── commands/               # CLI subcommands (6 + config + profile)
│       ├── find.py             # mm find (--tree, --schema, --columns)
│       ├── cat.py              # mm cat (-n, --level, auto-detect by type)
│       ├── grep.py             # mm grep
│       ├── sql.py              # mm sql (DuckDB)
│       ├── wc.py               # mm wc (--by-kind)
│       ├── bench.py            # mm bench (L0/L1/L2 benchmark suite)
│       ├── config.py           # mm config (show, init, set)
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
| `find`    | Find/list files, tree view, schema | `--kind`, `--ext`, `--min-size`, `--max-size`, `--sort`, `--columns`, `--tree`, `--depth`, `--schema`, `--limit`, `--format` |
| `cat`     | Content extraction (auto-detected by file type) | `--level 0/1/2`, `-n` (head/tail), `--detail`, `--mode`, `--mosaic-*`, `--audio-*`, `--format` |
| `grep`    | Content search across files | `--kind`, `--ext`, `-C` (context), `--count`, `--level`, `--format` |
| `sql`     | DuckDB SQL on the file index | `--dir`, `--format` |
| `wc`      | Count files, bytes, lines, estimated tokens | `--kind`, `--by-kind`, `--format` |
| `bench`   | Benchmark suite (L0/L1/L2) | `--format`, `--rounds` |
| `config`  | Extraction mode settings | `show`, `init`, `set` |
| `profile` | Manage LLM provider profiles | `list`, `add`, `update`, `use`, `remove`, `--format` |

### Consolidated commands

The following commands were merged into the 5 core commands:

- `head` / `tail` → `cat -n 10` (head) / `cat -n -10` (tail)
- `keyframes` → `cat video.mp4 -l 2` (auto-generates mosaic)
- `pages` → `cat document.pdf` (auto-extracts text at L1)
- `audio` → `cat audio.mp3 -l 2` (metadata → LLM description)
- `ls` / `tree` / `describe` → `find` with `--tree`, `--schema`, `--columns`
- `info` → `wc` (default summary panel)

### find modes

- `mm find ~/data` — tabular listing (default)
- `mm find ~/data --tree --depth 2` — hierarchical tree view with sizes
- `mm find ~/data --schema` — column names, Arrow types, descriptions, sample values
- `mm find ~/data --columns name,size,kind` — custom column selection

### cat modes (auto-detected from file type × level)

- `mm cat file` — text/metadata extraction (default, L1, <100ms)
- `mm cat file -n 20` — first 20 lines (head)
- `mm cat file -n -20` — last 20 lines (tail)
- `mm cat file --level 0` — raw file content
- `mm cat file --level 2` — LLM-generated caption/description
- `mm cat video.mp4 -l 2` — auto-generates keyframe mosaic → LLM description
- `mm cat photo.png -l 2 --detail` — LLM caption (~80 words)

### Schema and SQL

Use `mm find <dir> --schema` to see all available columns, their Arrow types, descriptions of what they contain, and a sample value.

Columns: `path`, `name`, `stem`, `ext`, `size`, `modified`, `created`, `mime`, `kind`, `is_binary`, `depth`, `parent`, `width`, `height`.

`kind` values: `image`, `video`, `document`, `code`, `audio`, `data`, `config`, `text`, `other`.

### Output modes (`--format`)

- **`rich`** (default in TTY): Rich formatted tables/panels
- **`tsv`** (default when piped): Tab-separated values, no ANSI
- **`csv`**: Comma-separated values
- **`json`**: Structured JSON (compact when piped, pretty in TTY)

## Processing levels

- **L0** (metadata): path, size, kind, ext, timestamps, depth, parent, width, height. Built in Rust with `ignore` + `rayon`. Measured at ~0.02ms/file on real multi-modal data (249 files in 5ms).
- **L1** (content): `cat` auto-detects file type. PDFs → text via pypdfium2. Images → dimensions/MIME/xxh3/EXIF via Rust. Video/audio → metadata only (resolution, duration, codecs, <100ms, no ffmpeg). Code/text → raw passthrough. Scanned/image-only PDFs yield empty text at L1.
- **L2** (semantic): LLM-generated captions/descriptions via OpenAI-compatible API. Requires a configured profile (`mm profile add/update`).

## Python API

```python
from mm import Context

ctx = Context("~/data/1-demo")         # L0 scan happens here (~5ms for 249 files)

df = ctx.to_polars()                    # polars.DataFrame
df = ctx.to_pandas()                    # pandas.DataFrame
tbl = ctx.to_arrow()                    # pyarrow.Table

result = ctx.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC")

big_images = ctx.filter(kind="image", min_size="1MB")

text = ctx.cat("paper.pdf", level=1)
hits = ctx.grep("attention", kind="document")

ctx.show()   # Rich table
ctx.info()   # Rich summary panel
```

## Architecture notes

- **Rust → Python data path**: Arrow RecordBatch serialized to IPC bytes in Rust, deserialized via `pyarrow.ipc.open_stream` in Python. Not PyCapsule FFI (had compatibility issues with pyarrow).
- **Rust fast path**: `find --format json`, `wc --format json` bypass pyarrow entirely — serde_json in Rust, ~60ms cold start.
- **Parallel scanning**: `ignore` crate for gitignore-aware walking + `rayon` for parallelism.
- **Hashing**: xxh3 via `xxhash-rust` for fast content fingerprinting (full file via mmap).
- **Video metadata (L1)**: Native MP4 parsing (mp4parse) and MKV/WebM parsing (matroska) in Rust. No ffmpeg at L1 — metadata only, <100ms.
- **PDF text extraction**: `pypdfium2` on the Python CLI side (in `commands/cat.py`). Scanned/image-only PDFs return empty text.
- **Pipe detection**: `pipe.py` uses `select.select()` with zero timeout to avoid blocking when stdin is not a TTY but has no data.
- **LLM backend**: Uses the `openai` Python SDK for all chat/completions calls. Sends `think=false` and `reasoning_effort="none"` to suppress chain-of-thought. Temperature defaults to 0.1.

## LLM configuration

Provider settings (base_url, api_key, model) are configured per-profile. Active profile is resolved as: `--profile` flag > `MM_PROFILE` env > `active_profile` in config file > `"default"`.

```bash
# Profile management
mm profile add openrouter --base-url https://openrouter.ai/api/v1 --model vlm-1
mm profile update openrouter --model qwen3-vl:8b              # update a field
mm profile use openrouter                                      # switch active profile
mm profile list                                            # list all profiles

# Per-command profile selection
mm --profile openrouter cat photo.png -l 2
MM_PROFILE=openrouter mm cat photo.png -l 2
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
# Full bench (L0 + L1 + L2) with Rich output
mm bench ~/data/mmbench-mini --format rich --rounds 3

# JSON output for archival
mm bench ~/data/mmbench-mini --format json --rounds 3 > benchmarks/mm-bench-YYYYMMDD.json

# Single-file video benchmark
mm cat video.mp4 -l 2 --mode fast   # timing + token metrics in footer
```

### Saving benchmark results

After each benchmark run, save results to `benchmarks/` as flat files:
- `benchmarks/mm-bench-YYYYMMDD.json` — full `mm bench` JSON output
- `benchmarks/mm-bench-YYYYMMDD.md` — key numbers and comparison with previous runs

Naming: `mm-bench-YYYYMMDD` (e.g. `mm-bench-260322`).

### Key metrics to track

- **L0**: files/s, MB/s, bits/s (metadata scanning throughput)
- **L1**: per-file latency, MB/s (content extraction)
- **L2**: total wall time, realtime multiplier, prompt→completion tokens
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

- Python `Context.cat(level=1)` for PDFs uses Rust L1 extractor (raw bytes) instead of pypdfium2. The CLI `cat --level 1` correctly uses pypdfium2.
- L2 requires an external LLM server; no built-in model. Default: local Ollama with `qwen3.5:0.8b`.

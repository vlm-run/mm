# CLAUDE.md — vlmctx

## What this is

`vlmctx` is a high-performance multi-modal context management library + CLI. Rust core for speed, Python for developer experience, Unix philosophy for composability.

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

**Rust (vlmctx-core):**
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
vlmctx/
├── Cargo.toml                  # Rust workspace root (edition 2024)
├── pyproject.toml              # Python package (maturin build backend)
├── Makefile                    # Common dev targets (all via uv)
├── rust-toolchain.toml         # Pinned to stable + clippy/rustfmt
├── config/
│   └── config.example.toml     # Sample LLM provider config
├── crates/
│   ├── vlmctx-core/            # Rust core library
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
│   └── vlmctx-python/          # PyO3 bindings (Scanner, L1Result)
│       └── src/lib.rs          # Arrow IPC transfer to Python
├── python/vlmctx/              # Python package source
│   ├── __init__.py             # Public API re-exports
│   ├── _vlmctx.pyi            # Type stubs for Rust bindings
│   ├── cli.py                  # Typer app — registers 6 commands + config
│   ├── context.py              # Context class (main Python API)
│   ├── config.py               # LLM provider config (~/.vlmctx/config.toml)
│   ├── llm.py                  # LLM backend (OpenAI SDK, L2)
│   ├── df.py                   # arrow_to_polars / arrow_to_pandas
│   ├── duck.py                 # DuckDB query helper
│   ├── display.py              # Rich formatting (tables, panels, format_size, format_number)
│   ├── pipe.py                 # stdin/stdout pipe detection (uses select())
│   ├── pdf.py                  # PDF page mosaic extraction (pypdfium2 + Pillow)
│   ├── ffmpeg.py               # ffmpeg wrappers (keyframe mosaics, audio extraction)
│   ├── video.py                # Video metadata helpers
│   └── commands/               # CLI subcommands (6 + config)
│       ├── find.py             # vlmctx find
│       ├── ls.py               # vlmctx ls (--tree, --schema)
│       ├── cat.py              # vlmctx cat (-n, --level, auto-detect by type)
│       ├── grep.py             # vlmctx grep
│       ├── sql.py              # vlmctx sql (DuckDB)
│       ├── wc.py               # vlmctx wc (--by-kind)
│       └── config.py           # vlmctx config (show, init, set)
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
vlmctx <command> [args]

# Or without activating:
uv run vlmctx <command> [args]
```

## CLI commands (6 total)

| Command | Purpose | Key flags |
|---------|---------|-----------|
| `find`  | Locate files by kind/ext/size | `--kind`, `--ext`, `--min-size`, `--max-size`, `--limit`, `--json` |
| `ls`    | Tabular listing, tree view, schema | `--sort`, `--columns`, `--kind`, `--tree`, `--depth`, `--schema`, `--json` |
| `cat`   | Content extraction (auto-detected by file type) | `--level 0/1/2`, `-n` (head/tail), `--detail`, `--mosaic-*`, `--audio-*`, `--json` |
| `grep`  | Content search across files | `--kind`, `--ext`, `-C` (context), `--count`, `--level`, `--json` |
| `sql`   | DuckDB SQL on the file index | `--dir`, `--json` |
| `wc`    | Count files, bytes, lines, estimated tokens | `--kind`, `--by-kind`, `--json` |

### Consolidated commands

The following commands were merged into the 6 core commands:

- `head` / `tail` → `cat -n 10` (head) / `cat -n -10` (tail)
- `keyframes` → `cat video.mp4 -l 2` (auto-generates mosaic)
- `pages` → `cat document.pdf` (auto-extracts text at L1)
- `audio` → `cat audio.mp3 -l 2` (metadata → LLM description)
- `tree` → `ls --tree --depth 2`
- `describe` → `ls --schema`
- `info` → `wc` (default summary panel)

### ls modes

- `vlmctx ls ~/data` — tabular listing (default)
- `vlmctx ls ~/data --tree --depth 2` — hierarchical tree view with sizes
- `vlmctx ls ~/data --schema` — column names, Arrow types, descriptions, sample values

### cat modes (auto-detected from file type × level)

- `vlmctx cat file` — text/metadata extraction (default, L1, <100ms)
- `vlmctx cat file -n 20` — first 20 lines (head)
- `vlmctx cat file -n -20` — last 20 lines (tail)
- `vlmctx cat file --level 0` — raw file content
- `vlmctx cat file --level 2` — LLM-generated caption/description
- `vlmctx cat video.mp4 -l 2` — auto-generates keyframe mosaic → LLM description
- `vlmctx cat photo.png -l 2 --detail` — LLM caption (~80 words)

### Schema and SQL

Use `vlmctx ls <dir> --schema` to see all available columns, their Arrow types, descriptions of what they contain, and a sample value.

Columns: `path`, `name`, `stem`, `ext`, `size`, `modified`, `created`, `mime`, `kind`, `is_binary`, `depth`, `parent`, `width`, `height`.

`kind` values: `image`, `video`, `document`, `code`, `audio`, `data`, `config`, `text`, `other`.

### Output modes

- **TTY stdout**: Rich formatted tables/panels
- **Piped stdout**: plain TSV/text (machine-readable, no ANSI)
- **`--json` flag**: JSON output on any command that supports it

## Processing levels

- **L0** (metadata): path, size, kind, ext, timestamps, depth, parent, width, height. Built in Rust with `ignore` + `rayon`. Measured at ~0.02ms/file on real multi-modal data (249 files in 5ms).
- **L1** (content): `cat` auto-detects file type. PDFs → text via pypdfium2. Images → dimensions/MIME/xxh3/EXIF via Rust. Video/audio → metadata only (resolution, duration, codecs, <100ms, no ffmpeg). Code/text → raw passthrough. Scanned/image-only PDFs yield empty text at L1.
- **L2** (semantic): LLM-generated captions/descriptions via OpenAI-compatible API. Requires `VLMCTX_BASE_URL` env var. Falls back to L1 when unconfigured.

## Python API

```python
from vlmctx import Context

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
- **Rust fast path**: `find --json`, `ls --json`, `wc --json` bypass pyarrow entirely — serde_json in Rust, ~60ms cold start.
- **Parallel scanning**: `ignore` crate for gitignore-aware walking + `rayon` for parallelism.
- **Hashing**: xxh3 via `xxhash-rust` for fast content fingerprinting (full file via mmap).
- **Video metadata (L1)**: Native MP4 parsing (mp4parse) and MKV/WebM parsing (matroska) in Rust. No ffmpeg at L1 — metadata only, <100ms.
- **PDF text extraction**: `pypdfium2` on the Python CLI side (in `commands/cat.py`). Scanned/image-only PDFs return empty text.
- **Pipe detection**: `pipe.py` uses `select.select()` with zero timeout to avoid blocking when stdin is not a TTY but has no data.
- **LLM backend**: Uses the `openai` Python SDK for all chat/completions calls. Sends `think=false` and `reasoning_effort="none"` to suppress chain-of-thought. Temperature defaults to 0.1.

## LLM configuration

Provider settings resolved in order: CLI flags > env vars > `~/.vlmctx/config.toml` > defaults.

```bash
# Env vars
export VLMCTX_BASE_URL="http://localhost:11434"   # Ollama default
export VLMCTX_API_KEY=""                           # if needed
export VLMCTX_MODEL="qwen3.5:0.8b"                # default model

# CLI flags (override everything)
vlmctx --base-url http://... --model gpt-4o cat photo.png -l 2

# Config file management
vlmctx config show                # show resolved config with sources
vlmctx config init                # create ~/.vlmctx/config.toml
vlmctx config set model gpt-4o   # update a key
```

## Testing

```bash
cargo test --workspace                                      # Rust tests
uv run pytest tests/python -v                               # Python tests
cargo bench --workspace                                     # Rust benchmarks (Criterion)
uv run pytest tests/python/test_benchmark.py --benchmark-only  # Python benchmarks
```

## Known gaps / TODOs

- Python `Context.cat(level=1)` for PDFs uses Rust L1 extractor (raw bytes) instead of pypdfium2. The CLI `cat --level 1` correctly uses pypdfium2.
- L2 requires an external LLM server; no built-in model. Default: local Ollama with `qwen3.5:0.8b`.

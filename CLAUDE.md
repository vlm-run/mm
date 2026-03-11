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

## Project layout

```
vlmctx/
├── Cargo.toml                  # Rust workspace root (edition 2024)
├── pyproject.toml              # Python package (maturin build backend)
├── Makefile                    # Common dev targets (all via uv)
├── rust-toolchain.toml         # Pinned to stable + clippy/rustfmt
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
│   │   │   ├── extractors/     # Per-type extractors (code, image)
│   │   │   ├── cache.rs        # Manifest-based incremental re-indexing
│   │   │   └── format.rs       # Output formatting helpers
│   │   └── benches/            # Criterion benchmarks (l0_walk, l0_index)
│   └── vlmctx-python/          # PyO3 bindings (Scanner, L1Result)
│       └── src/lib.rs          # Arrow IPC transfer to Python
├── python/vlmctx/              # Python package source
│   ├── __init__.py             # Public API re-exports
│   ├── _vlmctx.pyi            # Type stubs for Rust bindings
│   ├── cli.py                  # Typer app — registers 6 commands
│   ├── context.py              # Context class (main Python API)
│   ├── df.py                   # arrow_to_polars / arrow_to_pandas
│   ├── duck.py                 # DuckDB query helper
│   ├── display.py              # Rich formatting (tables, panels, format_size, format_number)
│   ├── pipe.py                 # stdin/stdout pipe detection (uses select())
│   ├── llm.py                  # LLM backend (OpenAI-compatible, L2)
│   └── commands/               # CLI subcommands (6 total)
│       ├── find.py             # vlmctx find
│       ├── ls.py               # vlmctx ls (--tree, --schema)
│       ├── cat.py              # vlmctx cat (-n, --visual, --audio, --level)
│       ├── grep.py             # vlmctx grep
│       ├── sql.py              # vlmctx sql (DuckDB)
│       └── wc.py               # vlmctx wc (--by-kind)
└── tests/
    └── python/                 # pytest suite
        ├── conftest.py
        ├── test_context.py
        ├── test_cli.py
        ├── test_pipe.py
        └── test_benchmark.py
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
| `cat`   | Content extraction (text, visual mosaics, audio) | `--level 0/1/2`, `-n` (head/tail), `--visual`, `--audio`, `--speed`, `--json` |
| `grep`  | Content search across files | `--kind`, `--ext`, `-C` (context), `--count`, `--level`, `--json` |
| `sql`   | DuckDB SQL on the file index | `--dir`, `--json` |
| `wc`    | Count files, bytes, lines, estimated tokens | `--kind`, `--by-kind`, `--json` |

### Consolidated commands

The following commands were merged into the 6 core commands:

- `head` / `tail` → `cat -n 10` (head) / `cat -n -10` (tail)
- `keyframes` → `cat video.mp4 --visual`
- `pages` → `cat document.pdf --visual`
- `audio` → `cat video.mp4 --audio --speed 2`
- `tree` → `ls --tree --depth 2`
- `describe` → `ls --schema`
- `info` → `wc` (default summary panel)

### ls modes

- `vlmctx ls ~/data` — tabular listing (default)
- `vlmctx ls ~/data --tree --depth 2` — hierarchical tree view with sizes
- `vlmctx ls ~/data --schema` — column names, Arrow types, descriptions, sample values

### cat modes

- `vlmctx cat file` — text/metadata extraction (default, L1)
- `vlmctx cat file -n 20` — first 20 lines (head)
- `vlmctx cat file -n -20` — last 20 lines (tail)
- `vlmctx cat file --visual` — visual mosaic (PDF pages or video keyframes)
- `vlmctx cat file --audio` — extract audio track from video/audio
- `vlmctx cat file --level 0` — raw file content
- `vlmctx cat file --level 2` — LLM-generated caption/description

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
- **L1** (content): `cat` uses `pypdfium2` for PDF text extraction and Rust extractors for image dimensions/MIME/xxh3 hash. `--visual` renders PDF page mosaics or video keyframe grids. `--audio` extracts audio via ffmpeg. Scanned/image-only PDFs yield empty text at L1.
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

- **Rust -> Python data path**: Arrow RecordBatch serialized to IPC bytes in Rust, deserialized via `pyarrow.ipc.open_stream` in Python. Not PyCapsule FFI (had compatibility issues with pyarrow).
- **Parallel scanning**: `ignore` crate for gitignore-aware walking + `rayon` for parallelism.
- **Hashing**: xxh3 via `xxhash-rust` for fast content fingerprinting.
- **PDF text extraction**: `pypdfium2` on the Python CLI side (in `commands/cat.py`). Scanned/image-only PDFs return empty text.
- **Pipe detection**: `pipe.py` uses `select.select()` with zero timeout to avoid blocking when stdin is not a TTY but has no data (e.g. when run from automation tools).
- **LLM backend**: OpenAI-compatible API. Env vars: `VLMCTX_BASE_URL`, `VLMCTX_API_KEY`, `VLMCTX_MODEL`.

## Testing

```bash
cargo test --workspace                                      # Rust tests
uv run pytest tests/python -v                               # Python tests
cargo bench --workspace                                     # Rust benchmarks (Criterion)
uv run pytest tests/python/test_benchmark.py --benchmark-only  # Python benchmarks
```

## Known gaps / TODOs

- Python `Context.cat(level=1)` for PDFs uses Rust L1 extractor (raw bytes) instead of pypdfium2. The CLI `cat --level 1` correctly uses pypdfium2.
- L2 requires an external LLM server; no built-in model.

## Key dependencies

**Rust**: arrow 54, parquet 54, pyo3 0.23, rayon, ignore, mime_guess, infer, xxhash-rust, image 0.25, kamadak-exif, compact_str, chrono, thiserror

**Python**: typer, rich, polars, pandas, duckdb, pyarrow, pypdfium2

# CLAUDE.md — vlmctx

## What this is

`vlmctx` is a high-performance multi-modal context management library + CLI. Rust core for speed, Python for developer experience, Unix philosophy for composability.

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
│   ├── cli.py                  # Typer app — registers all commands
│   ├── context.py              # Context class (main Python API)
│   ├── df.py                   # arrow_to_polars / arrow_to_pandas
│   ├── duck.py                 # DuckDB query helper
│   ├── display.py              # Rich formatting (tables, panels)
│   ├── pipe.py                 # stdin/stdout pipe detection (uses select())
│   ├── llm.py                  # LLM backend (OpenAI-compatible, L2)
│   └── commands/               # CLI subcommands
│       ├── find.py             # vlmctx find
│       ├── ls.py               # vlmctx ls
│       ├── cat.py              # vlmctx cat (--level 0/1/2, pypdfium2 for PDF)
│       ├── head.py             # vlmctx head
│       ├── tail.py             # vlmctx tail
│       ├── grep.py             # vlmctx grep
│       ├── sql.py              # vlmctx sql (DuckDB)
│       ├── describe.py         # vlmctx describe (column names, types, descriptions)
│       ├── info.py             # vlmctx info
│       ├── tree.py             # (stub — not yet implemented)
│       ├── wc.py               # (stub — not yet implemented)
│       └── context.py          # (stub — not yet implemented)
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

## CLI commands

| Command | Purpose | Key flags |
|---------|---------|-----------|
| `find`  | Find files by kind/ext/size | `--kind`, `--ext`, `--min-size`, `--max-size`, `--limit`, `--json` |
| `ls`    | Tabular listing (all rows) | `--sort`, `--desc`, `--columns`, `--kind`, `--limit`, `--json` |
| `cat`   | Semantic content display | `--level 0/1/2`, `--json` |
| `head`  | First N lines/pages | `-n` |
| `tail`  | Last N lines/pages | `-n` |
| `grep`  | Content search across files | `--kind`, `--ext`, `-C` (context), `--count`, `--level`, `--json` |
| `sql`   | DuckDB SQL on the file index | `--dir`, `--json` |
| `describe` | Describe file index columns, types, and contents | `--json` |
| `info`  | Summary panel | (directory argument) |
| `keyframes` | Video keyframe mosaic extraction | `--strategy`, `--cols`, `--rows`, `--width`, `--num-mosaics` |
| `audio` | Audio extraction at Nx speed for transcription | `--speed`, `--format`, `--sample-rate` |
| `wc`    | Count files, bytes, lines, estimated tokens | `--kind`, `--by-kind`, `--json` |
| `tree`  | Hierarchical directory view with sizes | `--depth`, `--kind`, `--size`, `--json` |
| `pages` | PDF page mosaic extraction | `--cols`, `--rows`, `--width`, `--max-pages`, `--json` |

### describe and SQL table

Use `vlmctx describe <dir>` to see all available columns, their Arrow types, descriptions of what they contain, and a sample value. This is the equivalent of `DESCRIBE table` in SQL.

Columns: `path`, `name`, `stem`, `ext`, `size`, `modified`, `created`, `mime`, `kind`, `is_binary`, `depth`, `parent`.

`kind` values: `image`, `video`, `document`, `code`, `other`.

### Output modes

- **TTY stdout**: Rich formatted tables/panels
- **Piped stdout**: plain TSV/text (machine-readable, no ANSI)
- **`--json` flag**: JSON output on any command that supports it

## Processing levels

- **L0** (metadata): path, size, kind, ext, timestamps, depth, parent. Built in Rust with `ignore` + `rayon`. Measured at ~0.02ms/file on real multi-modal data (249 files in 5ms).
- **L1** (content): The CLI `cat`/`head`/`tail` commands use `pypdfium2` for PDF text extraction and Rust extractors for image dimensions/MIME/xxh3 hash. Note: scanned/image-only PDFs yield empty text at L1. The Python `Context.cat()` method currently uses the Rust L1 extractor (returns raw bytes for PDFs, not pypdfium2-extracted text — this is a known gap).
- **L2** (semantic): LLM-generated captions/descriptions via OpenAI-compatible API. Requires `VLMCTX_LLM_BASE_URL` env var. Falls back to L1 when unconfigured.

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
- **LLM backend**: OpenAI-compatible API. Env vars: `VLMCTX_LLM_BASE_URL`, `VLMCTX_LLM_API_KEY`, `VLMCTX_LLM_MODEL`.

## Testing

```bash
cargo test --workspace                                      # Rust tests
uv run pytest tests/python -v                               # Python tests
cargo bench --workspace                                     # Rust benchmarks (Criterion)
uv run pytest tests/python/test_benchmark.py --benchmark-only  # Python benchmarks
```

## Known gaps / TODOs

- `tree`, `wc`, `context` commands are stubbed but not implemented.
- Python `Context.cat(level=1)` for PDFs uses Rust L1 extractor (raw bytes) instead of pypdfium2. The CLI `cat --level 1` correctly uses pypdfium2.
- No video content extraction at L1 yet.
- L2 requires an external LLM server; no built-in model.

## Key dependencies

**Rust**: arrow 54, parquet 54, pyo3 0.23, rayon, ignore, mime_guess, infer, xxhash-rust, image 0.25, kamadak-exif, compact_str, chrono, thiserror

**Python**: typer, rich, polars, pandas, duckdb, pyarrow, pypdfium2

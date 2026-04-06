# mm

High-performance multi-modal context management library + CLI.

Rust core for speed. Python for developer experience. Unix philosophy for composability.

## Installation

```bash
# Development install (requires Rust toolchain + uv)
git clone <repo-url> && cd mm
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"
uv run maturin develop --release
```

## CLI

Six commands that mirror familiar Unix tools but operate on multi-modal semantics.
Indexing is implicit — every command auto-builds a metadata index on first use.

L0 commands (`find`, `wc` with `--format json`) run in **~60ms** on 700 files via the Rust fast path.

### Quick start

```bash
mm find ~/data --tree --depth 1              # directory overview with sizes
mm wc ~/data --by-kind                       # file/byte/token counts by kind
mm find ~/data --kind image --format json    # find all images (60ms)
mm cat paper.pdf                             # extract text from PDF
mm cat video.mp4                             # video metadata (<100ms)
mm cat video.mp4 -l 2                        # keyframe mosaic → LLM description
mm cat photo.png -l 2 --detail               # LLM caption (~80 words)
```

### Command reference

| Command | Purpose | Key flags |
|---------|---------|-----------|
| `find`  | Find/list files, tree view, schema | `--kind`, `--ext`, `--min-size`, `--max-size`, `--sort`, `--reverse`, `--columns`, `--tree`, `--depth`, `--schema`, `--limit`, `--format` |
| `cat` | Content extraction (auto-detected by file type) | `--level 0/1/2`, `-n`, `--detail`, `--mosaic-*`, `--audio-*`, `--format` |
| `grep` | Content search across files | `--kind`, `--ext`, `-C`, `--count`, `--format` |
| `sql` | SQL queries on file index, L2 results, and chunks | `--dir`, `--format`, `--no-cache`, `--list-tables` |
| `wc` | Count files, bytes, lines, tokens | `--kind`, `--by-kind`, `--format` |
| `bench` | Benchmark suite (L0/L1/L2) | `--format`, `--rounds` |
| `config` | Extraction mode settings | `show`, `init`, `set`, `reset-db` |
| `profile` | Manage LLM provider profiles | `list`, `add`, `update`, `use`, `remove` |

### find — locate/list, tree, and schema

```bash
mm find ~/data --kind image                               # all images
mm find ~/data --kind video --sort size --reverse         # videos by size
mm find ~/data --ext .pdf --min-size 10mb                 # large PDFs
mm find ~/data --kind image --limit 5 --format json       # JSON output

mm find ~/data --sort size --reverse --limit 20        # tabular listing
mm find ~/data --kind document --columns name,size,ext
mm find ~/data --tree --depth 2                        # hierarchical tree view
mm find ~/data --tree --kind video                     # tree filtered to videos
mm find ~/data --schema                                # column names, types, descriptions
mm find ~/data --format json                           # full metadata JSON
```

### cat — content extraction

```bash
mm cat paper.pdf                               # extract text (L1)
mm cat paper.pdf -n 20                         # first 20 lines (head)
mm cat paper.pdf -n -20                        # last 20 lines (tail)
mm cat photo.png                               # image dims, MIME, hash, EXIF
mm cat video.mp4                               # resolution, duration, codecs (<100ms)
mm cat video.mp4 -l 2                          # mosaic → LLM description
mm cat photo.png -l 2                          # LLM caption (~20 words)
mm cat photo.png -l 2 --detail                 # LLM description (~80 words)
```

### wc — count files, bytes, tokens

```bash
mm wc ~/data --by-kind
mm wc ~/data --by-kind --format json
```

### grep — content search

```bash
mm grep "attention" ~/data --kind document
mm grep "TODO" ~/data --kind code
mm grep "invoice" ~/data --count               # match counts per file
```

### sql — query the index

Queries file metadata via scan + DuckDB, or L2 results and chunks directly from LanceDB.

```bash
mm find ~/data --schema                          # see available columns
mm sql "SELECT kind, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb \
  FROM files GROUP BY kind ORDER BY mb DESC" --dir ~/data

# Query LanceDB tables directly (auto-detected from table name)
mm sql "SELECT uri, summary FROM l2_results LIMIT 10"
mm sql "SELECT uri, chunk_idx, LENGTH(chunk_text) FROM chunks"
mm sql "SELECT COUNT(*) FROM chunks WHERE embed_model IS NOT NULL"
mm sql --list-tables                              # show available tables
```

### Output modes

- **TTY**: Rich formatted tables/panels
- **Piped**: plain TSV/text (machine-readable, no ANSI)
- **`--format json`**: JSON output on any command that supports it

## Python API

```python
from mm import Context

ctx = Context("~/data/domains")
print(ctx)  # Context(root='/Users/.../domains', files=702)

# DataFrame export
df = ctx.to_polars()         # polars.DataFrame (zero-copy)
df = ctx.to_pandas()         # pandas.DataFrame

# SQL via DuckDB
result = ctx.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC")

# Chainable filtering
big_images = ctx.filter(kind="image", min_size="1MB")

# Content access
text  = ctx.cat("paper.pdf", level=1)
hits  = ctx.grep("revenue", kind="document")

# Display
ctx.show()    # Rich table
ctx.info()    # Rich summary panel
```

## Processing Levels

| Level | What | Speed | How |
|-------|------|-------|-----|
| L0 | File metadata (path, size, kind, ext, timestamps, dimensions) | ~60ms / 700 files | Rust `stat()` + extension classification + image headers |
| L1 | Content extraction (text from PDF, image hash/EXIF, video metadata) | <100ms/file | pypdfium2 (PDF), Rust mmap (images), mp4parse/matroska (video) |
| L2 | Semantic understanding (captions, descriptions) | Varies | LLM API via active profile |

## Performance

Benchmarked on Apple Silicon (M-series), 702 files (7.2GB):

| Operation | Latency |
|-----------|---------|
| L0 scan (702 files) | 8ms |
| CLI cold start (`find --format json`) | 60ms |
| CLI cold start (`find --schema --format json`) | 109ms |
| CLI cold start (`sql`) | 300ms |
| L1 code extraction | ~52ms |
| L1 image extraction | ~61ms |
| L1 PDF text extraction | ~220ms |
| L1 video metadata | <100ms |
| PDF page mosaic (per page) | ~10ms |
| Video keyframe mosaic (48 frames) | ~1s |

## Storage

mm uses a global LanceDB database at `~/.local/share/mm/mm.lance/` with three tables:

| Table | Contents | Relationship |
|-------|----------|-------------|
| `files` | L0 + L1 file metadata (one row per file, `uri` = absolute path) | — |
| `l2_results` | LLM-generated summaries (many per file) | FK → `files.uri` |
| `chunks` | ~1024-char content chunks + embedding vectors | FK → `l2_results` |

A dbm sidecar cache (`~/.local/share/mm/cache.db`) provides sub-millisecond cache reads for L1/L2 results without importing LanceDB. Use `mm config reset-db` to clear all databases and caches.

## Architecture

```
Rust (mm-core)                   Python (mm)
┌─────────────────────┐             ┌─────────────────────┐
│ ignore (parallel     │  serde_json │ Typer CLI           │
│   dir walk + stat)  │────────────>│   find/wc        │
│ rayon parallelism   │  (fast path)│   (60ms, no pyarrow)│
│ Arrow RecordBatch   │             │                     │
│ xxh3 hashing (mmap) │  Arrow IPC  │ Context class       │
│ directory_hash      │────────────>│ .to_polars/pandas() │
│ L1 extractors       │  PyO3       │ .sql() via DuckDB   │
│   code, image,      │<───────────>│ LanceDB (storage)   │
│   video (mp4parse,  │             │ dbm cache (fast L1/  │
│    matroska)        │             │   L2 reads, ~0.2ms) │
│ EXIF extraction     │             │ Embeddings (Gemini)  │
└─────────────────────┘             └─────────────────────┘
```

## L2 LLM Configuration using Profiles

For semantic understanding (`--level 2`), mm uses the `openai` Python SDK to call any OpenAI-compatible API. Provider settings are managed through **profiles** — named configurations stored in `~/.config/mm/mm.toml`.

### Quick setup

```bash
mm config init                # create config with default profile (local Ollama)
mm config show                # show resolved config with sources
```

### Managing profiles

Each profile stores `base_url`, `api_key`, and `model`. You can have as many as you need — one per provider, one per use-case, etc.

```bash
# Add profiles for different providers
mm profile add openai --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o
mm profile add openrouter --base-url  https://openrouter.ai/api/v1 --model qwen/qwen3.5-27b
mm profile add ollama --base-url http://localhost:11434 --model qwen3.5:9B

# List all profiles (● = active)
mm profile list

# Switch the active profile
mm profile use openai

# Update a field on an existing profile
mm profile update openai --model gpt-4o-mini --api-key sk-new-key

# Remove a profile (cannot remove the active one)
mm profile remove openai
```

### Selecting a profile per-command

```bash
# --profile flag (one-off override, does not change active profile)
mm --profile openai cat photo.png -l 2

# Environment variable
MM_PROFILE=openai mm cat photo.png -l 2
```

### Resolution order

Provider settings (base_url, api_key, model) come from the active profile, falling back to built-in defaults.

The active profile is resolved as:

```
--profile flag  >  MM_PROFILE env  >  active_profile in config file  >  "default"
```

### Config file format

```toml
# ~/.config/mm/mm.toml
active_profile = "default"

[profile.ollama]
base_url = "http://localhost:11434"
api_key = ""
model = "qwen3.5:0.8b"

[profile.openrouter]
base_url = " https://openrouter.ai/api/v1"
api_key = ""
model = "qwen/qwen3.5-27b"
```

## License

MIT

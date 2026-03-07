# vlmctx

High-performance multi-modal context management library + CLI.

Rust core for speed. Python for developer experience. Unix philosophy for composability.

## Installation

```bash
# Development install (requires Rust toolchain + uv)
git clone <repo-url> && cd vlmctx
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"
uv run maturin develop --release
```

## CLI

vlmctx commands mirror familiar Unix tools but operate on multi-modal semantics.
Indexing is implicit -- every command auto-builds a metadata index on first use.

### info — directory overview

```bash
$ vlmctx info ~/data/1-demo
╭──────────────────────── 1-demo ────────────────────────╮
│   Files            249                                  │
│   Total Size       636.9 MB                             │
│   Image            218                                  │
│   Video            17                                   │
│   Document         8                                    │
│   Top Extensions   .png (155), .jpg (55), .mp4 (17)     │
╰────────────────────────────────────────────────────────╯
```

### find — locate files

```bash
vlmctx find ~/data --kind image                    # all images
vlmctx find ~/data --kind video                    # all videos
vlmctx find ~/data --kind document                 # all PDFs/docs
vlmctx find ~/data --ext .png,.webp                # by extension
vlmctx find ~/data --min-size 10mb                 # by size
vlmctx find ~/data --min-size 1mb --max-size 5mb --kind image
vlmctx find ~/data --kind image --limit 5 --json   # JSON output
```

### ls — tabular listing

```bash
vlmctx ls ~/data                                    # all rows
vlmctx ls ~/data --limit 10                         # first 10 rows
vlmctx ls ~/data --sort size --desc --limit 20
vlmctx ls ~/data --kind document --columns name,size,ext
vlmctx ls ~/data --sort size --desc --limit 10 --columns name,kind,size --json
```

### describe — inspect the file index table

Like `DESCRIBE` in SQL — shows every column, its type, what it contains, and a sample value:

```bash
vlmctx describe ~/data            # Rich table with column docs
vlmctx describe ~/data --json     # machine-readable
```

### cat — semantic content display

```bash
vlmctx cat paper.pdf --level 1     # extract text from PDF via pypdfium2
vlmctx cat photo.png --level 1     # image dimensions, MIME, content hash
vlmctx cat photo.png --level 2     # LLM-generated caption (requires LLM config)
vlmctx cat code.rs --level 0       # raw file content
```

### head / tail — first/last N lines

```bash
vlmctx head paper.pdf -n 15        # first 15 lines of extracted PDF text
vlmctx tail paper.pdf -n 10        # last 10 lines
```

### grep — content search

```bash
vlmctx grep "attention" ~/data --kind document
vlmctx grep "invoice" ~/data --kind document --json
vlmctx grep "TODO" ~/data --kind code
```

### sql — DuckDB queries on the file index

The table name is always `files`. Columns: `path`, `name`, `stem`, `ext`, `size`, `modified`, `created`, `mime`, `kind`, `is_binary`, `depth`, `parent`.

```bash
# File kind breakdown
vlmctx sql "SELECT kind, COUNT(*) as n, ROUND(SUM(size)/1024.0/1024.0, 1) as mb \
  FROM files GROUP BY kind ORDER BY mb DESC" --dir ~/data

# Extension analytics
vlmctx sql "SELECT ext, COUNT(*) as n, ROUND(AVG(size)/1024.0, 1) as avg_kb \
  FROM files GROUP BY ext ORDER BY n DESC" --dir ~/data

# Size distribution
vlmctx sql "SELECT
  CASE WHEN size < 100*1024 THEN '<100KB'
       WHEN size < 1024*1024 THEN '100KB-1MB'
       WHEN size < 10*1024*1024 THEN '1MB-10MB'
       ELSE '>10MB' END as bucket,
  COUNT(*) as n
  FROM files WHERE kind != 'other'
  GROUP BY bucket ORDER BY n DESC" --dir ~/data

# Cross-tab by directory and kind
vlmctx sql "SELECT parent, kind, COUNT(*) as n \
  FROM files GROUP BY parent, kind ORDER BY parent, n DESC" --dir ~/data

# LIKE search
vlmctx sql "SELECT name, ROUND(size/1024.0, 1) as kb \
  FROM files WHERE name LIKE '%dashboard%'" --dir ~/data
```

### Output modes

- **TTY**: Rich formatted tables and panels
- **Piped**: plain TSV/text (machine-readable)
- **`--json`**: JSON output on any command that supports it

## Python API

```python
from vlmctx import Context

ctx = Context("~/data/1-demo")
print(ctx)  # Context(root='/Users/sudeep/data/1-demo', files=249)

# DataFrame export
df = ctx.to_polars()         # polars.DataFrame (249, 12)
df = ctx.to_pandas()         # pandas.DataFrame (249, 12)

# SQL via DuckDB
result = ctx.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC")

# Chainable filtering
big_images = ctx.filter(kind="image", min_size="1MB")  # 102 files

# Content access (relative paths from root)
text  = ctx.cat("paper.pdf", level=1)       # extracted text
first = ctx.head("paper.pdf", n=15)         # first 15 lines
last  = ctx.tail("paper.pdf", n=10)         # last 10 lines
hits  = ctx.grep("attention", kind="document")

# Display
ctx.show()    # Rich table in terminal
ctx.info()    # Rich summary panel
```

## Processing Levels

| Level | What | Speed | How |
|-------|------|-------|-----|
| L0 | File metadata (path, size, kind, ext, timestamps) | ~0.02ms/file | Rust `stat()` + extension classification |
| L1 | Content extraction (text from PDF, image dimensions/hash) | <1s/file | pypdfium2 (PDF), image crate (images), Rust extractors |
| L2 | Semantic understanding (captions, descriptions) | Varies | LLM API via `VLMCTX_LLM_BASE_URL` |

## Performance

Benchmarked on Apple Silicon (M-series):

| Dataset | Files | L0 Scan Time | Per File |
|---------|-------|-------------|----------|
| Synthetic 1K | 1,000 | 5.7ms | 5.7us |
| Synthetic 10K | 10,000 | 16.6ms | 1.7us |
| Real multi-modal (~/data/1-demo) | 249 | 5ms | 0.02ms |

## Architecture

```
Rust (vlmctx-core)                   Python (vlmctx)
┌─────────────────────┐             ┌─────────────────────┐
│ ignore (parallel     │  Arrow IPC  │ Context class       │
│   dir walk + stat)  │────────────>│ .to_polars()        │
│ Arrow RecordBatch   │             │ .to_pandas()        │
│ Parquet I/O         │  PyO3       │ .sql() via DuckDB   │
│ L1 extractors       │<───────────>│ Typer CLI           │
│   code, image       │             │ Rich display        │
└─────────────────────┘             │ pypdfium2 (PDF)     │
                                    │ LlmBackend (L2)     │
                                    └─────────────────────┘
```

## L2 LLM Configuration

For semantic understanding (`--level 2`), configure an OpenAI-compatible LLM backend:

```bash
export VLMCTX_LLM_BASE_URL="http://localhost:11434/v1"   # e.g. Ollama
export VLMCTX_LLM_API_KEY=""                               # if needed
export VLMCTX_LLM_MODEL="llava"                            # vision model
```

## License

MIT

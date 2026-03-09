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
Indexing is implicit — every command auto-builds a metadata index on first use.

L0 commands (`find`, `ls`, `wc`, `tree` with `--json`) run in **~60ms** on 700 files via the Rust fast path.

### Quick start

```bash
vlmctx tree ~/data --depth 1            # directory overview with sizes
vlmctx wc ~/data --by-kind              # file/byte/token counts by kind
vlmctx find ~/data --kind image --json  # find all images (60ms)
vlmctx cat paper.pdf --level 1          # extract text from PDF
vlmctx pages ~/data --max-pages 8       # PDF page mosaics for VLM
vlmctx keyframes video.mp4              # video keyframe mosaic grids
```

### Command reference

| Command | Purpose | Latency | Key flags |
|---------|---------|---------|-----------|
| `find` | Locate files by kind/ext/size | ~60ms | `--kind`, `--ext`, `--min-size`, `--max-size`, `--sort`, `--limit`, `--json` |
| `ls` | Tabular file listing | ~60ms | `--sort`, `--desc`, `--columns`, `--kind`, `--limit`, `--json` |
| `tree` | Hierarchical directory view | ~70ms | `--depth`, `--kind`, `--size`, `--json` |
| `wc` | Count files, bytes, lines, tokens | ~65ms | `--kind`, `--by-kind`, `--json` |
| `cat` | Semantic content display | 50-220ms | `--level 0/1/2`, `--json` |
| `head` | First N lines/pages | 50-220ms | `-n` |
| `tail` | Last N lines/pages | 50-220ms | `-n` |
| `grep` | Content search across files | varies | `--kind`, `--ext`, `-C`, `--count`, `--json` |
| `sql` | DuckDB SQL on file index | ~300ms | `--dir`, `--json` |
| `describe` | Column schema introspection | ~110ms | `--json` |
| `info` | Directory summary panel | ~700ms | (directory argument) |
| `keyframes` | Video keyframe mosaic grids | ~1s | `--strategy`, `--cols`, `--rows`, `--num-mosaics`, `--json` |
| `pages` | PDF page mosaic grids | ~10ms/page | `--cols`, `--rows`, `--width`, `--max-pages`, `--json` |
| `audio` | Audio extraction for transcription | ~200ms | `--speed`, `--format`, `--sample-rate`, `--json` |

### info — directory overview

```bash
$ vlmctx info ~/data/domains
╭──────────────────────── domains ─────────────────────────╮
│  702 files  7.2 GB                                        │
│  Document 545  Image 134  Video 7  Code 4  Audio 2       │
│  .pdf (454), .PDF (91), .jpg (84), .png (32), .jpeg (8)  │
╰──────────────────────────────────────────────────────────╯
```

### find — locate files

```bash
vlmctx find ~/data --kind image                    # all images
vlmctx find ~/data --kind video --sort size --desc  # videos by size
vlmctx find ~/data --ext .pdf --min-size 10mb       # large PDFs
vlmctx find ~/data --kind image --limit 5 --json    # JSON output
```

### ls — tabular listing

```bash
vlmctx ls ~/data --sort size --desc --limit 20
vlmctx ls ~/data --kind document --columns name,size,ext
vlmctx ls ~/data --json                             # full metadata JSON
```

### tree — hierarchical view

```bash
vlmctx tree ~/data --depth 1                        # one level deep
vlmctx tree ~/data --kind video                     # video files only
vlmctx tree ~/data --json                           # JSON tree
```

### wc — count files, bytes, tokens

```bash
vlmctx wc ~/data --by-kind --json
# {"files": 702, "bytes": 7775220367, "estimated_tokens": 1503804306,
#  "by_kind": {"document": {"files": 545, "tokens": 792881131}, ...}}
```

### describe and SQL

```bash
vlmctx describe ~/data                              # show table columns
vlmctx sql "SELECT kind, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb \
  FROM files GROUP BY kind ORDER BY mb DESC" --dir ~/data
```

### cat — semantic content display

```bash
vlmctx cat paper.pdf --level 1     # extract text from PDF via pypdfium2
vlmctx cat photo.png --level 1     # image dimensions, MIME, hash, EXIF
vlmctx cat video.mp4 --level 1     # resolution, duration, codecs + keyframe mosaic
vlmctx cat code.rs --level 0       # raw file content
```

### grep — content search

```bash
vlmctx grep "attention" ~/data --kind document
vlmctx grep "TODO" ~/data --kind code
vlmctx grep "invoice" ~/data --count               # match counts per file
```

### keyframes — video mosaic grids

```bash
vlmctx keyframes video.mp4                          # 6x8 grid, 48 frames
vlmctx keyframes video.mp4 --strategy scene         # scene-change detection
vlmctx keyframes video.mp4 --num-mosaics 4 --json   # 4 grids (192 frames)
```

### pages — PDF page mosaics

```bash
vlmctx pages document.pdf                           # 4x4 page grid
vlmctx pages ~/data/pdfs --max-pages 16 --json      # all PDFs, limit pages
```

### Output modes

- **TTY**: Rich formatted tables/panels
- **Piped**: plain TSV/text (machine-readable, no ANSI)
- **`--json`**: JSON output on any command that supports it

## Python API

```python
from vlmctx import Context

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
first = ctx.head("paper.pdf", n=15)
hits  = ctx.grep("revenue", kind="document")

# Display
ctx.show()    # Rich table
ctx.info()    # Rich summary panel
```

## Processing Levels

| Level | What | Speed | How |
|-------|------|-------|-----|
| L0 | File metadata (path, size, kind, ext, timestamps, dimensions) | ~60ms / 700 files | Rust `stat()` + extension classification + image headers |
| L1 | Content extraction (text from PDF, image hash/EXIF, video metadata) | 50ms-1.5s/file | pypdfium2 (PDF), Rust mmap (images), mp4parse/matroska (video) |
| L2 | Semantic understanding (captions, descriptions) | Varies | LLM API via `VLMCTX_LLM_BASE_URL` |

## Performance

Benchmarked on Apple Silicon (M-series), 702 files (7.2GB):

| Operation | Latency |
|-----------|---------|
| L0 scan (702 files) | 8ms |
| CLI cold start (`find --json`) | 60ms |
| CLI cold start (`describe --json`) | 109ms |
| CLI cold start (`sql`) | 300ms |
| L1 code extraction | ~52ms |
| L1 image extraction | ~61ms |
| L1 PDF text extraction | ~220ms |
| L1 video metadata + mosaic | ~1.5s |
| PDF page mosaic (per page) | ~10ms |
| Video keyframe mosaic (48 frames) | ~1s |

## Architecture

```
Rust (vlmctx-core)                   Python (vlmctx)
┌─────────────────────┐             ┌─────────────────────┐
│ ignore (parallel     │  serde_json │ Typer CLI           │
│   dir walk + stat)  │────────────>│   find/ls/wc/tree   │
│ rayon parallelism   │  (fast path)│   (60ms, no pyarrow)│
│ Arrow RecordBatch   │             │                     │
│ Parquet I/O         │  Arrow IPC  │ Context class       │
│ serde_json (direct) │────────────>│ .to_polars/pandas() │
│ L1 extractors       │  PyO3       │ .sql() via DuckDB   │
│   code, image,      │<───────────>│ Rich display        │
│   video (mp4parse,  │             │ pypdfium2 (PDF)     │
│    matroska)        │             │ Pillow (mosaics)    │
│ xxh3 hashing (mmap) │             │ ffmpeg (video/audio)│
│ EXIF extraction     │             │ LlmBackend (L2)     │
└─────────────────────┘             └─────────────────────┘
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

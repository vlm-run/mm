---
name: vlmctx-cli-skill
description: >
  Use the vlmctx CLI to index, explore, query, and extract content from multi-modal directories
  containing images, videos, PDFs, code, and other files. Triggers: exploring a directory's contents,
  listing/finding files by type or size, extracting text from PDFs, getting image metadata, running SQL
  analytics on file metadata, searching across file contents, counting tokens, viewing directory trees,
  extracting PDF page mosaics, video keyframe extraction, 'what files are in this folder',
  'find all images', 'show me the PDFs', 'how much storage do videos use', 'extract text from this PDF',
  'search documents for X', 'analyze this directory', 'how many tokens', 'show the tree'.
---

# vlmctx CLI

`vlmctx` is a high-performance multi-modal context management CLI. It indexes directories instantly (~60ms for 700 files), then exposes Unix-style commands for exploring, querying, and extracting content from images, videos, PDFs, code, and other files.

Always use `--json` for machine-readable output when parsing results programmatically.

## Workflow

1. Start with `vlmctx info <dir>` for an overview (file count, size, kind breakdown).
2. Use `vlmctx tree <dir> --depth 1` to see the directory structure at a glance.
3. Use `vlmctx wc <dir> --by-kind` to estimate token counts for LLM context budgeting.
4. Use `vlmctx describe <dir>` to see available columns and types before writing SQL.
5. Explore with `find`, `ls`, `sql`, `grep`, `cat` as needed.
6. Use `pages` / `keyframes` for visual extraction from PDFs and videos.

## Commands

### info — directory overview

```bash
vlmctx info <dir>
```

Returns: file count, total size, breakdown by kind, top extensions. ~700ms (uses Rich display).

### tree — hierarchical directory view

```bash
vlmctx tree <dir>                    # full tree with sizes
vlmctx tree <dir> --depth 1          # top-level dirs only
vlmctx tree <dir> --kind image       # only image files
vlmctx tree <dir> --json             # JSON tree structure
```

Shows directory hierarchy with file counts and sizes per directory. ANSI-colored by kind. ~70ms.

### wc — count files, bytes, lines, tokens

```bash
vlmctx wc <dir>                      # summary totals
vlmctx wc <dir> --by-kind            # breakdown by file kind
vlmctx wc <dir> --kind document      # only documents
vlmctx wc <dir> --json               # machine-readable
```

Estimates LLM tokens (~chars/4 for text, tile-based for images). ~65ms.

### describe — show table schema

```bash
vlmctx describe <dir>           # Rich table with column docs
vlmctx describe <dir> --json    # machine-readable
```

Columns in the `files` table:

| Column | Type | Description |
|--------|------|-------------|
| path | string | Relative path from scan root |
| name | string | File name with extension |
| stem | string | File name without extension |
| ext | string | Extension including dot (`.png`, `.pdf`) |
| size | uint64 | File size in bytes |
| modified | timestamp | Last modification time |
| created | timestamp | Creation time |
| mime | string | MIME type (`image/png`, `application/pdf`) |
| kind | string | `image`, `video`, `document`, `code`, `audio`, `data`, `config`, `text`, `other` |
| is_binary | bool | Whether file is binary |
| depth | uint16 | Directory depth (0 = top-level) |
| parent | string | Parent directory path |
| width | uint32 | Pixel width (images only, null otherwise) |
| height | uint32 | Pixel height (images only, null otherwise) |

### find — locate files

```bash
vlmctx find <dir> --kind image                         # all images
vlmctx find <dir> --kind video                         # all videos
vlmctx find <dir> --kind document                      # all PDFs/docs
vlmctx find <dir> --kind audio                         # audio files
vlmctx find <dir> --ext .png,.webp                     # by extension
vlmctx find <dir> --ext .PDF                           # case-sensitive ext match
vlmctx find <dir> --min-size 1mb --max-size 10mb       # by size range
vlmctx find <dir> --kind image --limit 5 --json        # JSON output, capped
vlmctx find <dir> --sort size --desc --limit 10        # largest files
```

~63ms via Rust fast path. Piped output is one path per line. `--json` returns full metadata.

### ls — tabular listing

```bash
vlmctx ls <dir>                                         # all files, all columns
vlmctx ls <dir> --columns name,kind,size --limit 10     # select columns
vlmctx ls <dir> --sort size --desc                      # sorted
vlmctx ls <dir> --kind document --columns name,size     # filtered
vlmctx ls <dir> --sort size --desc --json               # JSON output
```

~61ms for `--json`. TTY output uses Rich tables.

### sql — DuckDB queries on file index

The table name is `files`. Use `describe` to see columns.

```bash
# Kind breakdown with sizes
vlmctx sql "SELECT kind, COUNT(*) as n, ROUND(SUM(size)/1024.0/1024.0,1) as mb FROM files GROUP BY kind ORDER BY mb DESC" --dir <dir>

# Extension analytics
vlmctx sql "SELECT ext, COUNT(*) as n, ROUND(AVG(size)/1024.0,1) as avg_kb FROM files GROUP BY ext ORDER BY n DESC" --dir <dir>

# Files by directory
vlmctx sql "SELECT parent, COUNT(*) as n FROM files GROUP BY parent ORDER BY n DESC" --dir <dir>

# Size distribution
vlmctx sql "SELECT CASE WHEN size<100*1024 THEN '<100KB' WHEN size<1024*1024 THEN '100KB-1MB' WHEN size<10*1024*1024 THEN '1MB-10MB' ELSE '>10MB' END as bucket, COUNT(*) as n FROM files GROUP BY bucket ORDER BY n DESC" --dir <dir>

# Cross-tab by directory and kind
vlmctx sql "SELECT parent, kind, COUNT(*) as n, ROUND(SUM(size)/1024.0/1024.0,1) as mb FROM files GROUP BY parent, kind HAVING n > 3 ORDER BY mb DESC LIMIT 15" --dir <dir>

# Name search
vlmctx sql "SELECT name, ROUND(size/1024.0,1) as kb FROM files WHERE name LIKE '%invoice%'" --dir <dir>

# JSON output
vlmctx sql "SELECT * FROM files WHERE kind='document'" --dir <dir> --json
```

~270-500ms (DuckDB overhead).

### cat — content extraction

```bash
vlmctx cat <file> --level 0     # raw file content
vlmctx cat <file> --level 1     # extracted content (default)
vlmctx cat <file> --level 2     # LLM-generated description (needs VLMCTX_LLM_BASE_URL)
```

Level 1 behavior by file type:
- **PDF**: text extraction via pypdfium2 (~220ms). Scanned/image-only PDFs return empty.
- **Image** (.png/.jpg/.webp/.gif): dimensions, MIME, xxh3 hash, EXIF data (~61ms)
- **Video** (.mp4/.mkv/.webm): resolution, duration, FPS, codecs + keyframe mosaic (~1.5s)
- **Code/text/config**: raw content with line/word counts (~52ms)

### head / tail — first/last N lines

```bash
vlmctx head <file> -n 20        # first 20 lines of extracted content
vlmctx tail <file> -n 10        # last 10 lines
```

Works on PDFs (extracts text first, then slices lines).

### grep — content search

```bash
vlmctx grep "pattern" <dir>                       # search all files
vlmctx grep "attention" <dir> --kind document      # search only documents
vlmctx grep "TODO" <dir> --kind code               # search code files
vlmctx grep "invoice" <dir> --kind document --json # JSON output
vlmctx grep "error" <dir> -C 2                    # 2 context lines
vlmctx grep "invoice" <dir> --count                # match counts per file
```

**Warning**: grep runs L1 extraction on every matching file. On large document directories (500+ PDFs), this can take minutes. Prefer `--kind code` or `--kind text` for fast searches. Use SQL `LIKE` queries for metadata-only searches.

### keyframes — video keyframe mosaics

```bash
vlmctx keyframes <video>                        # 6x8 mosaic grid (48 frames)
vlmctx keyframes <video> --strategy scene        # scene-change detection
vlmctx keyframes <video> --num-mosaics 4         # 4 grids (192 frames)
vlmctx keyframes <video> --cols 4 --rows 4       # 4x4 grid
vlmctx keyframes <video> --json                  # JSON with mosaic paths
```

Requires `ffmpeg`. ~1s per video via parallel seeking. Output: JPEG mosaic grids suitable for VLM input.

### pages — PDF page mosaics

```bash
vlmctx pages <file.pdf>                          # 4x4 page grid
vlmctx pages <dir>                               # all PDFs in directory
vlmctx pages <file.pdf> --max-pages 8            # limit rendered pages
vlmctx pages <file.pdf> --cols 2 --rows 4        # 2x4 grid
vlmctx pages <dir> --json                        # JSON with mosaic paths
```

Renders PDF pages as thumbnails and tiles into mosaic grids. ~10ms/page. Output: JPEG mosaics suitable for VLM input.

### audio — audio extraction

```bash
vlmctx audio <video>                             # extract audio at 2x speed
vlmctx audio <video> --speed 1.0                 # original speed
vlmctx audio <video> --format mp3                # mp3 output
vlmctx audio <video> --json                      # JSON with audio path
```

Extracts audio optimized for Whisper transcription (mono, 16kHz, PCM). Requires `ffmpeg`.

## Output modes

- **TTY**: Rich formatted tables/panels (human-friendly).
- **Piped / non-TTY**: plain TSV/text or one-path-per-line (machine-readable, no ANSI codes).
- **`--json`**: JSON output. Always use this when parsing results programmatically.

## Pipe composability

```bash
# Find images, pipe to ls for metadata
vlmctx find <dir> --kind image | vlmctx ls <dir>

# Find large PDFs, pipe to wc
vlmctx find <dir> --kind document --min-size 10mb | wc -l

# Count images by extension
vlmctx find <dir> --kind image | xargs -I{} basename {} | sort | uniq -c | sort -rn
```

## Python API (alternative to CLI)

```python
from vlmctx import Context

ctx = Context("/path/to/dir")          # scans instantly
df = ctx.to_polars()                    # polars DataFrame
df = ctx.to_pandas()                    # pandas DataFrame
result = ctx.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind")
images = ctx.filter(kind="image", min_size="1MB")
text = ctx.cat("paper.pdf", level=1)
hits = ctx.grep("revenue", kind="document")
ctx.info()                              # prints Rich summary
```

## Tips

- All L0 commands (`find`, `ls`, `wc`, `tree` with `--json`) run in ~60ms via the Rust fast path.
- `sql` and `info` are slower (~300-700ms) because they use DuckDB/pyarrow.
- Start with `tree --depth 1` then `wc --by-kind` for the fastest directory overview.
- Use `--json` when you need to parse output programmatically.
- `find` returns paths only when piped; `ls` returns full metadata rows.
- `sql` is the most powerful command — any DuckDB-compatible SQL works against the `files` table.
- For PDFs, `cat --level 1` extracts text; if empty, the PDF is likely scanned/image-only — use `pages` to get visual mosaics instead.
- For videos, `keyframes` generates mosaic grids suitable for VLM inference.
- Size filters accept human units: `1kb`, `5mb`, `1gb`.
- Extension matching is case-sensitive: `.pdf` ≠ `.PDF`.

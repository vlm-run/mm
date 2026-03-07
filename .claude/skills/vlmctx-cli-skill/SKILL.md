---
name: vlmctx-cli-skill
description: >
  Use the vlmctx CLI to index, explore, query, and extract content from multi-modal directories
  containing images, videos, PDFs, code, and other files. Triggers: exploring a directory's contents,
  listing/finding files by type or size, extracting text from PDFs, getting image metadata, running SQL
  analytics on file metadata, searching across file contents, 'what files are in this folder',
  'find all images', 'show me the PDFs', 'how much storage do videos use', 'extract text from this PDF',
  'search documents for X', 'analyze this directory'.
---

# vlmctx CLI

`vlmctx` is a high-performance multi-modal context management CLI. It indexes directories instantly (<0.02ms/file), then exposes Unix-style commands for exploring, querying, and extracting content from images, videos, PDFs, code, and other files.

Always use `--json` for machine-readable output when parsing results programmatically.

## Workflow

1. Start with `vlmctx info <dir>` to get an overview (file count, size, kind breakdown).
2. Use `vlmctx describe <dir>` to see available columns and their types before writing SQL.
3. Explore with `find`, `ls`, `sql`, `grep`, `cat` as needed.

## Commands

### info — directory overview

```bash
vlmctx info <dir>
```

Returns: file count, total size, breakdown by kind (image/video/document/code/other), top extensions.

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
| kind | string | `image`, `video`, `document`, `code`, or `other` |
| is_binary | bool | Whether file is binary |
| depth | uint16 | Directory depth (0 = top-level) |
| parent | string | Parent directory name |

### find — locate files

```bash
vlmctx find <dir> --kind image                         # all images
vlmctx find <dir> --kind video                         # all videos
vlmctx find <dir> --kind document                      # all PDFs/docs
vlmctx find <dir> --ext .png,.webp                     # by extension
vlmctx find <dir> --min-size 1mb --max-size 10mb       # by size range
vlmctx find <dir> --kind image --limit 5 --json        # JSON output, capped
vlmctx find <dir> --sort size --desc --limit 10        # largest files
```

### ls — tabular listing

```bash
vlmctx ls <dir>                                         # all files, all columns
vlmctx ls <dir> --columns name,kind,size --limit 10     # select columns
vlmctx ls <dir> --sort size --desc                      # sorted
vlmctx ls <dir> --kind document --columns name,size     # filtered
vlmctx ls <dir> --sort size --desc --json               # JSON output
```

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

# Name search
vlmctx sql "SELECT name, ROUND(size/1024.0,1) as kb FROM files WHERE name LIKE '%invoice%'" --dir <dir>

# JSON output
vlmctx sql "SELECT * FROM files WHERE kind='document'" --dir <dir> --json
```

### cat — content extraction

```bash
vlmctx cat <file> --level 0     # raw file content
vlmctx cat <file> --level 1     # extracted content (default)
vlmctx cat <file> --level 2     # LLM-generated description (needs VLMCTX_LLM_BASE_URL)
```

Level 1 behavior by file type:
- **PDF**: extracts text via pypdfium2 (scanned/image-only PDFs return empty)
- **Image** (.png/.jpg/.webp/.gif): returns dimensions, MIME, xxh3 content hash
- **Text/code**: returns raw file content

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
```

Output format: `<file>:<line_number>:<matching_line>`

## Output modes

- **TTY**: Rich formatted tables/panels (human-friendly).
- **Piped / non-TTY**: plain TSV/text (machine-readable, no ANSI codes).
- **`--json`**: JSON output. Always use this when parsing results programmatically.

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

- Start with `info` then `describe` before writing SQL queries.
- Use `--json` when you need to parse output programmatically.
- `find` returns paths only; `ls` returns full metadata rows.
- `sql` is the most powerful command — any DuckDB-compatible SQL works against the `files` table.
- For PDFs, `cat --level 1` extracts text; if empty, the PDF is likely scanned/image-only.
- Size filters accept human units: `1kb`, `5mb`, `1gb`.

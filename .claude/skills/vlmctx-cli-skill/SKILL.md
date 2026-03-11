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

`vlmctx` is a high-performance multi-modal context management CLI. It indexes directories instantly (~60ms for 700 files), then exposes 6 Unix-style commands for exploring, querying, and extracting content from images, videos, PDFs, code, and other files.

Always use `--json` for machine-readable output when parsing results programmatically.

## Commands (6 total)

| Command | Purpose |
|---------|---------|
| `find` | Locate files by kind/ext/size |
| `ls` | Tabular listing, tree view, schema |
| `cat` | Content extraction (text, visual mosaics, audio) |
| `grep` | Content search across files |
| `sql` | DuckDB SQL on file index |
| `wc` | Count files, bytes, lines, tokens |

## Workflow

1. Start with `vlmctx ls <dir> --tree --depth 1` to see the directory structure.
2. Use `vlmctx wc <dir> --by-kind` to estimate token counts for LLM context budgeting.
3. Use `vlmctx ls <dir> --schema` to see available columns before writing SQL.
4. Explore with `find`, `ls`, `sql`, `grep`, `cat` as needed.
5. Use `cat --visual` / `cat --audio` for media extraction from PDFs and videos.

## find — locate files

```bash
vlmctx find <dir> --kind image                         # all images
vlmctx find <dir> --kind video                         # all videos
vlmctx find <dir> --kind document                      # all PDFs/docs
vlmctx find <dir> --kind audio                         # audio files
vlmctx find <dir> --ext .png,.webp                     # by extension
vlmctx find <dir> --min-size 1mb --max-size 10mb       # by size range
vlmctx find <dir> --kind image --limit 5 --json        # JSON output, capped
vlmctx find <dir> --sort size --desc --limit 10        # largest files
```

~63ms via Rust fast path. Piped output is one path per line. `--json` returns full metadata.

## ls — tabular listing, tree view, schema

```bash
# Tabular listing (default)
vlmctx ls <dir>                                         # all files
vlmctx ls <dir> --columns name,kind,size --limit 10     # select columns
vlmctx ls <dir> --sort size --desc --json               # sorted JSON

# Tree view (replaces old `tree` command)
vlmctx ls <dir> --tree                                  # full tree with sizes
vlmctx ls <dir> --tree --depth 1                        # top-level dirs only
vlmctx ls <dir> --tree --kind image                     # only image files
vlmctx ls <dir> --tree --json                           # JSON tree structure

# Schema (replaces old `describe` command)
vlmctx ls <dir> --schema                                # Rich table with column docs
vlmctx ls <dir> --schema --json                         # machine-readable
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

## cat — content extraction

Unified content extraction: text, head/tail, visual mosaics, audio.

```bash
# Text/metadata extraction (default mode)
vlmctx cat <file>                                       # L1 extracted content
vlmctx cat <file> --level 0                             # raw file content
vlmctx cat <file> --level 2                             # LLM caption (needs VLMCTX_BASE_URL)

# Head / tail (replaces old `head`/`tail` commands)
vlmctx cat <file> -n 20                                 # first 20 lines
vlmctx cat <file> -n -10                                # last 10 lines

# Visual mosaics (replaces old `keyframes`/`pages` commands)
vlmctx cat <file.pdf> --visual                          # PDF page mosaic grid
vlmctx cat <video.mp4> --visual                         # video keyframe mosaic
vlmctx cat <video.mp4> --visual --strategy scene        # scene-change detection
vlmctx cat <video.mp4> --visual --num-mosaics 4         # 4 grids (192 frames)
vlmctx cat <file.pdf> --visual --max-pages 8            # limit rendered pages
vlmctx cat <file> --visual --json                       # JSON with mosaic paths

# Audio extraction (replaces old `audio` command)
vlmctx cat <video.mp4> --audio                          # extract audio at 2x speed
vlmctx cat <video.mp4> --audio --speed 1.0              # original speed
vlmctx cat <video.mp4> --audio --json                   # JSON with audio path
```

Level 1 behavior by file type:
- **PDF**: text extraction via pypdfium2 (~220ms). Scanned/image-only PDFs return empty.
- **Image** (.png/.jpg/.webp/.gif): dimensions, MIME, xxh3 hash, EXIF data (~61ms)
- **Video** (.mp4/.mkv/.webm): resolution, duration, FPS, codecs + keyframe mosaic (~1.5s)
- **Code/text/config**: raw content with line/word counts (~52ms)

## wc — count files, bytes, lines, tokens

```bash
vlmctx wc <dir>                      # summary totals
vlmctx wc <dir> --by-kind            # breakdown by file kind
vlmctx wc <dir> --kind document      # only documents
vlmctx wc <dir> --json               # machine-readable
```

Estimates LLM tokens (~chars/4 for text, tile-based for images). ~65ms.

## grep — content search

```bash
vlmctx grep "pattern" <dir>                       # search all files
vlmctx grep "attention" <dir> --kind document      # search only documents
vlmctx grep "TODO" <dir> --kind code               # search code files
vlmctx grep "invoice" <dir> --kind document --json # JSON output
vlmctx grep "error" <dir> -C 2                    # 2 context lines
vlmctx grep "invoice" <dir> --count                # match counts per file
```

**Warning**: grep runs L1 extraction on every matching file. On large document directories (500+ PDFs), this can take minutes. Prefer `--kind code` or `--kind text` for fast searches.

## sql — DuckDB queries on file index

The table name is `files`. Use `ls --schema` to see columns.

```bash
# Kind breakdown with sizes
vlmctx sql "SELECT kind, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files GROUP BY kind ORDER BY mb DESC" --dir <dir>

# Extension analytics
vlmctx sql "SELECT ext, COUNT(*) as n, ROUND(AVG(size)/1024.0,1) as avg_kb FROM files GROUP BY ext ORDER BY n DESC" --dir <dir>

# Size distribution
vlmctx sql "SELECT CASE WHEN size<100*1024 THEN '<100KB' WHEN size<1e6 THEN '100KB-1MB' WHEN size<10*1e6 THEN '1-10MB' ELSE '>10MB' END as bucket, COUNT(*) as n FROM files GROUP BY bucket" --dir <dir>

# Name search
vlmctx sql "SELECT name, ROUND(size/1024.0,1) as kb FROM files WHERE name LIKE '%invoice%'" --dir <dir>

# JSON output
vlmctx sql "SELECT * FROM files WHERE kind='document'" --dir <dir> --json
```

~270-500ms (DuckDB overhead).

## Output modes

- **TTY**: Rich formatted tables/panels (human-friendly).
- **Piped / non-TTY**: plain TSV/text or one-path-per-line (machine-readable, no ANSI codes).
- **`--json`**: JSON output. Always use this when parsing results programmatically.

## Pipe composability

```bash
vlmctx find <dir> --kind image | vlmctx ls <dir>        # find images, pipe to ls
vlmctx find <dir> --kind document --min-size 10mb | wc -l  # count large PDFs
```

## Tips

- All L0 commands (`find`, `ls`, `wc` with `--json`) run in ~60ms via the Rust fast path.
- `sql` is slower (~300ms) because it uses DuckDB/pyarrow.
- Start with `ls --tree --depth 1` then `wc --by-kind` for the fastest directory overview.
- Use `--json` when you need to parse output programmatically.
- `find` returns paths only when piped; `ls` returns full metadata rows.
- `sql` is the most powerful command — any DuckDB-compatible SQL works against the `files` table.
- For PDFs, `cat` extracts text; if empty, the PDF is scanned — use `cat --visual` for page mosaics.
- For videos, `cat --visual` generates mosaic grids suitable for VLM inference.
- Size filters accept human units: `1kb`, `5mb`, `1gb`.
- Extension matching is case-sensitive: `.pdf` ≠ `.PDF`.

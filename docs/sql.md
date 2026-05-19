# mm sql

Run SQL queries against file metadata, LLM extraction outputs, and chunked content — without leaving the terminal.

## Synopsis

```bash
mm sql "QUERY" [OPTIONS]
mm sql --list-tables
```

## Options

| Flag | Short | Type | Description |
|------|-------|------|-------------|
| `--dir DIR` | `-d` | path | Directory to scan for the `files` table (default: `.`) |
| `--format FORMAT` | `-f` | enum | Output format: `rich` (default), `json`, `tsv`, `csv`, `dataset-jsonl`, `dataset-hf` |
| `--list-tables` | | flag | List available tables and their row counts |
| `--pre-index` | | flag | Index unindexed files into the persistent store before querying `files` |

## Tables

`mm sql` auto-routes queries to the correct backend based on the `FROM` clause. Three tables are available:

| Table | Source | Persistence |
|-------|--------|-------------|
| `files` | Directory scan + SQLite persistent store | Indexed entries survive across sessions; unindexed files show a diff |
| `extractions` | SQLite (`~/.local/share/mm/mm.db`) | Persistent — written by `mm cat` |
| `chunks` | SQLite (`~/.local/share/mm/mm.db`) | Persistent — written by `mm cat` |

Queries referencing `extractions` or `chunks` in the `FROM` or `JOIN` clause go to persistent SQLite directly. All other queries hit the `files` table.

```bash
# see what's in each table
mm sql --list-tables
```

## `files` table

The `files` table combines a live directory scan with the persistent metadata index. Rows from the SQLite store are loaded into an in-memory SQLite table and the user's query runs over them.

If files exist on disk but have not been indexed yet, `mm sql` shows a diff of unindexed files to stderr and prints a hint to re-run with `--pre-index`.

### Columns

| Column | Type | Description |
|--------|------|-------------|
| `uri` | TEXT | Absolute file path (primary key) |
| `name` | TEXT | Filename with extension |
| `stem` | TEXT | Filename without extension |
| `ext` | TEXT | Extension including dot (`.png`, `.pdf`) |
| `size` | INTEGER | File size in bytes |
| `modified` | REAL | Last modification timestamp (Unix epoch) |
| `created` | REAL | Creation timestamp (Unix epoch) |
| `mime` | TEXT | MIME type inferred from extension |
| `kind` | TEXT | Semantic kind: `image`, `video`, `audio`, `document`, `code`, `data`, `config`, `text`, `other` |
| `is_binary` | INTEGER | 1 if file is binary content |
| `depth` | INTEGER | Directory depth from scan root (0 = top-level) |
| `parent` | TEXT | Parent directory name |
| `width` | INTEGER | Pixel width (images / video). Null for non-media. |
| `height` | INTEGER | Pixel height. Null for non-media. |
| `content_hash` | TEXT | xxh3 content hash (hex). Null until indexed. |
| `text_preview` | TEXT | Locally-extracted text content. Null until indexed. |
| `line_count` | INTEGER | Line count for text/code files. Null for binary. |
| `word_count` | INTEGER | Word count for text/code files. |
| `language` | TEXT | Detected programming/natural language. |
| `dimensions` | TEXT | `WxH` string (e.g. `1920x1080`). |
| `pages` | INTEGER | Page count for documents. |
| `duration_s` | REAL | Duration in seconds (audio/video). |
| `fps` | REAL | Frames per second (video). |
| `magic_mime` | TEXT | Content-inspected MIME type when it differs from `mime`. |
| `exif_camera` | TEXT | Camera make and model. |
| `exif_date` | TEXT | Date/time original from EXIF. |
| `exif_gps` | TEXT | GPS coordinates. |
| `exif_orientation` | TEXT | EXIF orientation tag. |
| `video_codec` | TEXT | Video codec (e.g. `h264`, `av1`). |
| `audio_codec` | TEXT | Audio codec (e.g. `aac`, `opus`). |
| `has_audio` | INTEGER | 1 if video has an audio track. |
| `phash` | TEXT | Perceptual hash (16-digit hex) for images. |
| `indexed_at` | INTEGER | Unix timestamp when the file was last indexed. |
| `content_indexed_at` | INTEGER | Unix timestamp when content extraction ran. |

## `extractions` table

Stores the output of `mm cat` runs — one row per unique (file, profile, model, mode) combination.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Extraction ID (primary key) |
| `file_uri` | TEXT | Absolute path of the source file |
| `content_hash` | TEXT | xxh3 hash of the file at extraction time |
| `profile` | TEXT | Profile name used for the LLM call |
| `model` | TEXT | Model used for extraction |
| `mode` | TEXT | `fast` or `accurate` |
| `detail` | INTEGER | Detail flag (reserved) |
| `extra` | TEXT | Override fingerprint (pipeline/flag hash) |
| `summary` | TEXT | The extraction output text |
| `metadata` | TEXT | JSON metadata (e.g. verbose timing suffix) |
| `created_at` | INTEGER | Unix timestamp of when the extraction was stored |

## `chunks` table

Stores chunked content for vector search — one row per chunk. `mode` ∈ `metadata`, `fast`, `accurate`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-incrementing primary key |
| `extraction_id` | TEXT | Foreign key → `extractions.id` (nullable for metadata-tier chunks) |
| `file_uri` | TEXT | Absolute path of the source file |
| `content_hash` | TEXT | xxh3 hash of the file |
| `profile` | TEXT | Profile name |
| `model` | TEXT | Model name |
| `mode` | TEXT | `metadata`, `fast`, or `accurate` |
| `chunk_idx` | INTEGER | Chunk sequence index within the file |
| `chunk_text` | TEXT | Chunk content |
| `created_at` | INTEGER | Unix timestamp |

## Examples

### Discovery and inventory

```bash
# count files by kind
mm sql "SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC"

# file count and total size by extension
mm sql "SELECT ext, COUNT(*) as n, SUM(size) as total_bytes FROM files GROUP BY ext ORDER BY total_bytes DESC"

# total storage used per kind
mm sql "SELECT kind, SUM(size) as bytes, COUNT(*) as files FROM files GROUP BY kind ORDER BY bytes DESC"

# top-level directory breakdown (depth=0)
mm sql "SELECT parent, COUNT(*) as files, SUM(size) as bytes FROM files WHERE depth=0 GROUP BY parent"

# files modified in the last 7 days (epoch: now - 7*86400)
mm sql "SELECT name, kind, modified FROM files WHERE modified > strftime('%s','now','-7 days') ORDER BY modified DESC"

# duplicate detection: files sharing a content_hash
mm sql "SELECT content_hash, COUNT(*) as n, GROUP_CONCAT(name, ', ') as names FROM files WHERE content_hash IS NOT NULL GROUP BY content_hash HAVING n > 1"

# largest 20 files across all kinds
mm sql "SELECT name, kind, size FROM files ORDER BY size DESC LIMIT 20"

# all files in a specific directory
mm sql "SELECT name, kind, size FROM files WHERE kind='image'" --dir ~/photos
```

### Image queries

```bash
# largest images
mm sql "SELECT name, size FROM files WHERE kind='image' ORDER BY size DESC LIMIT 10"

# images with GPS coordinates
mm sql "SELECT name, exif_gps, exif_date FROM files WHERE exif_gps IS NOT NULL"

# images from a specific camera
mm sql "SELECT name, exif_camera, exif_date FROM files WHERE exif_camera LIKE '%iPhone%'"

# images taken on a specific date
mm sql "SELECT name, exif_date FROM files WHERE exif_date LIKE '2024-03%' ORDER BY exif_date"

# images by resolution (widest first)
mm sql "SELECT name, width, height, width*height as pixels FROM files WHERE kind='image' ORDER BY pixels DESC LIMIT 10"

# images missing EXIF data
mm sql "SELECT name FROM files WHERE kind='image' AND exif_date IS NULL"

# potentially misnamed files (magic_mime differs from mime)
mm sql "SELECT name, mime, magic_mime FROM files WHERE magic_mime IS NOT NULL AND magic_mime != mime"

# images by perceptual hash (for duplicate grouping)
mm sql "SELECT phash, COUNT(*) as n, GROUP_CONCAT(name, ', ') as names FROM files WHERE phash IS NOT NULL GROUP BY phash HAVING n > 1"
```

### Video and audio queries

```bash
# all videos with duration and codec
mm sql "SELECT name, duration_s, fps, video_codec, audio_codec FROM files WHERE kind='video'"

# longest videos
mm sql "SELECT name, ROUND(duration_s/60, 1) as minutes, video_codec FROM files WHERE kind='video' ORDER BY duration_s DESC"

# videos without audio track
mm sql "SELECT name, duration_s FROM files WHERE kind='video' AND has_audio=0"

# videos by codec
mm sql "SELECT video_codec, COUNT(*) as n FROM files WHERE kind='video' GROUP BY video_codec"

# audio files longer than 5 minutes
mm sql "SELECT name, ROUND(duration_s/60, 1) as minutes FROM files WHERE kind='audio' AND duration_s > 300 ORDER BY duration_s DESC"

# total media duration
mm sql "SELECT kind, ROUND(SUM(duration_s)/3600, 2) as hours FROM files WHERE kind IN ('video','audio') GROUP BY kind"
```

### Document queries

```bash
# PDFs sorted by page count
mm sql "SELECT name, pages, size FROM files WHERE ext='.pdf' ORDER BY pages DESC"

# documents without extracted text (unindexed)
mm sql "SELECT name, kind FROM files WHERE kind='document' AND text_preview IS NULL"

# average page count by document kind
mm sql "SELECT ext, AVG(pages) as avg_pages, COUNT(*) as n FROM files WHERE pages IS NOT NULL GROUP BY ext"
```

### Code and text queries

```bash
# code files by language
mm sql "SELECT language, COUNT(*) as files, SUM(line_count) as total_lines FROM files WHERE kind='code' GROUP BY language ORDER BY total_lines DESC"

# largest source files
mm sql "SELECT name, language, line_count, word_count FROM files WHERE kind='code' ORDER BY line_count DESC LIMIT 20"

# files with unusually high line counts (> 1000 lines)
mm sql "SELECT name, line_count FROM files WHERE line_count > 1000 ORDER BY line_count DESC"

# word count across all text files
mm sql "SELECT SUM(word_count) as total_words, COUNT(*) as files FROM files WHERE kind IN ('text','code')"
```

### `extractions` table

```bash
# all cached extractions
mm sql "SELECT file_uri, mode, model, SUBSTR(summary,1,120) as preview FROM extractions LIMIT 20"

# extractions for accurate mode only
mm sql "SELECT file_uri, model, summary FROM extractions WHERE mode='accurate'"

# extractions by profile and model
mm sql "SELECT profile, model, COUNT(*) as n FROM extractions GROUP BY profile, model ORDER BY n DESC"

# most recently cached files
mm sql "SELECT file_uri, mode, datetime(created_at,'unixepoch') as ts FROM extractions ORDER BY created_at DESC LIMIT 10"

# full-text search in extraction summaries
mm sql "SELECT file_uri, SUBSTR(summary,1,200) FROM extractions WHERE summary LIKE '%attention mechanism%'"

# extraction size distribution
mm sql "SELECT mode, AVG(LENGTH(summary)) as avg_chars, MAX(LENGTH(summary)) as max_chars FROM extractions GROUP BY mode"

# files extracted more than once (multiple modes or models)
mm sql "SELECT file_uri, COUNT(*) as n FROM extractions GROUP BY file_uri HAVING n > 1 ORDER BY n DESC"

# cache coverage: how many indexed files have an extraction
mm sql "SELECT e.mode, COUNT(DISTINCT e.file_uri) as extracted FROM extractions e GROUP BY e.mode"
```

### `chunks` table

```bash
# chunks by content tier
mm sql "SELECT mode, COUNT(*) as n, AVG(LENGTH(chunk_text)) as avg_chars FROM chunks GROUP BY mode"

# chunks for a specific file
mm sql "SELECT chunk_idx, SUBSTR(chunk_text,1,200) FROM chunks WHERE file_uri LIKE '%paper.pdf%' ORDER BY chunk_idx"

# files with the most chunks
mm sql "SELECT file_uri, COUNT(*) as chunks FROM chunks GROUP BY file_uri ORDER BY chunks DESC LIMIT 10"

# long chunks (may indicate unsplit content)
mm sql "SELECT file_uri, chunk_idx, LENGTH(chunk_text) as chars FROM chunks WHERE LENGTH(chunk_text) > 2000 ORDER BY chars DESC"

# indexed coverage: distinct files in chunks vs extractions
mm sql "SELECT 'chunks' as tbl, COUNT(DISTINCT file_uri) as files FROM chunks UNION ALL SELECT 'extractions', COUNT(DISTINCT file_uri) FROM extractions"
```

### Cross-table queries

```bash
# files that have been extracted
mm sql "SELECT f.name, f.kind, e.mode, e.model FROM files f JOIN extractions e ON f.uri = e.file_uri"

# files not yet extracted (no entry in extractions)
mm sql "SELECT f.name, f.kind FROM files f LEFT JOIN extractions e ON f.uri = e.file_uri WHERE e.file_uri IS NULL"

# extraction summary alongside file size
mm sql "SELECT f.name, f.size, e.mode, SUBSTR(e.summary,1,100) as preview FROM files f JOIN extractions e ON f.uri = e.file_uri ORDER BY f.size DESC LIMIT 10"

# chunk count per file plus its kind
mm sql "SELECT f.name, f.kind, COUNT(c.id) as chunks FROM files f JOIN chunks c ON f.uri = c.file_uri GROUP BY f.uri ORDER BY chunks DESC"
```

### Indexing and schema introspection

```bash
# index files first, then query
mm sql "SELECT kind, COUNT(*) as n FROM files GROUP BY kind" --dir ~/data --pre-index

# inspect available PRAGMA information
mm sql "PRAGMA table_info(files)"
mm sql "PRAGMA table_info(extractions)"
mm sql "PRAGMA table_info(chunks)"

# list tables and row counts
mm sql --list-tables
```

### Machine-readable output

```bash
# JSON
mm sql "SELECT name, size FROM files WHERE kind='image'" --format json

# TSV for scripting
mm sql "SELECT kind, COUNT(*) as n FROM files GROUP BY kind" --format tsv

# CSV for spreadsheet import
mm sql "SELECT name, kind, size FROM files ORDER BY size DESC" --format csv

# pipe into jq
mm sql "SELECT name, size FROM files ORDER BY size DESC LIMIT 5" --format json | jq '.[] | .name'

# pipe into awk
mm sql "SELECT name, size FROM files WHERE kind='video'" --format tsv | awk -F'\t' 'NR>1 {sum+=$2} END {print sum " bytes"}'
```

## Table routing

`mm sql` inspects the query's `FROM` and `JOIN` clauses to determine routing:

- If any clause references `extractions`, `chunks`, or `chunks_vec` → persistent SQLite direct
- `PRAGMA` queries → persistent SQLite direct
- Everything else → scanned `files` table (in-memory SQLite over the persistent index)

## Unindexed files diff

When querying the `files` table without `--pre-index`, `mm sql` shows a diff of files that exist on disk but have not been indexed yet. Up to 5 unindexed paths are shown; the remainder are summarized with a count. A re-run hint is printed to stdout:

```
To include these files, run:
  mm sql "SELECT ..." --dir ~/data --pre-index
```

## Notes

- The `files` table in `mm sql` is sourced from the **persistent store** (SQLite), not a fresh live scan. Files are indexed into the persistent store by `mm cat`, `mm peek`, or `mm sql --pre-index`. Use `mm find` for a live scan with no dependency on the index.
- Rich output trims columns to a readable subset (`name`, `kind`, `ext`, `size`, `parent`, `mime`, `width`, `height`, `modified`, `depth`) when the full column set would be too wide. Use `--format tsv` or `--format json` to see all columns.
- `extractions.summary` is the full LLM-generated text. It can be long — use `SUBSTR(summary, 1, 200)` to truncate in queries.
- `chunks.mode = 'metadata'` rows contain locally-extracted metadata (text preview, EXIF, etc.) without any LLM call. `fast` and `accurate` chunks correspond to pipeline extraction outputs.

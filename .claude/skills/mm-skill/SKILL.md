---
name: mm-skill
description: >
  Use the mm CLI to index, explore, query, and extract content from multi-modal directories
  containing images, videos, PDFs, code, and other files. Triggers: exploring a directory's contents,
  listing/finding files by type or size, extracting text from PDFs, getting image metadata, running SQL
  analytics on file metadata, searching across file contents, counting tokens, viewing directory trees,
  extracting PDF page mosaics, video keyframe extraction, 'what files are in this folder',
  'find all images', 'show me the PDFs', 'how much storage do videos use', 'extract text from this PDF',
  'search documents for X', 'analyze this directory', 'how many tokens', 'show the tree'.
---

# mm CLI

`mm` is a high-performance multi-modal context management CLI. It indexes directories instantly (~60ms for 700 files), then exposes Unix-style commands for exploring, querying, and extracting content from images, videos, PDFs, code, and other files.

Always use `--format json` for machine-readable output when parsing results programmatically.

## Installation

```bash
# First run `mm --help` or `mm --version` to confirm mm isn't already installed

curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh
```

## Commands

| Command   | Purpose                                                                     |
| --------- | --------------------------------------------------------------------------- |
| `find`    | Locate/list files by name/kind/ext/size, tabular listing, tree view, schema |
| `cat`     | Content extraction (auto-detected by file type × level)                     |
| `grep`    | Content search — text (L0/L1) and semantic (L2 via embeddings)              |
| `sql`     | SQL on files, L2 results, and chunks (auto-routed)                          |
| `wc`      | Count files, bytes, lines, tokens                                           |
| `bench`   | Benchmark suite (L0/L1/L2) with statistical analysis                        |
| `config`  | Extraction mode settings (show, init, set, reset-db)                        |
| `profile` | Manage LLM provider profiles (list, add, update, use, remove)               |

## Workflow

1. Start with `mm find <dir> --tree --depth 1` to see the directory structure.
2. Use `mm wc <dir> --by-kind` to estimate token counts for LLM context budgeting.
3. Use `mm find <dir> --schema` to see available columns before writing SQL.
4. Explore with `find`, `sql`, `grep`, `cat` as needed.
5. Use `mm cat <file> -l 2` for LLM-powered descriptions (auto-generates mosaics for video).

## find — locate files, tabular listing, tree view, schema

```bash
mm find <dir> --kind image                           # all images
mm find <dir> --kind video                           # all videos
mm find <dir> --kind document                        # all PDFs/docs
mm find <dir> --kind audio                           # audio files
mm find <dir> --name "test_.*\.py"                   # filter by name (regex)
mm find <dir> -n config                              # filter by name (substring)
mm find <dir> --ext .png,.webp                       # by extension
mm find <dir> --min-size 1mb --max-size 10mb         # by size range
mm find <dir> --kind image --limit 5 --format json   # JSON output, capped
mm find <dir> --sort size --reverse --limit 10       # largest files
```

~63ms via Rust fast path. Piped output is one path per line. `--format json` returns full metadata.

```bash
# Tabular listing (default)
mm find <dir>                                         # all files
mm find <dir> --columns name,kind,size --limit 10     # select columns
mm find <dir> --sort size --reverse --format json     # sorted JSON

# Tree view
mm find <dir> --tree                                  # full tree with sizes
mm find <dir> --tree --depth 1                        # top-level dirs only
mm find <dir> --tree --kind image                     # only image files
mm find <dir> --tree --format json                    # JSON tree structure

# Schema inspection
mm find <dir> --schema                                # Rich table with column docs
mm find <dir> --schema --format json                  # machine-readable
```

Columns in the `files` table:

| Column    | Type      | Description                                                                      |
| --------- | --------- | -------------------------------------------------------------------------------- |
| path      | string    | Relative path from scan root                                                     |
| name      | string    | File name with extension                                                         |
| stem      | string    | File name without extension                                                      |
| ext       | string    | Extension including dot (`.png`, `.pdf`)                                         |
| size      | uint64    | File size in bytes                                                               |
| modified  | timestamp | Last modification time                                                           |
| created   | timestamp | Creation time                                                                    |
| mime      | string    | MIME type (`image/png`, `application/pdf`)                                       |
| kind      | string    | `image`, `video`, `document`, `code`, `audio`, `data`, `config`, `text`, `other` |
| is_binary | bool      | Whether file is binary                                                           |
| depth     | uint16    | Directory depth (0 = top-level)                                                  |
| parent    | string    | Parent directory path                                                            |
| width     | uint32    | Pixel width (images only, null otherwise)                                        |
| height    | uint32    | Pixel height (images only, null otherwise)                                       |

## cat — content extraction (auto-detected)

Behaviour is auto-detected from (file type × processing level). No mode flags needed.

```bash
# Text/metadata extraction (L1 default, <100ms for media)
mm cat <file>                                       # L1 extracted content
mm cat <file> --level 0                             # raw file content
mm cat <file> --level 2                             # LLM caption (needs configured profile)
mm cat <file> -l 2 --detail                         # ~80-word LLM description
mm cat <file> -l 2                                  # basic LLM caption (default)
mm cat <file> -l 2 --mode fast                       # fast extraction (10 words + 5 tags)
mm cat <file> -l 2 --mode accurate                   # detailed extraction (200 words + 10 tags)
mm cat <file> -l 2 --no-cache                       # bypass cache, force fresh LLM call

# Head / tail
mm cat <file> -n 20                                 # first 20 lines
mm cat <file> -n -10                                # last 10 lines

# Video L2 (auto-generates keyframe mosaics → LLM description)
mm cat <video.mp4> -l 2                             # keyframe mosaic → LLM description
mm cat <video.mp4> -l 2 --video-mosaic-strategy scene  # scene-change mosaics
mm cat <video.mp4> -l 2 --video-mosaic-count 4       # 4 mosaic grids
mm cat <video.mp4> -l 2 --output-dir ./mosaics       # save mosaics to specific dir

# PDF L2
mm cat <file.pdf> -l 2 --max-pages 8                # limit rendered pages

# Output
mm cat <file> --format json                          # JSON output
```

Level 1 behavior by file type (<100ms target):

- **PDF** (.pdf): text extraction via pypdfium2. Scanned/image-only PDFs return empty.
- **Document** (.docx, .pptx): markdown extraction via docling at L2.
- **Image** (.png/.jpg/.webp/.gif/.bmp/.tiff/.svg): dimensions, MIME, xxh3 hash, EXIF data.
- **Video** (.mp4/.mkv/.webm/.avi/.mov): resolution, duration, FPS, codecs (metadata only, no ffmpeg).
- **Audio** (.mp3/.wav/.flac/.aac/.ogg/.m4a): duration, codec, bitrate (metadata only).
- **Code/text/config**: raw content passthrough.

## wc — count files, bytes, lines, tokens

```bash
mm wc <dir>                      # summary totals
mm wc <dir> --by-kind            # breakdown by file kind
mm wc <dir> --kind document      # only documents
mm wc <dir> --format json        # machine-readable
```

Estimates LLM tokens (~chars/4 for text, tile-based for images). ~65ms.

## grep — content search (text + semantic)

```bash
# Text search (L0/L1 — regex matching)
mm grep "pattern" <dir>                                # search all files
mm grep "attention" <dir> --kind document              # search only documents
mm grep "TODO" <dir> --kind code                       # search code files
mm grep "invoice" <dir> --kind document --format json  # JSON output
mm grep "error" <dir> -C 2                             # 2 context lines
mm grep "invoice" <dir> --count                        # match counts per file
mm grep "def " <dir> --kind code --level 0             # search raw content (L0)

# Semantic search (L2 — vector similarity via embeddings)
mm grep "financial projections" <dir> -l 2             # semantic search across all files
mm grep "patient diagnosis" <dir> -l 2 --kind document # semantic search in documents only
mm grep "architecture overview" <dir> -l 2 --format json  # JSON output with distances
mm grep "revenue forecast" <dir> -l 2 --index          # auto-index unindexed files before search
find <dir> -name * | mm grep "revenue forecast" -l 2  # semantic search piped files
```

**Warning**: L0/L1 grep runs extraction on every matching file. On large document directories (500+ PDFs), this can take minutes. Prefer `--kind code` or `--kind text` for fast text searches.

**L2 semantic search** uses embeddings stored in sqlite-vec. Files must be indexed first — use `--index` to auto-index on demand, or manually via `mm cat <file> -l 2`. Returns top-k results ranked by vector distance.

## sql — SQL queries on files, L2 results, and chunks

Four tables available. Table is auto-detected from the `FROM` clause:

- `files` — L0+L1 file metadata (via `--dir`, or persistent SQLite)
- `l2_results` — LLM-generated summaries (persistent SQLite)
- `chunks` — chunked L2 content (persistent SQLite)
- `chunks_vec` — embedding vectors for semantic search (sqlite-vec virtual table)

```bash
# File metadata (scan + SQLite)
mm sql "SELECT kind, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb FROM files GROUP BY kind ORDER BY mb DESC" --dir <dir>
mm sql "SELECT * FROM files WHERE kind='document'" --dir <dir> --format json

# L2 results (SQLite direct)
mm sql "SELECT file_uri, profile, model, summary FROM l2_results LIMIT 10"
mm sql "SELECT COUNT(*) as n FROM l2_results"

# Chunks and embeddings (SQLite direct)
mm sql "SELECT file_uri, chunk_idx, LENGTH(chunk_text) as len FROM chunks"

# Pre-index unindexed files before query
mm sql "SELECT kind, COUNT(*) as n FROM files GROUP BY kind" --dir <dir> --pre-index

# List available tables
mm sql --list-tables
```

Stored table queries: ~100-180ms. Files queries: ~1.2s (includes directory scan).

## bench — benchmark suite

```bash
mm bench <dir>                          # full benchmark (L0 + L1 + L2 fast)
mm bench <dir> --rounds 5               # more measurement rounds
mm bench <dir> --mode accurate           # include accurate-mode L2 benchmarks
mm bench <dir> --mode all                # run both fast and accurate L2
mm bench <dir> --format json             # JSON output for archival
```

Runs 24 commands (L0×10, L1×8, L2×6) with statistical analysis and bits/s throughput.

## config — extraction mode settings

```bash
mm config show                                  # show current config
mm config init                                  # create config with default profile
mm config init --force                          # overwrite existing config
mm config set mode.fast.whisper_model tiny       # set a config value
mm config set mode.accurate.beam_size 5          # set a config value
mm config reset-db                              # delete all databases and caches (with confirmation)
mm config reset-db --yes                        # skip confirmation
```

## profile — LLM provider management

Provider settings are managed through **profiles** stored in `~/.config/mm/mm.toml`.

```bash
mm profile list                                            # list all profiles (● = active)
mm profile list --format json                              # JSON output
mm profile add openrouter --base-url https://openrouter.ai/api/v1 --model vlm-1  # add (--base-url and --model required)
mm profile update openrouter --model qwen3-vl:8b           # update fields on existing profile
mm profile use openrouter                                  # switch active profile
mm profile remove openrouter                               # remove (cannot remove active or 'default')
```

> Active profile resolved as: `--profile` flag > `MM_PROFILE` env > `active_profile` in config file > `"default"`.

Per-command profile selection:

```bash
mm --profile openrouter cat photo.png -l 2       # one-off override
MM_PROFILE=openrouter mm cat photo.png -l 2      # env override
```

## Output formats

- **TTY**: Rich formatted tables/panels (human-friendly).
- **Piped / non-TTY**: plain TSV/text or one-path-per-line (machine-readable, no ANSI codes).
- **`--format json`**: JSON output. Always use this when parsing results programmatically.
- **`--format tsv`**: Tab-separated values. Maximum token efficiency.
- **`--format csv`**: Comma-separated values.
- **`--format dataset-jsonl`**: JSONL for dataset export.
- **`--format dataset-hf`**: HuggingFace Datasets format.

## Pipe composability

```bash
mm find <dir> --kind image | mm cat               # find images, extract metadata
mm find <dir> --kind document --min-size 10mb | wc -l  # count large PDFs
mm find <dir> --kind video --format json | jq '.[].name'  # extract video names
```

## Processing Levels

| Level | What                                                                | Speed             | How                                                            |
| ----- | ------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------- |
| L0    | File metadata (path, size, kind, ext, timestamps, dimensions)       | ~60ms / 700 files | Rust `stat()` + extension classification + image headers       |
| L1    | Content extraction (text from PDF, image hash/EXIF, video metadata) | <100ms/file       | pypdfium2 (PDF), Rust mmap (images), mp4parse/matroska (video) |
| L2    | Semantic understanding (captions, descriptions)                     | Varies            | LLM API via active profile                                     |

## Tips

- All L0 commands (`find`, `wc` with `--format json`) run in ~60ms via the Rust fast path.
- `sql` on stored tables runs in ~100-180ms; `files` queries are ~1.2s (includes scan).
- Start with `find --tree --depth 1` then `wc --by-kind` for the fastest directory overview.
- Use `mm find . --tree` to explore project structure.
- Use `--format json` when you need to parse output programmatically.
- `find` returns paths only when piped, else it returns full metadata rows.
- For exhaustive path lists, prefer `mm find <dir> --columns path | tail -n +2` and pipe/redirect as needed.
- Start with `mm find <dir> --tree --depth 1` then `mm wc <dir> --by-kind` for the fastest directory overview.
- Use `--format json` when you need to parse output programmatically.
- `find` returns paths only when piped, full metadata rows in TTY.
- `sql` is the most powerful command — queries auto-route to in-memory SQLite (`files`) or persistent SQLite (`l2_results`, `chunks`). Use `--list-tables` to see available tables.
- For PDFs, `cat` extracts text at L1; if empty, the PDF contains scanned images only.
- For videos, `cat -l 2` auto-generates keyframe mosaics and sends to LLM for description.
- L2 uses the `openai` Python SDK via the active profile. Temperature defaults to 0.1.
- Check available profiles with `mm profile list` and set an active profile with `mm profile use <profile_name>`.
- If `cat -l 2` returns `[LLM error: Connection error.]`, immediately retry with per-command profile override (e.g., `mm --profile gemini cat <file> -l 2 --detail`). If L2 still fails after trying all the available profiles, fallback to L0+L1 output.
- L2 modes: (default, simple LLM captions), `--mode fast` (10 words + tags), `--mode accurate` (200 words + tags).
- Use `--mode fast` for quick L2 summaries (10 words), `--mode accurate` for detailed ones (200 words).
- Use `--no-cache` with `cat -l 2` to force a fresh LLM call.
- L2 semantic grep (`mm grep "query" <file_path> -l 2`) uses embeddings via sqlite-vec for vector similarity search.
- Size filters accept human units: `1kb`, `5mb`, `1gb`.
- Extension matching is case-sensitive: `.pdf` ≠ `.PDF`.

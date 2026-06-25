# Overview

`mm` is a Unix-style CLI for multimodal file understanding. It scans, inspects, extracts, searches, and benchmarks files of any kind — images, video, audio, PDFs, code, and plain text — through a consistent nine-command surface.

## Commands

| Command | Purpose |
|---------|---------|
| [`find`](find.md) | List and filter files with metadata — like `fd` or `find` |
| [`wc`](wc.md) | Count files, bytes, estimated lines and tokens — like `wc` for LLM context |
| [`peek`](peek.md) | Directly extracted file metadata: dimensions, EXIF, codec, hash |
| [`grep`](grep.md) | Search file contents with regex, FTS, or semantic vector search |
| [`cat`](cat.md) | Extract and describe file content — pipeline-driven, LLM-capable |
| [`sql`](sql.md) | SQL queries over file metadata, extractions, and chunks |
| [`bench`](bench.md) | Benchmark all subcommands with statistical analysis |
| [`profile`](profile.md) | Manage LLM provider profiles: list, add, update, use, remove, clone |
| [`config`](config.md) | Configuration & diagnostics: show, init, set, reset-db, reset-profiles, reset, doctor |

## Global flags

These flags are accepted before any subcommand.

| Flag | Description | Default |
|------|-------------|---------|
| `--profile / -p NAME` | Use a specific named profile for this invocation | Active profile |
| `--color auto\|always\|never` | Control ANSI color output | `auto` |
| `--debug` | Enable debug logging (Python `mm` logger + Rust `RUST_LOG=debug` tracing) | off |
| `--version / -v` | Print version and exit | — |

```bash
mm --version
mm --profile openai cat photo.png -m accurate
mm --color never find ~/data --format tsv
mm --debug cat photo.png -m accurate                # debug logging
```

Profile resolution order: `--profile` flag > `MM_PROFILE` env var > `active_profile` in config > `"ollama"`.

## Output formats

Every command that produces tabular output accepts `--format / -f`:

| Format | Description | Default |
|--------|-------------|---------|
| `rich` | Rich-formatted tables and panels | TTY default |
| `tsv` | Tab-separated values, no ANSI | Pipe default |
| `csv` | Comma-separated values | |
| `json` | Compact JSON when piped, indented in TTY | |
| `pretty-json` | Always-indented JSON | |
| `dataset-jsonl` | Newline-delimited JSON records | |
| `dataset-hf` | HuggingFace Dataset export | |

`mm bench` additionally supports `stdout` as a format (bench snapshot mode).

## File kinds

Every file is assigned one of nine semantic kind labels:

| Kind | Description |
|------|-------------|
| `image` | PNG, JPEG, GIF, WebP, TIFF, BMP, HEIC, etc. |
| `video` | MP4, MOV, MKV, WebM, AVI, etc. |
| `audio` | MP3, WAV, FLAC, OGG, M4A, AAC, Opus, etc. |
| `document` | PDF, DOCX, PPTX, XLSX, ODT, and other office formats |
| `code` | Source files: Python, Rust, JavaScript, Go, Java, etc. |
| `data` | CSV, JSON, Parquet, Arrow, and other structured data |
| `config` | TOML, YAML, INI, dotfiles, and environment configs |
| `text` | Plain text, Markdown, RST, logs |
| `other` | Everything else |

Use `--kind` on `find`, `wc`, and `grep` to filter by one or more kinds (comma-separated).

## Unix composability

Commands follow Unix conventions and compose naturally through pipes:

```bash
# pipe find output into wc
mm find ~/data --kind image | mm wc

# pipe find output into cat
mm find ~/data --kind document --ext .pdf | mm cat -m accurate

# pipe find output into grep
mm find ~/project --kind code | mm grep "TODO"

# chain with standard tools
mm find ~/data --format tsv | awk -F'\t' '$2 == "video" {print $3}'
mm find ~/data --format json | jq '.[] | select(.size > 1048576)'
```

When stdin is not a TTY, `mm` reads file paths from stdin automatically. Output format defaults to `tsv` when piped and `rich` in a terminal.

## Performance

The scanner is Rust-backed (via `mm-core` and PyO3), using:

- **`ignore` crate** for gitignore-aware parallel directory walking
- **`rayon`** for parallel metadata extraction
- **`xxhash-rust`** (xxh3) for fast content fingerprinting via mmap
- **Arrow IPC** for zero-copy data transfer from Rust to Python

Typical cold-start scan: ~5 ms for 250 files. Metadata operations bypass Python entirely in the fast path.

## SQL

`mm sql` runs SQL queries against three tables populated from the scanned directory and the persistent store.

```bash
mm sql "SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC"
mm sql "SELECT name, size FROM files WHERE kind = 'image' ORDER BY size DESC LIMIT 10"
mm sql --list-tables
```

| Table | Source | Notes |
|-------|--------|-------|
| `files` | Directory scan + SQLite | Persistent store; reconciled against disk on each query |
| `extractions` | SQLite | LLM-generated summaries from `mm cat` |
| `chunks` | SQLite | Chunked content + embeddings; `mode` ∈ `metadata`, `fast`, `accurate` |

## Configuration files

| Path | Purpose |
|------|---------|
| `~/.config/mm/mm.toml` | Extraction mode defaults, transcription backend |
| `~/.config/mm/profiles.toml` | LLM provider profiles |
| `~/.local/share/mm/mm.db` | SQLite database (metadata, extractions, embeddings) |
| `~/.config/mm/pipelines/` | User-overridden pipeline YAMLs |

# mm

High-performance multimodal context management library + CLI.

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

Commands that mirror familiar Unix tools but operate on multimodal semantics.
Indexing is implicit — every command auto-builds a metadata index on first use.

Metadata commands (`find`, `wc` with `--format json`) run in **~60ms** on 700 files via the Rust fast path.

### Quick start

```bash
mm --version                                 # print version
mm find ~/data --tree --depth 1              # directory overview with sizes
mm wc ~/data --by-kind                       # file/byte/token counts by kind
mm find ~/data --kind image --format json    # find all images (60ms)
mm cat paper.pdf                             # extract text from PDF (fast mode)
mm cat video.mp4                             # video metadata (<100ms)
mm cat video.mp4 -m accurate                 # keyframe mosaic → LLM description
mm cat photo.png -m accurate                 # LLM caption
mm cat photo.png -p resize                   # use named encoder
```

### Command reference

| Command | Purpose | Key flags |
|---------|---------|-----------|
| `find`  | Find/list files, tree view, schema | `--name`, `--kind`, `--ext`, `--min-size`, `--max-size`, `--sort`, `--reverse`, `--columns`, `--tree`, `--depth`, `--schema`, `--limit`, `--no-ignore`, `--format` |
| `cat` | Content extraction (auto-detected by file type × mode) | `--mode fast/accurate`, `-p` (pipeline), `-n`, `--no-cache`, `-v`, `--encode.*`, `--generate.*`, `--list-pipelines`, `--list-encoders`, `--format` |
| `grep` | Content search across files | `--kind`, `--ext`, `-C`, `--count`, `-i`, `--level`, `--index`, `--no-ignore`, `--format` |
| `sql` | SQL queries on file index, results, chunks, and embeddings | `--dir`, `--pre-index`, `--format`, `--list-tables` |
| `wc` | Count files, size, lines (est.), tokens (est.) | `--kind`, `--by-kind`, `--format` |
| `bench` | Benchmark suite | `--rounds`, `--warmup`, `--mode`, `--format` |
| `config` | Extraction mode settings | `show`, `init`, `set`, `reset-db`, `reset-profiles`, `reset` |
| `profile` | Manage LLM provider profiles | `list`, `add`, `update`, `use`, `remove`, `--format` |

### find — locate/list, tree, and schema

```bash
mm find ~/data --kind image                               # all images
mm find ~/data --kind video --sort size --reverse         # videos by size
mm find ~/data --ext .pdf --min-size 10mb                 # large PDFs
mm find ~/data --kind image --limit 5 --format json       # JSON output
mm find ~/data --name "test_.*\.py"                       # regex name match
mm find ~/data -n config                                  # substring name match

mm find ~/data --sort size --reverse --limit 20        # tabular listing
mm find ~/data --kind document --columns name,size,ext
mm find ~/data --tree --depth 2                        # hierarchical tree view
mm find ~/data --tree --kind video                     # tree filtered to videos
mm find ~/data --schema                                # column names, types, descriptions
mm find ~/data --format json                           # full metadata JSON
mm find ~/data --no-ignore                             # include gitignored files
```

### cat — content extraction

```bash
mm cat paper.pdf                               # extract text (fast mode, no LLM)
mm cat paper.pdf -n 20                         # first 20 lines (head)
mm cat paper.pdf -n -20                        # last 20 lines (tail)
mm cat photo.png                               # image dims, MIME, hash, EXIF
mm cat video.mp4                               # resolution, duration, codecs (<100ms)
mm cat video.mp4 -m accurate                   # mosaic → LLM description
mm cat photo.png -m accurate                   # LLM caption
mm cat photo.png -p resize                     # use named encoder
mm cat photo.png -p my-pipeline.yaml           # custom pipeline YAML
mm cat video.mp4 -m accurate --no-cache        # force fresh LLM call
mm cat photo.png -m accurate -v                # verbose (shows pipeline tree)
mm cat --list-pipelines                        # list registered pipelines
mm cat --list-encoders                         # list registered encoders
```

### wc — count files, size, tokens

```bash
mm wc ~/data --by-kind
mm wc ~/data --by-kind --format json
```

### grep — content search

```bash
mm grep "attention" ~/data --kind document
mm grep "TODO" ~/data --kind code
mm grep "invoice" ~/data --count               # match counts per file
mm grep "Quantum Phase" ~/data -i              # case-insensitive search
mm grep "secret" ~/data --no-ignore            # search gitignored files
mm grep "revenue forecast" ~/data --level 2    # semantic (vector) search
mm grep "architecture" ~/data --level 2 --index  # auto-index before search
```

### sql — query the index

Queries file metadata via scan + SQLite, or results and chunks from the persistent SQLite store.

```bash
mm find ~/data --schema                          # see available columns
mm sql "SELECT kind, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb \
  FROM files GROUP BY kind ORDER BY mb DESC" --dir ~/data

# Query stored tables directly (auto-detected from table name)
mm sql "SELECT file_uri, summary FROM l2_results LIMIT 10"
mm sql "SELECT file_uri, chunk_idx, LENGTH(chunk_text) FROM chunks"
mm sql "SELECT * FROM files WHERE kind='image'" --dir ~/data --pre-index  # index before query
mm sql --list-tables                              # show available tables
```

### Output modes

- **TTY**: Rich formatted tables/panels
- **Piped**: plain TSV/text (machine-readable, no ANSI)
- **`--format json`**: JSON output on any command that supports it
- **`--format csv`**: Comma-separated values
- **`--format dataset-jsonl`**: JSONL for dataset export
- **`--format dataset-hf`**: HuggingFace Datasets format (requires `--output-dir`)

### Verbose mode (`--verbose` / `-v`)

`mm cat <file> [OPTIONS] --verbose` shows the pipeline execution tree after content:

```
pipeline
  ├─ encode: resize · 0.0s → 1 parts (1 image)
  └─ generate: ollama · 2.3s · 354→195 tokens
```

## Python API

```python
from mm import Context

ctx = Context("~/data/domains")
print(ctx)  # Context(root='/Users/.../domains', files=702)

# DataFrame export
df = ctx.to_polars()         # polars.DataFrame (zero-copy)
df = ctx.to_pandas()         # pandas.DataFrame

# SQL via SQLite
result = ctx.sql("SELECT kind, COUNT(*) as n FROM files GROUP BY kind ORDER BY n DESC")

# Chainable filtering
big_images = ctx.filter(kind="image", min_size="1MB")

# Content access
text  = ctx.cat("paper.pdf")
hits  = ctx.grep("revenue", kind="document")

# Display
ctx.show()    # Rich table
ctx.info()    # Rich summary panel
```

## Processing Modes

| Mode | What | Speed | How |
|------|------|-------|-----|
| **fast** (default) | Local extraction — text from PDF, image hash/EXIF, video metadata | <100ms/file | pypdfium2 (PDF), Rust mmap (images), mp4parse/matroska (video) |
| **accurate** | LLM-powered semantic understanding (captions, descriptions, summaries) | Varies | LLM API via active profile + pipeline config |

Metadata scanning (`find`, `wc`) always uses Rust-native extraction (~60ms / 700 files).

## Performance

Benchmarked on Apple Silicon (M-series), 702 files (7.2GB):

| Operation | Latency |
|-----------|---------|
| Metadata scan (702 files) | 8ms |
| CLI cold start (`find --format json`) | 60ms |
| CLI cold start (`find --schema --format json`) | 109ms |
| CLI cold start (`sql`) | 300ms |
| Fast code extraction | ~52ms |
| Fast image extraction | ~61ms |
| Fast PDF text extraction | ~220ms |
| Fast video metadata | <100ms |
| PDF page mosaic (per page) | ~10ms |
| Video keyframe mosaic (48 frames) | ~1s |

## Storage

mm uses a global SQLite database at `~/.local/share/mm/mm.db` with sqlite-vec for vector search:

| Table | Contents | Relationship |
|-------|----------|-------------|
| `files` | File metadata + content (one row per file, `uri` = absolute path) | — |
| `l2_results` | LLM-generated summaries (many per file, `file_uri` = FK) | FK → `files.uri` |
| `chunks` | ~1024-char content chunks (`file_uri` = FK) | FK → `l2_results.id` |
| `chunks_vec` | Embedding vectors (sqlite-vec virtual table) | FK → `chunks.id` |
| `cache` | Key-value result cache | — |

The `files` table includes metadata columns (path, size, kind, etc.) and content columns (content_hash, text_preview, line_count, duration_s, exif_*, video_codec, etc.).

Use `mm config reset-db` to clear all databases and caches.


### Pipelines — encode + generate

Pipelines are YAML configs under `pipelines/{kind}/{mode}.yaml` that pair an **encoder** with optional LLM **generation** parameters. When `generate` is `null`, the pipeline is encode-only (no LLM call). Encoders are Python classes under `encoders/` that convert media files into VLM-ready Messages. See [`docs/PIPELINES.md`](docs/PIPELINES.md) and [`docs/ENCODERS.md`](docs/ENCODERS.md) for the full pipeline and encoder reference.

Pipeline fields can be overridden from the CLI:

```bash
mm cat photo.jpg -m accurate --encode.strategy tile --generate.max-tokens 1024
mm cat photo.jpg -m accurate --generate.temperature 0.5
```

Load explicit pipeline YAML(s) with `-p` (repeatable, dispatched by `kind` field):

```bash
mm cat photo.jpg -p my-image-pipeline.yaml
mm cat *.jpg *.mp4 -p image-pipeline.yaml -p video-pipeline.yaml
mm cat photo.jpg -p ~/custom.yaml --generate.max-tokens 512
```

Custom pipeline paths can also be set in `~/.config/mm/mm.toml`:

```toml
[pipelines]
image.fast = "/path/to/my-image-fast.yaml"
video.accurate = "/path/to/my-video-accurate.yaml"
```

## LLM Configuration using Profiles

For accurate mode, mm uses the `openai` Python SDK to call any OpenAI-compatible API. Provider settings are managed through **profiles** — named configurations stored in `~/.config/mm/mm.toml`.

### Quick setup

```bash
mm config init                # create config with default profile (local Ollama)
mm config show                # show resolved config with sources
```

### Managing profiles

Each profile stores `base_url`, `api_key`, and `model`. You can have as many as you need — one per provider, one per use-case, etc.

```bash
# Add custom profiles
mm profile add openai --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o
mm profile add openrouter --base-url https://openrouter.ai/api/v1 --model qwen/qwen3.5-27b

# Update reserved profiles (ollama, gemini, vlmrun)
mm profile update ollama --base-url http://localhost:11434 --model qwen3.5:9B

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
mm --profile openai cat photo.png -m accurate

# Environment variable
MM_PROFILE=openai mm cat photo.png -m accurate
```

### Resolution order

Provider settings (base_url, api_key, model) come from the active profile, falling back to built-in defaults.

The active profile is resolved as:

```
--profile flag  >  MM_PROFILE env  >  active_profile in config file  >  "ollama"
```

### Config file format

```toml
# ~/.config/mm/mm.toml
active_profile = "ollama"

[profile.ollama]
base_url = "http://localhost:11434"
api_key = ""
model = "qwen3.5:0.8"

[profile.gemini]
base_url = "https://openrouter.ai/api/v1"
api_key = ""
model = "google/gemini-2.5-flash-lite"

[profile.vlmrun]
base_url = "https://mm-ctx.ngrok.io/v1"
api_key = ""
model = "Qwen/Qwen3.5-0.8B"
```

## License

MIT

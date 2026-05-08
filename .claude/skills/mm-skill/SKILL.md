---
name: mm-skill
description: >
  Use the mm CLI and Python API to index, explore, query, and extract content from multimodal
  directories containing images, videos, PDFs, code, and other files. Triggers: exploring a
  directory's contents, listing/finding files by type or size, extracting text from PDFs, getting
  image metadata, searching across file contents, counting tokens, viewing directory trees,
  extracting PDF page mosaics, video keyframe extraction, building VLM prompts, encoding media,
  audio transcription, 'what files are in this folder', 'find all images', 'show me the PDFs',
  'how much storage do videos use', 'extract text from this PDF', 'search documents for X',
  'analyze this directory', 'how many tokens', 'show the tree', 'build a VLM prompt',
  'transcribe audio', 'encode this image'.
---

# mm

Fast, multimodal context for agents. Rust core, Python developer experience, Unix-style composability.

Two interfaces:

- **CLI** — `find`, `cat`, `grep`, `wc`, `peek`, `sql`, `bench`, `config`, `profile`.
- **Python API** — `mm.Context` for VLM prompt building. See [api.md](api.md).

For programmatic parsing, always use `--format json`.

## Installation

```bash
pip install mm-ctx                                                       # pip
uv pip install mm-ctx                                                    # uv
uvx --from mm-ctx mm --help                                              # no-install run
curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh          # macOS/Linux installer
irm https://vlm-run.github.io/mm/install/install.ps1 | iex               # Windows (PowerShell)
```

### Optional extras and audio transcription

| Install | Best for | Audio transcription path |
|---------|----------|--------------------------|
| `mm-ctx[mlx]` | Apple Silicon / macOS with MLX | `lightning-whisper-mlx` first, then `ctranslate2/faster-whisper`, then OpenAI `/audio/transcriptions` |
| `mm-ctx` on a CUDA GPU runtime | Linux/Windows GPU hosts | `ctranslate2/faster-whisper` first, then OpenAI `/audio/transcriptions` |
| `mm-ctx` default / CPU | Portable local installs | `ctranslate2/faster-whisper` on CPU, then OpenAI `/audio/transcriptions` |

For audio transcription, `mm` prefers the fastest local backend available in this order:
MLX on Apple Silicon, ctranslate2/faster-whisper, then OpenAI transcription endpoint.

## Top-level flags

```
mm [--profile NAME | -p] [--color auto|always|never] [--version | -v] <command> ...
```

| Flag | Purpose |
|------|---------|
| `--profile NAME` / `-p` | Override active profile for this invocation (`MM_PROFILE` env also works). |
| `--color MODE` | `auto` (default), `always`, `never`. |
| `--version` / `-v` | Print version and exit. |

## Commands

| Command | Purpose |
|---------|---------|
| `find` | Locate/list files by name/kind/ext/size; tabular, tree, or schema view. |
| `peek` | Local file metadata (dimensions / EXIF / codec / duration / mime / hash). |
| `cat` | Content extraction (auto-detected by kind × mode); pipeline-driven. |
| `grep` | Content search — text (regex) and semantic (vector). |
| `sql` | SQL on `files`, `extractions`, `chunks` tables. |
| `wc` | Count files, bytes, lines (est.), tokens (est.). |
| `bench` | Benchmark suite with statistical analysis. |
| `config` | Configuration: `show`, `init`, `set`, `reset-db`, `reset-profiles`, `reset`. |
| `profile` | LLM provider profiles: `list`, `add`, `update`, `use`, `remove`. |

## Quick workflow

```bash
mm find <dir> --tree --depth 1   # directory shape
mm wc   <dir> --by-kind          # token/byte budget by kind
mm find <dir> --kind image       # filter
mm cat  <file>                   # fast extraction (default)
mm cat  <file> -m accurate       # LLM-powered (requires profile)
mm grep "pattern" <dir>          # regex; add -s for semantic
```

## find — locate files, tree, schema

```
mm find [DIR] [-n NAME] [-i] [-k KIND] [-e EXT] [--min-size S] [--max-size S]
              [-d DEPTH] [-s COL] [-r] [-c COLS] [--tree | --schema]
              [--limit N] [--no-ignore] [--session ID] [--refs] [-f FORMAT]
```

| Flag | Purpose |
|------|---------|
| `--name NAME` / `-n` | Filter by file name (substring or regex). |
| `--ignore-case` / `-i` | Case-insensitive name matching. |
| `--kind` / `-k` | Filter by kind (`image`, `video`, `document`, `code`, `audio`, `data`, `config`, `text`, `other`); comma-separated. |
| `--ext` / `-e` | Filter by extension(s), comma-separated. |
| `--min-size` / `--max-size` | Size bounds (e.g. `1kb`, `10mb`). |
| `--depth` / `-d` | Max directory depth. |
| `--sort` / `-s` | Sort by column. |
| `--reverse` / `-r` | Reverse sort. |
| `--columns` / `-c` | Comma-separated column subset. |
| `--tree` | Hierarchical view with sizes. |
| `--size` | Show sizes in tree (default on). |
| `--schema` | Show column names, Arrow types, descriptions, sample values. |
| `--limit N` | Cap result count. |
| `--no-ignore` | Don't respect `.gitignore`. |
| `--session` / `--refs` | Tag rows with `<session>/<ref_id>` (opt-in). |
| `--format` / `-f` | `rich`, `json`, `pretty-json`, `tsv`, `csv`, `dataset-jsonl`, `dataset-hf`. |

```bash
mm find ~/data --kind image,document             # filter (combined)
mm find ~/data --ext .pdf --min-size 10mb -s size -r --limit 10
mm find ~/data --tree --depth 2                  # tree
mm find ~/data --schema --format json            # schema → JSON
mm find ~/data --no-ignore                       # include gitignored
```

`files` columns: `path`, `name`, `stem`, `ext`, `size`, `modified`, `created`, `mime`, `kind`, `is_binary`, `depth`, `parent`, `width`, `height`.

## peek — raw file metadata

```
mm peek FILE [FILE...] [--full] [-f FORMAT]
```

| Flag | Purpose |
|------|---------|
| `--full` | Include document fields: `doc_author`, `doc_title`, `doc_subject`, `doc_keywords`, `doc_creator`, `doc_producer`, `pages`. |
| `--format` / `-f` | `rich`, `json`, `pretty-json`, `tsv`, `csv`, `stdout`. |

Single Rust scan, sub-100ms. Behaviour by kind:

- **Image** (`.png/.jpg/.webp/.gif/.bmp/.tiff/.svg`) — dimensions, MIME, xxh3 hash, EXIF, pHash.
- **Video** (`.mp4/.mkv/.webm/.avi/.mov`) — resolution, duration, FPS, codecs (no ffmpeg).
- **Audio** (`.mp3/.wav/.flac/.aac/.ogg/.m4a`) — duration, codec, bitrate.
- **PDF / DOCX / PPTX** — mime + content hash; `--full` adds document properties.
- **Text / code** — mime + content hash.

```bash
mm peek photo.png                            # rich panel
mm peek a.png b.mp4 c.pdf --format json      # multi-file JSON
mm peek paper.pdf --full                     # author/title/subject/keywords/pages
```

## cat — content extraction (pipeline-driven)

```
mm cat FILE... [-m fast|accurate] [-p PIPELINE]... [-n N] [-o DIR]
               [--no-cache] [--no-generate] [-v] [-y]
               [--encode.strategy NAME] [--encode.pyfunc PATH|CODE]
               [--encode.strategy_opts KEY=VALUE]...
               [--prompt TEXT | --generate.prompt TEXT]
               [--model NAME  | --generate.model NAME]
               [--generate.max-tokens N] [--generate.temperature F]
               [--generate.json-mode BOOL] [--generate.extra-body JSON]
               [--list-pipelines | --list-encoders | --print-pipeline KIND/MODE]
               [-f FORMAT]
```

`--mode` is `fast` (default) or `accurate`. Mode is a no-op for `kind=text` and non-PDF documents (`.docx`/`.pptx`) — they always passthrough.

| Kind | fast (default) | accurate |
|------|----------------|----------|
| Image | short VLM caption | full VLM caption + tags |
| Video | mosaic → short VLM | frames + transcript → VLM |
| Audio | Whisper transcript (no LLM) | transcript → LLM summary |
| PDF | page-text via pypdfium2 (no LLM) | page-text → LLM markdown |
| `.docx` / `.pptx` | passthrough text | passthrough text |
| code / text | passthrough text | passthrough text |

| Flag | Purpose |
|------|---------|
| `--mode` / `-m` | `fast` or `accurate`. |
| `--pipeline` / `-p` | Encoder name OR pipeline YAML path. Repeatable (dispatched by `kind`). |
| `-n N` | Head/tail: `+N` = first N lines, `-N` = last N lines. |
| `--output-dir` / `-o` | Write generated artifacts to dir. |
| `--no-cache` | Bypass L2 cache; force fresh run. |
| `--no-generate` | Skip the generate (LLM) step; emit encoder text parts only. |
| `--verbose` / `-v` | Show pipeline tree (encode/generate timings). |
| `--yes` / `-y` | Skip the batch-size confirmation (≥9 paths; env `MM_CAT_BATCH_CONFIRM_THRESHOLD`). |
| `--encode.strategy` | Override encoder name. |
| `--encode.pyfunc` | Custom Python transform (`.py` path or inline `def`). |
| `--encode.strategy_opts KEY=VALUE` | Override encode opts (repeatable; values coerced to int/float/bool). |
| `--prompt` (= `--generate.prompt`) | Override LLM prompt template. |
| `--model` (= `--generate.model`) | Override model for this call. |
| `--generate.max-tokens` | Max completion tokens. |
| `--generate.temperature` | Sampling temperature. |
| `--generate.json-mode` | Request JSON response (`true`/`false`). |
| `--generate.extra-body` | JSON object deep-merged into OpenAI `extra_body` (CLI keys win). |
| `--list-pipelines` | List built-in pipelines and exit. |
| `--list-encoders` | List registered encoders and exit. |
| `--print-pipeline KIND/MODE` | Print built-in pipeline YAML (e.g. `image/accurate`). |
| `--format` / `-f` | `rich`, `json`, `pretty-json`, `tsv`, `csv`, `dataset-jsonl`, `dataset-hf`. |

```bash
# Default fast mode
mm cat photo.png                                  # short VLM caption
mm cat video.mp4                                  # mosaic → short VLM
mm cat audio.mp3                                  # Whisper transcript only
mm cat paper.pdf                                  # page-text (pypdfium2)
mm cat src/main.py                                # passthrough text
mm cat notes.docx                                 # libreoffice-rs passthrough

# Accurate mode (LLM-powered; requires profile)
mm cat photo.png   -m accurate                    # caption + tags + objects
mm cat video.mp4   -m accurate                    # mosaic → VLM
mm cat audio.mp3   -m accurate                    # transcript → LLM summary
mm cat paper.pdf   -m accurate                    # text → LLM markdown

# Head / tail
mm cat <file> -n 20                               # first 20 lines
mm cat <file> -n -10                              # last 10 lines

# Pipelines
mm cat photo.png   -p image-tile
mm cat *.jpg *.mp4 -p image.yaml -p video.yaml    # multi-kind
mm cat --list-pipelines
mm cat --list-encoders
mm cat --print-pipeline image/accurate

# Overrides
mm cat photo.png -m accurate --encode.strategy_opts max_width=768
mm cat photo.png -m accurate --prompt "List 3 objects." --generate.max-tokens 64
mm cat photo.png -m accurate --no-cache --no-generate    # encoder snapshot
```

### Override surfaces (right-most wins)

```
profile (mm.toml)  →  pipeline YAML (generate.*)  →  CLI flags
  base_url             prompt                          --prompt / --generate.prompt
  api_key              model                           --model  / --generate.model
  model (default)      max_tokens                      --generate.max-tokens
                       temperature                     --generate.temperature
                       json_mode                       --generate.json-mode
                       extra_body (deep-merged)        --generate.extra-body
```

`base_url` and `api_key` are profile-only. The merged `model` + `extra_body` participate in the L2 cache key.

### Built-in encoders

| Name | Kind | Notes |
|------|------|-------|
| `image-resize` | image | **Default.** Fit to bbox (default 1024 px). |
| `image-tile` | image | Resized overview + tile crops in one Message. |
| `video-frames` | video | Frames at `fps` (ffmpeg). |
| `video-frames-w-transcript` | video | Frames + Whisper transcript (accurate-mode default). |
| `video-keyframes` | video | I-frames from bitstream. |
| `video-keyframes-w-transcript` | video | + transcript. |
| `video-mosaic` | video | Mosaic grids from sampled frames (fast-mode default). |
| `video-mosaic-w-transcript` | video | + transcript. |
| `video-shots` | video | PySceneDetect → frames per shot. |
| `video-shots-w-transcript` | video | + transcript. |
| `video-shot-mosaic` | video | PySceneDetect → mosaic per shot. |
| `video-shot-mosaic-w-transcript` | video | + transcript. |
| `video-chunks` | video | Overlapping time-based chunks. |
| `video-clips` | video | Base64 video clips of uniform duration. |
| `video-clips-w-transcript` | video | + transcript. |
| `video-summary` | video | Adaptive N-frame summary. |
| `video-summary-w-transcript` | video | + transcript. |
| `video-captions` | video | Embedded subtitle stream (falls back to Whisper). |
| `video-transcript` | video | Whisper transcript only. |
| `video-gemini` / `video-gemini-chunked` | video | Gemini `inline_data` Part(s). |
| `audio-base64` | audio | **Default (Python API).** Raw `input_audio` part. |
| `audio-transcribe` | audio | Whisper transcript (`backend`/`base_url`/`api_key` kwargs). |
| `audio-gemini` | audio | Gemini Part. |
| `document-page-text` | document | Per-page text (PDF/DOCX/PPTX). |
| `document-rasterize` | document | Render PDF pages as images. |
| `document-rasterize-text` | document | Rasterize + extract text, interleaved. |
| `document-gemini` | document | Gemini Part. |

### Custom pipeline YAML

```yaml
# custom-image.yaml
kind: image
mode: accurate
encode:
  strategy: image-tile
  strategy_opts:
    max_width: 2048
generate:
  prompt: "Describe this image."
  max_tokens: 512
---
kind: video
mode: accurate
encode:
  strategy: video-mosaic
  strategy_opts:
    tile_cols: 8
    tile_rows: 6
generate:
  prompt: "Summarize this video."
  max_tokens: 1024
```

```bash
mm cat *.jpg *.mp4 -p custom-image.yaml
```

Omit `generate:` for encode-only pipelines (no LLM call). CLI overrides (`--encode.*`, `--generate.*`, `--prompt`, `--model`) layer on top of `-p`.

Override built-in pipeline paths in `~/.config/mm/mm.toml`:

```toml
[pipelines]
image.fast = "~/.config/mm/pipelines/image/fast.yaml"
video.accurate = "/path/to/my-video-accurate.yaml"
```

### Custom Python transforms (pyfunc)

`--encode.pyfunc` runs a Python transform on encoded parts before the LLM call.

```bash
# my_transform.py exposes: def transform(parts, context): ...
mm cat photo.png -m accurate --encode.pyfunc ~/my_transform.py
```

Inline `def` in YAML:

```yaml
encode:
  pyfunc: |
    def transform(parts, context):
        return [p for p in parts if p.get("type") == "image_url"]
```

## grep — content search

```
mm grep PATTERN [DIR] [-k KIND] [-e EXT] [-C N] [-c] [-i] [-s] [--pre-index]
                      [--no-ignore] [-f FORMAT]
```

| Flag | Purpose |
|------|---------|
| `--kind` / `-k` | Filter by kind (comma-separated). |
| `--ext` / `-e` | Filter by extension(s). |
| `-C N` | Context lines around match. |
| `--count` / `-c` | Match counts per file only. |
| `--ignore-case` / `-i` | Case-insensitive matching. |
| `--semantic` / `-s` | Vector similarity search (binary kinds via embeddings). |
| `--pre-index` | Auto-index unindexed files before semantic search (max 50). |
| `--no-ignore` | Search gitignored files. |
| `--format` / `-f` | `rich`, `json`, `pretty-json`, `tsv`, `csv`, `dataset-jsonl`, `dataset-hf`. |

```bash
mm grep "TODO" ~/src --kind code -C 2
mm grep "invoice" ~/docs --kind document --count
mm grep "Quantum Phase" ~/data -s --pre-index    # semantic
```

**Warning**: regex grep extracts content from each matching file. On large doc directories prefer `--kind code` / `--kind text` for speed.

## sql — query metadata, extractions, chunks

```
mm sql [QUERY] [-d DIR] [--list-tables] [--pre-index] [-f FORMAT]
```

Auto-routes by `FROM` table:

- `files` — scan + in-memory SQLite (use `--dir`, `--pre-index` to populate persistent rows first).
- `extractions` — persistent SQLite (LLM outputs).
- `chunks` — persistent SQLite (chunked content + embeddings; `mode` ∈ `metadata`/`fast`/`accurate`).

```bash
mm sql "SELECT kind, COUNT(*) FROM files GROUP BY kind" --dir ~/data
mm sql "SELECT file_uri, summary FROM extractions LIMIT 10"
mm sql "SELECT file_uri, chunk_idx FROM chunks WHERE mode='accurate'"
mm sql --list-tables
```

## wc — count files, bytes, lines, tokens

```
mm wc [DIR] [-k KIND] [--by-kind] [-f FORMAT]
```

```bash
mm wc ~/project                     # summary panel
mm wc ~/project --by-kind           # per-kind breakdown
mm wc ~/project --kind code         # filter
```

Token estimates: ~chars/4 for text, tile-based for images/video.

## bench — benchmark suite

```
mm bench [DIR] [-r N] [-w N] [-m MODE] [-c TERM] [-g GROUP] [--model M] [--task T]
               [-b PATH] [--dry-run] [--host-info] [--with-generate] [--timeout S]
               [-f FORMAT]
```

| Flag | Purpose |
|------|---------|
| `--rounds` / `-r` | Measurement rounds (default 3). |
| `--warmup` / `-w` | Warmup rounds (default 1). |
| `--mode` / `-m` | `metadata` (default), `fast`, `accurate`, `all`. |
| `--command` / `-c` | Substring filter on bench-command names. |
| `--group` / `-g` | Filter by `BenchCommand.group` (case-insensitive exact). |
| `--model` | Filter by `tags['model']`. |
| `--task` | Filter by `tags['task']`: `cap`, `ocr`, `det`, `seg`, `llm`, `pose`, `track`, `noop`. |
| `--bench-file` / `-b` | Python file exposing `COMMANDS: list[BenchCommand]` or `def commands(files)`. Replaces built-in matrix; `--mode` is ignored. |
| `--dry-run` | Resolve plan without timing (`-` placeholders / `dry_run: true`). |
| `--host-info` | Print host spec and exit. |
| `--with-generate` | Stdout snapshot mode: include LLM step (default omits it). |
| `--timeout` | Per-command timeout in seconds (stdout snapshot mode). |
| `--format` / `-f` | `rich`, `json`, `pretty-json`, `tsv`, `csv`, `stdout`. |

`--format stdout` snapshots each variant's stdout between `---` separators (handy for `tests/stdout/cat.md`).

```bash
mm bench ~/data                                          # default suite
mm bench ~/data --mode all --rounds 5
mm bench ~/data --command cat --format stdout > tests/stdout/cat.md
mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --task ocr
mm bench ~/data -b ... --dry-run                         # inspect plan
mm bench --host-info                                     # host spec
```

## config — extraction settings & DB reset

```bash
mm config show                                       # resolved config + sources
mm config show --format json
mm config init                                       # create default ~/.config/mm/mm.toml
mm config init --force                               # overwrite existing
mm config set mode.fast.whisper_model tiny
mm config set mode.accurate.beam_size 5
mm config set transcription.backend openai
mm config set transcription.base_url http://localhost:11434/v1
mm config set transcription.api_key sk-...
mm config reset-db        [-y]                       # delete all DBs & caches
mm config reset-profiles  [-y]                       # restore default profiles
mm config reset           [-y]                       # both (irreversible)
```

## profile — LLM provider profiles

Stored in `~/.config/mm/mm.toml`. Reserved profiles: `ollama`, `gemini`, `vlmrun`.

```bash
mm profile list [-f FORMAT]                          # ● = active
mm profile add NAME    --base-url URL --model NAME [--api-key KEY]
mm profile update NAME [--base-url URL] [--api-key KEY] [--model NAME]
mm profile use NAME                                  # switch active
mm profile remove NAME                               # cannot remove active
```

Per-command selection:

```bash
mm --profile openrouter cat photo.png -m accurate    # one-off
MM_PROFILE=openrouter mm cat photo.png -m accurate   # env
```

Resolution: `--profile` flag > `MM_PROFILE` env > `active_profile` in config > `"ollama"`.

## Output formats

| Format | Notes |
|--------|-------|
| `rich` | Default in TTY: tables/panels. |
| `tsv` / `csv` | Plain delimited; default in pipes (`tsv`). |
| `json` | Compact in pipes, indented in TTY. |
| `pretty-json` | Always indented (good for piping into markdown / docs). |
| `dataset-jsonl` | JSONL for fine-tuning datasets. |
| `dataset-hf` | HuggingFace Datasets format (requires `--output-dir`). |
| `stdout` | Plain stdout (cat / config show / bench snapshot). |

## Pipe composability

```bash
mm find <dir> --kind image | mm cat                          # extract metadata
mm find <dir> --kind document --min-size 10mb | wc -l        # count
mm find <dir> --kind video --format json | jq '.[].name'     # JSON
mm find <dir> --kind image | mm cat -m accurate --format dataset-jsonl
```

## Tips

- `find`/`wc` JSON path runs in ~60ms (Rust serde). Use it for budgeting before paying for `cat`.
- Start with `find --tree --depth 1` then `wc --by-kind` for fastest overview.
- `find` returns paths only when piped; full metadata rows in TTY.
- `--mode` is a no-op for `kind=text` and non-PDF documents — they always passthrough.
- `--no-cache` forces fresh LLM call; no-op for passthrough kinds.
- `--no-generate` snapshots encoder output without calling the LLM.
- For PDFs, `cat` returns empty in fast mode if scanned; use `-m accurate` or `-p document-rasterize`.
- Chunks are written on first `cat`. Embedding + vec storage happens on `mm grep -s --pre-index`.
- `mm sql --list-tables` shows row counts across `files`, `extractions`, `chunks`.

## Python API (incremental Context)

```python
import mm
from pathlib import Path
ctx = mm.Context()                                   # auto-mints UUIDv7 session
ctx.add("Describe this image.", role="user")
img: mm.Ref = ctx.add(Path("photo.jpg"), role="user")
messages = ctx.to_messages(format="openai")          # or format="gemini"
ctx.get(img)                                         # round-trip the original obj
```

Full reference: [api.md](api.md).

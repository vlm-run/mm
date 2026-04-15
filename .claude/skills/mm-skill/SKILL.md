---
name: mm-skill
description: >
  Use the mm CLI to index, explore, query, and extract content from multimodal directories
  containing images, videos, PDFs, code, and other files. Triggers: exploring a directory's contents,
  listing/finding files by type or size, extracting text from PDFs, getting image metadata,
  searching across file contents, counting tokens, viewing directory trees,
  extracting PDF page mosaics, video keyframe extraction, 'what files are in this folder',
  'find all images', 'show me the PDFs', 'how much storage do videos use', 'extract text from this PDF',
  'search documents for X', 'analyze this directory', 'how many tokens', 'show the tree'.
---

# mm CLI

`mm` is a high-performance multimodal context management CLI. It indexes directories instantly (~60ms for 700 files), then exposes Unix-style commands for exploring, querying, and extracting content from images, videos, PDFs, code, and other files.

Always use `--format json` for machine-readable output when parsing results programmatically.

## Installation

```bash
# First run `mm --help` or `mm --version` to confirm mm isn't already installed

# macOS / Linux
curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh

# Windows (PowerShell)
irm https://vlm-run.github.io/mm/install/install.ps1 | iex
```

## Commands

| Command   | Purpose                                                                     |
| --------- | --------------------------------------------------------------------------- |
| `find`    | Locate/list files by name/kind/ext/size, tabular listing, tree view, schema |
| `cat`     | Content extraction (auto-detected by file type × mode)                      |
| `grep`    | Content search — text and semantic (via embeddings)                         |
| `wc`      | Count files, bytes, lines, tokens                                           |
| `bench`   | Benchmark suite with statistical analysis                                   |
| `config`  | Extraction mode settings (show, init, set, reset-db, reset-profiles, reset) |
| `profile` | Manage LLM provider profiles (list, add, update, use, remove)               |

## Workflow

1. Start with `mm find <dir> --tree --depth 1` to see the directory structure.
2. Use `mm wc <dir> --by-kind` to estimate token counts for LLM context budgeting.
3. Explore with `find`, `grep`, `cat` as needed.
5. Use `mm cat <file> -m accurate` for LLM-powered descriptions.

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

# Include gitignored files
mm find <dir> --no-ignore                             # bypass .gitignore rules
mm find <dir> --no-ignore --kind video                # gitignored videos
mm find <dir> --no-ignore --tree                      # tree including ignored dirs
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
| width     | uint32    | Pixel width (images from header, videos via native parsing). Null for non-media. |
| height    | uint32    | Pixel height (images from header, videos via native parsing). Null for non-media.|

## cat — content extraction (pipeline-driven)

Behaviour is auto-detected from file type. Default `--mode fast` runs local extraction (no LLM). Use `-m accurate` for LLM-powered descriptions.

```bash
# Fast mode (default) — local extraction, no LLM
mm cat <file>                                       # text/metadata extraction
mm cat photo.png                                    # image metadata (dims, MIME, hash, EXIF)
mm cat video.mp4                                    # video metadata (resolution, duration, codecs)
mm cat paper.pdf                                    # text extraction via pypdfium2

# Accurate mode — LLM-powered descriptions
mm cat photo.png -m accurate                        # VLM caption
mm cat video.mp4 -m accurate                        # mosaic → VLM description
mm cat audio.mp3 -m accurate                        # transcript → LLM summary
mm cat paper.pdf -m accurate                        # text → LLM summary

# Head / tail
mm cat <file> -n 20                                 # first 20 lines
mm cat <file> -n -10                                # last 10 lines

# Cache control
mm cat <file> --no-cache                            # bypass cache, force fresh run

# Output formats
mm cat <file> --format json                          # JSON output
```

Fast mode behavior by file type (<100ms target):

- **PDF** (.pdf): text extraction via pypdfium2. Scanned/image-only PDFs return empty.
- **Document** (.docx, .pptx): text extraction.
- **Image** (.png/.jpg/.webp/.gif/.bmp/.tiff/.svg): dimensions, MIME, xxh3 hash, EXIF data.
- **Video** (.mp4/.mkv/.webm/.avi/.mov): resolution, duration, FPS, codecs (metadata only, no ffmpeg).
- **Audio** (.mp3/.wav/.flac/.aac/.ogg/.m4a): duration, codec, bitrate (metadata only).

## cat -p — named encoders and pipeline YAMLs

The `-p` / `--pipeline` flag accepts either a registered encoder name or a YAML file path.

```bash
# Named encoder (encodes media into VLM-ready JSON messages)
mm cat photo.png -p image-resize              # Fit to 1024px, base64 encode
mm cat photo.png -p image-tile                # Resized overview + all tiles in one Message
mm cat video.mp4 -p video-frame-sample        # Extract frames at 1fps
mm cat video.mp4 -p video-chunk               # Chunk into 60s segments
mm cat doc.pdf  -p document-rasterize         # Render pages as images
mm cat doc.pdf  -p document-rasterize-text    # Rasterize + extract text

# YAML pipeline file
mm cat photo.png -p custom-pipeline.yaml

# Multiple pipelines (dispatched by kind field in YAML)
mm cat *.jpg *.mp4 -p image.yaml -p video.yaml

# List available encoders and pipelines
mm cat --list-pipelines
```

### Built-in encoders

Use either the bare name or the kind-prefixed display name.

| Name                      | Media    | Description                                          |
| ------------------------- | -------- | ---------------------------------------------------- |
| `image-resize`            | image    | **Default.** Fit to 1024px bounding box              |
| `image-tile`              | image    | Resized overview + tile crops in one Message         |
| `video-frame-sample`      | video    | Extract frames at _fps_ (requires ffmpeg)            |
| `video-frames-transcript` | video    | Frames + Whisper transcript (accurate mode default)  |
| `video-chunk`             | video    | Chunk into time-based segments with overlap          |
| `video-mosaic`            | video    | Build mosaic grids from sampled frames               |
| `video-shot-frames`       | video    | Scene detection → representative frames per shot     |
| `video-shot-mosaic`       | video    | Scene detection → mosaic grid per shot               |
| `video-gemini`            | video    | Pass video file as a Gemini Part                     |
| `video-gemini-chunked`    | video    | Chunk video into Gemini Parts                        |
| `audio-transcribe`        | audio    | Transcribe audio via Whisper (fast/accurate default) |
| `audio-gemini`            | audio    | Pass audio file as a Gemini Part                     |
| `document-page-text`      | document | Extract text per page from PDF/DOCX/PPTX             |
| `document-rasterize`      | document | Render PDF pages as images (requires pypdfium2)      |
| `document-rasterize-text` | document | Rasterize + extract text, interleaved                |
| `document-gemini`         | document | Pass document file as a Gemini Part                  |

### Writing custom encoders

Create a `.py` file in `python/mm/encoders/image/`, `python/mm/encoders/video/` (auto-discovered) or `~/.config/mm/encoders/`. The `name` is optional — it defaults to the function name with underscores replaced by hyphens:

```python
from pathlib import Path
from mm.encoders import register_encoder

@register_encoder(media_types=("image",))
def my_custom(path: Path, **kw):
    """Registered as 'my-custom' (auto-named from function)."""
    import base64, io
    from PIL import Image
    img = Image.open(path)
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    yield {"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    ]}
```

### Python API

```python
from mm import process_image, process_image_tiled, process_video, process_document
from pathlib import Path

msg = process_image(Path("photo.png"), max_width=1024)       # Single Message dict
tiles = list(process_image_tiled(Path("scan.png"), tile_size=1024))  # Multiple Messages
chunks = list(process_video(Path("video.mp4")))               # Multiple Messages
pages = list(process_document(Path("doc.pdf")))               # Multiple Messages

# Via Context
from mm import Context
ctx = Context("~/data")
messages = ctx.encode("photo.png", strategy="resize")
```

## cat — pipeline overrides

Pipelines are 2-stage YAMLs: **encode** (convert to LLM-ready parts) → **generate** (LLM call). Key parameters can be overridden from the CLI.

### Encode overrides (--encode.\*)

```bash
mm cat photo.png -m accurate --encode.strategy image-tile      # override encoder
mm cat photo.png -m accurate --encode.pyfunc ~/my_filter.py    # custom transform
```

### Generate overrides (--generate.\*)

```bash
mm cat photo.png -m accurate --generate.max-tokens 1024          # increase token limit
mm cat photo.png -m accurate --generate.temperature 0.5           # higher temperature
mm cat photo.png -m accurate --generate.prompt "List 3 main objects in this image."
mm cat photo.png -m accurate --generate.json-mode true            # request JSON response
```

### Combining overrides

```bash
mm cat photo.png -m accurate \
  --encode.strategy image-tile \
  --generate.max-tokens 512 \
  --generate.prompt "Analyze this architecture diagram."
```

## cat -p — explicit pipeline YAML

Load custom pipeline configurations from YAML files. The YAML's `kind` field dispatches the pipeline to the correct media type. The `generate` field is optional — omit it for encode-only pipelines.

### Single pipeline

```yaml
# custom-image.yaml
kind: image
mode: accurate
encode:
  strategy: resize
  max_width: 512
generate:
  prompt: "What is in this image? One sentence only."
  max_tokens: 64
```

```bash
mm cat photo.png -p custom-image.yaml
```

### Encode-only pipeline (no LLM)

```yaml
# encode-only.yaml
kind: document
mode: fast
encode:
  strategy: null
# generate omitted = encode-only, no LLM call
```

### Multi-document YAML

```yaml
kind: image
mode: accurate
encode:
  strategy: image-tile
  max_width: 2048
generate:
  prompt: "Describe this image in detail."
  max_tokens: 512
---
kind: video
mode: accurate
encode:
  mosaic_tile: "8x6"
  mosaic_count: 2
  frame_selection: scene
generate:
  prompt: "Summarize this video."
  max_tokens: 1024
```

```bash
mm cat *.jpg *.mp4 -p multi-pipeline.yaml
```

### CLI overrides layer on top of -p

```bash
mm cat photo.png -p my-pipeline.yaml --generate.max-tokens 128
```

### TOML pipeline path overrides

Override default pipeline paths in `~/.config/mm/mm.toml`:

```toml
[pipelines]
image.fast = "~/.config/mm/pipelines/image/fast.yaml"
video.accurate = "/path/to/my-video-accurate.yaml"
```

## cat — custom Python transforms (pyfunc)

The `--encode.pyfunc` flag runs a custom Python transform on the encoded content parts before they are sent to the LLM.

### File-based pyfunc

```bash
# my_transform.py:
# def transform(parts, context):
#     extra = {"type": "text", "text": "Focus on the data flow."}
#     return parts + [extra]

mm cat photo.png -m accurate --encode.pyfunc ~/my_transform.py
```

### Pyfunc in pipeline YAML

```yaml
kind: image
mode: accurate
encode:
  strategy: resize
  max_width: 512
  pyfunc: ~/my_transforms/filter.py
generate:
  prompt: "Analyze this image."
  max_tokens: 128
```

Inline `def` syntax in YAML:

```yaml
encode:
  pyfunc: |
    def transform(parts, context):
        return [p for p in parts if p.get("type") == "image_url"]
```

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
# Text search (regex matching)
mm grep "pattern" <dir>                                # search all files
mm grep "attention" <dir> --kind document              # search only documents
mm grep "TODO" <dir> --kind code                       # search code files
mm grep "invoice" <dir> --kind document --format json  # JSON output
mm grep "error" <dir> -C 2                             # 2 context lines
mm grep "invoice" <dir> --count                        # match counts per file
mm grep "Quantum Phase" <dir> -i                       # case-insensitive search
mm grep "TODO" <dir> --ignore-case --kind code         # case-insensitive in code
mm grep "secret" <dir> --no-ignore                     # search gitignored files too

# Semantic search (vector similarity via embeddings)
mm grep "financial projections" <dir> -s               # semantic search across all files
mm grep "architecture overview" <dir> -s --format json # JSON with distances
mm grep "revenue forecast" <dir> -s --index            # auto-index unindexed files before search
```

**Warning**: grep runs extraction on every matching file. On large document directories (500+ PDFs), this can take minutes. Prefer `--kind code` or `--kind text` for fast text searches.

## bench — benchmark suite

```bash
mm bench <dir>                          # full benchmark
mm bench <dir> --rounds 5               # more measurement rounds
mm bench <dir> --mode accurate          # include accurate-mode benchmarks
mm bench <dir> --format json            # JSON output for archival
```

## config — extraction mode settings

```bash
mm config show                                  # show current config
mm config init                                  # create config with default profile
mm config init --force                          # overwrite existing config
mm config set mode.fast.whisper_model tiny       # set a config value
mm config set mode.accurate.beam_size 5          # set a config value
mm config reset-db                              # delete all databases and caches
mm config reset-profiles                        # restore profiles to defaults
mm config reset                                 # reset everything (db + profiles)
```

## profile — LLM provider management

Provider settings are managed through **profiles** stored in `~/.config/mm/mm.toml`.

```bash
mm profile list                                            # list all profiles (● = active)
mm profile add openrouter --base-url https://openrouter.ai/api/v1 --model vlm-1
mm profile update openrouter --model gemma4:e2b
mm profile use openrouter                                  # switch active profile
mm profile remove openrouter
```

Per-command profile selection:

```bash
mm --profile openrouter cat photo.png -m accurate    # one-off override
MM_PROFILE=openrouter mm cat photo.png -m accurate   # env override
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

## Tips

- All metadata commands (`find`, `wc`) run in ~60ms via the Rust fast path.
- Start with `find --tree --depth 1` then `wc --by-kind` for the fastest directory overview.
- Use `--format json` when you need to parse output programmatically.
- `find` returns paths only when piped, else it returns full metadata rows.
- For PDFs, `cat` extracts text in fast mode; if empty, the PDF contains scanned images only.
- For videos, `mm cat video.mp4 -m accurate` auto-generates keyframe mosaics and sends to LLM.
- Use `--mode fast` for quick metadata/text extraction (default), `--mode accurate` for LLM descriptions.
- Use `--no-cache` with `-m accurate` to force a fresh LLM call.
- Use `-p` to load custom pipeline YAMLs or named encoders; CLI overrides layer on top.
- Use `--encode.pyfunc` to inject custom Python transforms.
- Use `--list-pipelines` to see all available encoders and built-in pipelines.

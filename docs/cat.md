# mm cat

Extract and describe file content — pipeline-driven, mode-aware, and LLM-capable.

`cat` is the primary extraction command. It auto-detects what to do from the file type and the selected mode. For raw file metadata (dimensions, EXIF, codec, hash), use [`peek`](peek.md) instead.

## Synopsis

```bash
mm cat FILE [FILE ...] [OPTIONS]
```

## Input

- **Multimodal**: auto-detects kind from extension → image, video, audio, document, text
- **Multi-file**: `mm cat a.jpg b.pdf c.mp4` — processes files in parallel (up to 8 threads); output order matches input order. With `--stream`, files are processed sequentially to avoid interleaved output.
- **Large batches**: if the path count is **≥ 9** (i.e. more than 8 files; override with `MM_CAT_BATCH_CONFIRM_THRESHOLD`), `cat` asks for confirmation in a TTY; in non-interactive use it **exits with an error** unless you pass **`--yes` / `-y`**
- **Stdin**: `find . -name '*.pdf' | mm cat` — reads newline-delimited paths from stdin
- **Head/tail**: `-n 20` (first 20 lines), `-n -20` (last 20 lines)

## Modes

`--mode fast` (default) — runs the kind's fast pipeline. Whether an LLM is involved depends on the pipeline's `generate` step (image/fast.yaml has one, document/fast.yaml does not).
`--mode accurate` — runs the kind's accurate pipeline; always LLM-heavy.

Both `fast` and `accurate` read from the **metadata tier** as their input —
the locally-extracted content cached in `files.text_preview`. That tier
never invokes an LLM and is reusable across both `fast` and `accurate`
extractions of the same file.

`kind=text` files ignore `--mode` entirely: they always return passthrough text and
write FK-orphan chunks + concurrent embeddings on first sight, no `extractions` row.
Office documents are passthrough in fast mode but go through the LLM pipeline in accurate mode (see below).

### Overview

|                           | `fast` (default)                          | `accurate`                              |
|---------------------------|-------------------------------------------|-----------------------------------------|
| **Images**                | Short VLM caption                         | Full VLM description + tags             |
| **Videos**                | Frame mosaic → short VLM description      | Mosaic + transcript → VLM description   |
| **Audio** (default: `transcribe`) | Whisper transcript         | Whisper transcript             |
| **Audio** (`-p native`)   | 10-word description  | Detailed LLM description |
| **Audio** (`-p gemini-native`)   | 10-word description               | Detailed LLM description        |
| **PDFs**                  | Page-text extraction (pypdfium2)          | Text → LLM markdown structuring         |
| **Office docs** (.docx/.pptx/.xlsx/.odt/.odp/.ods) | Passthrough text (no LLM) | Office → PDF conversion → LLM markdown  |
| **Code / text**           | Passthrough text (no LLM)                 | Passthrough text (no LLM)               |

`--mode` is a no-op for code and text — they always return passthrough text regardless of mode. Office documents (`.docx`, `.pptx`, `.xlsx`, `.odt`, `.odp`, `.ods`) are passthrough in fast mode but converted to PDF and processed through the LLM pipeline in accurate mode.

### Image

| | fast (default) | accurate |
|---|---|---|
| Encoder | `resize` (max 512px) | `resize` (max 1024px) |
| Output | 10-word description + 5 tags | ~200-word description + 10 tags + 10 objects |
| Tokens | 256 max | 2048 max |

### Video

Multi-file: `mm cat a.mp4 b.mp4 -y` runs each video sequentially; the same **≥ 9 paths** batch rule applies as for images.

| | fast (default) | accurate |
|---|---|---|
| Encoder | `mosaic` (4×4 grid, 128 frames, up to 8 mosaics) | `frames-w-transcript` (1fps, whisper medium, 2.0× speed) |
| Output | 50-word description + tags | ~200-word summary + tags + scene breakdown |
| Tokens | 512 max | 1536 max |
| Audio | none | whisper medium, 2.0× speed |

### Audio

| | fast (default) | accurate |
|---|---|---|
| Encoder | `transcribe` (whisper medium, 2.0×) | `transcribe` (whisper medium, 2.0×) |
| Output | Whisper transcript | Whisper transcript |
| LLM call | None — `transcribe` suppresses generate | None — `transcribe` suppresses generate |
| For LLM output | Use `-p native` (10-word description, 128 tok) | Use `-p native` or `-p gemini-native` (full description, 1024 tok) |

**Transcription backends** (auto-detected by priority, override via --encode.backend or `mm config set transcription.backend`):

| Backend | Priority | Device | Notes |
|---|---|---|---|
| `mlx` | 10 | Apple Metal GPU | Requires `mm[mlx]` extra |
| `ctranslate2` | 20 | CPU (int8) / CUDA (float16) | Requires `mm-ctx[gpu]` extra |
| `openai` | 30 | Remote API | Any OpenAI-compatible `/v1/audio/transcriptions` endpoint |

**Selecting a backend** — precedence from most to least specific:

1. **CLI flag** (one-off): `mm cat audio.mp3 --encode.backend openai`
2. **Pipeline YAML** (`encode.backend:` top-level)
3. **Global default** (`mm config set transcription.backend openai`), persisted in `[transcription]` of `~/.config/mm/mm.toml`
4. **Environment** (`MM_TRANSCRIPTION_BASE_URL`, openai backend only)
5. **Auto-detect** (mlx → ctranslate2 → openai)

**Python API** encoders for audio:

| Name | Description |
|---|---|
| `native` | (default in `to_messages`) Raw base64-encoded audio for native VLM input |
| `transcribe` | Whisper transcript as text, supports `backend`/`base_url`/`api_key` kwargs |
| `gemini-native` | Pass audio file as a base64-encoded `input_audio` part |

### Document (PDF only)

| | fast (default) | accurate |
|---|---|---|
| Encoder | `page-text` (pypdfium2, 1 page/message) | `page-text` (pypdfium2, 1 page/message) |
| Output | concatenated page text | lossless markdown restructuring |
| Tokens | — | 16384 max |

### Document (Office: DOCX / PPTX / XLSX / ODS / ODT / ODP)

| | fast (default) | accurate |
|---|---|---|
| Behavior | Passthrough text via libreoffice-rs | Office → PDF conversion → LLM markdown structuring |
| LLM call | None | Yes (routes through office→PDF before encode) |

In fast mode, raw text is extracted directly. In accurate mode, the file is converted to PDF via `office_to_pdf` and then processed through the document/accurate pipeline.

**Python API** encoders for documents:

| Name | Description |
|---|---|
| `page-text` | (default in fast/accurate pipelines) Per-page text extraction via pypdfium2 (PDF) or libreoffice-rs (office docs) |
| `rasterize` | Render PDF pages as JPEG images via pypdfium2 |
| `rasterize-text` | Rasterize + interleave extracted page text |
| `native` | Raw base64 `file` part (OpenAI-compatible) — for models with native document input |
| `document_url` | Raw base64 `document_url` part — native input shape for the vlm.run gateway |
| `gemini-native` | Raw base64 Gemini `inline_data` Part — for Gemini |

### Text / Code / Config

Passthrough in all modes — raw file content via `read_text`. No pipeline, no LLM; mode is a no-op.

## Options

### Core

| Flag | Short | Type | Description |
|------|-------|------|-------------|
| `--mode MODE` | `-m` | enum | Processing mode: `fast` (default) or `accurate` |
| `--pipeline NAME_OR_PATH` | `-p` | string | Named encoder or path to a pipeline YAML. Repeatable. |
| `--list-pipelines` | | flag | List all built-in pipelines and exit |
| `--list-encoders` | | flag | List all registered encoders and exit |
| `--print-pipeline PIPELINE` | | string | Print the YAML for a built-in pipeline (e.g. `image/accurate`) |
| `-n N` | | int | Line limit: `+N` = first N lines (head), `-N` = last N lines (tail) |
| `--output-dir DIR` | `-o` | path | Output directory for generated artifacts (datasets) |
| `--no-cache` | | flag | Bypass cache, force a fresh run |
| `--no-generate` | | flag | Skip the LLM step — emit only the encoder's text parts |
| `--dry-run` | | flag | Resolve and display the pipeline without executing it |
| `--format FORMAT` | `-f` | enum | Output format: `rich`, `json`, `pretty-json`, `tsv`, `csv`, `dataset-jsonl`, `dataset-hf` |
| `--stream` | | flag | Stream LLM output tokens to stdout as they arrive. Takes precedence over `--format`. |
| `--verbose` | `-v` | flag | Show progress bars and LLM call details |
| `--yes` | `-y` | flag | Skip the confirmation prompt when batching many files |

### Encode overrides

Override the pipeline's encoder behavior for this invocation.

| Flag | Description |
|------|-------------|
| `--encode.strategy NAME` | Override the encoder name |
| `--encode.pyfunc CODE_OR_PATH` | Inline Python transform or path to a `.py` file |
| `--encode.backend BACKEND` | Transcription backend for audio/video encoding: `openai`, `mlx`, `ctranslate2`. Ignored by encoders that have no backend concept. |
| `--encode.model MODEL` | Model used by the encoder, independent of the LLM generate model (e.g. `nvidia/parakeet-tdt-0.6b-v3`, `whisper-1`). Ignored by encoders that have no model concept. |
| `--encode.strategy_opts KEY=VALUE` | Override individual strategy options. Repeatable. Values are coerced to int/float/bool where possible. |

### Generate overrides

Override the pipeline's LLM generation behavior. Right-most layer wins over pipeline YAML defaults.

| Flag | Alias | Description |
|------|-------|-------------|
| `--prompt TEXT` | `--generate.prompt` | Override the LLM prompt template |
| `--model MODEL` | `--generate.model` | Override the model for this call |
| `--extra-body JSON` | `--generate.extra-body` | JSON object deep-merged onto the pipeline's `extra_body` |
| `--generate.max-tokens N` | | Override max completion tokens |
| `--generate.temperature T` | | Override sampling temperature |
| `--generate.json-mode BOOL` | | Override JSON mode (true/false) |

## Override hierarchy

Settings are applied in this order — right wins on conflict:

```
profile (mm.toml)  →  pipeline YAML (generate.*)  →  CLI flags
  base_url               prompt                         --prompt / --generate.prompt
  api_key                model                          --model  / --generate.model
  model (default)        max_tokens                     --generate.max-tokens
                         temperature                    --generate.temperature
                         json_mode                      --generate.json-mode
                         extra_body (deep-merged)       --extra-body / --generate.extra-body
```

## Pipeline customization

### Built-in pipelines

```
pipelines/
  image/    fast.yaml    accurate.yaml
  video/    fast.yaml    accurate.yaml
  audio/    fast.yaml    accurate.yaml
  document/ fast.yaml    accurate.yaml
```

### Override mechanisms (priority order)

1. `-p pipeline.yaml` — explicit YAML file
2. `-p encoder_name` — named encoder (e.g. `tile`, `mosaic`, `page-text`)
3. `~/.config/mm/pipelines/{kind}/{mode}.yaml` — user override directory
4. Built-in `pipelines/{kind}/{mode}.yaml`

### Pipeline YAML structure

```yaml
kind: image
mode: fast

encode:
  strategy: resize          # registered encoder name
  strategy_opts:
    max_width: 512          # encoder-specific options

generate:                   # optional — omit for encode-only
  prompt: "Describe..."     # supports {filename}, {content}, {transcript}
  max_tokens: 256
  temperature: 0.1          # optional
  json_mode: false          # optional
```

### CLI overrides

Namespaced flags override individual pipeline fields:

- `--encode.strategy resize` — swap encoder
- `--encode.strategy_opts max_width=768` — override a single `strategy_opts` entry
  (repeatable; values are coerced to int/float/bool when possible, e.g.
  `--encode.strategy_opts max_width=768 --encode.strategy_opts fps=5`)
- `--encode.pyfunc transform.py` — custom Python transform
- `--generate.prompt "..."` — override prompt
- `--generate.max-tokens 512` — override token limit
- `--generate.temperature 0.5` — override temperature
- `--print-pipeline image/accurate` — print the YAML source of a built-in pipeline
  (accepts `<kind>/<mode>`, useful as a starting point for a custom pipeline)

## Caching

The metadata tier is cached in `files.text_preview` keyed by `content_hash`
(populated by `extract_meta`; reused on every subsequent `cat` of the same
file, regardless of mode).

The unified `extractions` table (SQLite at `~/.local/share/mm/mm.db`) caches
**both** fast and accurate pipeline outputs (the metadata tier never writes
here — it lives in `files`).

- Cache key (`extractions`): `content_hash × profile × model × mode × overrides`
  - Same file with different modes/profiles/overrides → separate cache entries
- `--no-cache`: bypasses read, evicts existing entry, forces fresh run (applies to fast/accurate for image/video/audio/PDF; the metadata tier is always read from `files`, and `kind=text` + non-PDF documents ignore `--no-cache` since their content is deterministic)
- Cache hit indicator: footer shows `cached • 36ms • 412.8 KB • 7.0 MB/s`
- Embedding: on cache miss with accurate mode, `embed_file_chunks` auto-generates Gemini embeddings

## Verbose (`--verbose` / `-v`)

Pipeline execution tree shown after content:

```
pipeline
  ├─ encode: resize • 0.0s → 1 parts (1 image)
  └─ generate: ollama • 2.3s • 354→195 tokens
```

- Encode-only pipelines (document fast): single `└─` node
- Encode + generate: `├─` encode, `└─` generate
- Generate line: `profile_name • elapsed • prompt→completion tokens`

## Streaming (`--stream`)

When `--stream` is passed, LLM tokens are written to stdout incrementally as the backend generates them. Streaming takes precedence over `--format` — formatted output modes are bypassed.

- **Multi-file**: files are processed sequentially (no parallel threads) to avoid interleaved output. Without `--stream`, files are processed in parallel.
- **Verbose**: `--stream -v` still displays the pipeline tree and timing metadata after the streamed content.
- **Fallback**: if the backend doesn't support streaming (e.g. VLM gateway returns 0 chunks), `_chat_stream` transparently falls back to a non-streaming call.

## Output formats

- **TTY** (default): Rich-formatted with syntax highlighting for code files
- **Piped** (default): plain text, no ANSI codes
- `--format json`: `{"path", "mode", "content"}`
- `--format pretty-json`: always-indented JSON (good for piping into docs)
- `--format dataset-jsonl`: one JSON object per line with metadata
- `--format dataset-hf`: HuggingFace-compatible dataset export (requires `--output-dir`)
- Multi-file separator: `--- path (kind, sizeB) ---`

## Footer

Always shown (dimmed):

```
elapsed • size • throughput
```

Examples: `836ms • 38.2 KB • 45.7 KB/s`, `cached • 36ms • 412.8 KB • 7.0 MB/s`

- Throughput auto-scales: B/s → KB/s → MB/s → GB/s
- `cached` prefix when served from the extractions cache

## Dry run

`--dry-run` resolves and prints the pipeline that *would* run (encoder, strategy options, model, prompt) without executing it. No encoding, no LLM call, no cache writes.

For passthrough kinds (text, code, `.docx`, `.pptx`) it emits a short header with the file size and a note that content would be passed through.

```bash
mm cat photo.png --dry-run            # show resolved image pipeline
mm cat video.mp4 -m accurate --dry-run  # show accurate video pipeline
mm cat notes.docx --dry-run           # passthrough preview
```

## Examples

### Basic usage

```bash
# passthrough text (code file)
mm cat main.py

# passthrough text (DOCX)
mm cat notes.docx

# PDF page-text extraction (fast pipeline)
mm cat paper.pdf

# first 20 lines
mm cat paper.pdf -n 20

# last 20 lines
mm cat paper.pdf -n -20
```

### Image extraction

```bash
# short VLM caption (fast pipeline)
mm cat photo.png

# full VLM description (accurate pipeline)
mm cat photo.png -m accurate

# use a named encoder
mm cat photo.png -p tile

# override a strategy option
mm cat photo.png -m accurate --encode.strategy_opts max_width=768
```

### Video extraction

```bash
# frame mosaic → short VLM description
mm cat clip.mp4

# mosaic + transcript → VLM description (accurate)
mm cat clip.mp4 -m accurate
```

### Audio extraction

```bash
# Whisper transcript (fast)
mm cat recording.mp3

# Whisper transcript only (default)
mm cat recording.mp3 -m accurate

# MLX backend (Apple Silicon)
mm cat recording.mp3 -m accurate --encode.backend mlx

# CTranslate2 backend (CPU/GPU)
mm cat recording.mp3 -m accurate --encode.backend ctranslate2

# override the Whisper model
mm cat recording.mp3 -m accurate --encode.model large-v3
```

### Pipeline inspection

```bash
# list all built-in pipelines
mm cat --list-pipelines

# list all registered encoders
mm cat --list-encoders

# print the YAML source for a pipeline
mm cat --print-pipeline image/accurate
mm cat --print-pipeline video/fast
```

### Custom pipeline

```bash
# load a custom pipeline YAML
mm cat photo.png -m accurate -p my-pipeline.yaml

# override the prompt inline
mm cat photo.png -m accurate --prompt "List all objects visible in this image."
```

### Streaming

```bash
# stream LLM tokens to stdout as they arrive
mm cat photo.png -m accurate --stream

# stream + force fresh LLM call (no cache)
mm cat video.mp4 -m accurate --stream --no-cache

# streaming works with verbose (pipeline tree + timing still shown)
mm cat photo.png -m accurate --stream -v
```

### Output formats

```bash
# JSON (compact in pipes, pretty in TTY)
mm cat photo.png --format json

# always-indented JSON (good for piping into docs)
mm cat photo.png --format pretty-json

# HuggingFace Dataset export
mm cat --format dataset-hf *.png --output-dir ./my_dataset
```

### Batch processing

```bash
# multi-file (output is separated by ==== headers)
mm cat *.png -m accurate

# pipe from find
mm find ~/data --kind image | mm cat -m accurate

# skip confirmation for large batches
mm find ~/data --kind image | mm cat -m accurate --yes
```

### Encode-only (no LLM)

```bash
# emit only the encoder's text parts, skip the LLM call
mm cat photo.png --no-generate

# useful for offline testing / snapshotting encoder behavior
mm cat photo.png -p tile --no-generate
```

### Pipeline inspection (dry run)

```bash
# show the resolved pipeline without executing it
mm cat photo.png --dry-run

# inspect accurate mode pipeline
mm cat video.mp4 -m accurate --dry-run

# preview with overrides applied
mm cat audio.mp3 -m accurate --encode.backend mlx --dry-run
```

## Per-provider / per-model overrides with `--generate.extra-body`

The `--generate.extra-body` flag accepts a JSON object forwarded to the OpenAI SDK's `extra_body` parameter. This enables provider-specific capabilities:

```bash
# Florence-2 OCR on a scanned page (vlmrt deployment)
mm --profile vlmrt cat page.png -m accurate \
  --model florence-2-base-ft \
  --generate.extra-body '{"method":"ocr"}'

# Moondream2 object detection
mm --profile vlmrt cat photo.jpg -m accurate \
  --model moondream2 \
  --generate.extra-body '{"method":"detect","method_params":{"object":"fish"}}'

# PaddleOCR scene-text recognition (Chinese)
mm --profile vlmrt cat storefront.jpg -m accurate \
  --model paddleocr-v5 \
  --generate.extra-body '{"method":"ocr","method_params":{"lang":"ch","score_threshold":0.6}}'

# Qwen3.5 video summarization with frame sampling controls
mm --profile vlmrt cat clip.mp4 -m accurate \
  --model qwen3.5-0.8b \
  --prompt "Summarize this clip in two sentences." \
  --generate.extra-body '{"video_fps":1.0,"video_max_frames":8}'
```

## Notes

- Multi-file output uses `====` as a separator with `<filename>` headers in rich mode.
- `--stream` writes LLM tokens to stdout as they arrive; takes precedence over `--format`. Falls back to non-streaming when the backend doesn't support it.
- `--verbose` shows timing, prompt tokens, and completion tokens from the LLM call.
- Files that do not exist are skipped with a warning; missing files are also pruned from the cache index.
- Batch confirmation is triggered when the path count reaches a threshold (default 9). Override with `--yes` or the `MM_CAT_BATCH_CONFIRM_THRESHOLD` environment variable.
- `--no-generate` is useful for snapshotting encoder behavior offline and for testing pipeline encoders without an LLM server.
- For `dataset-jsonl` and `dataset-hf` output formats, each record includes `path`, `mode`, `content`, `name`, `type`, and `size` fields.
- `--list-pipelines`: show all built-in and user-override pipeline YAML files.
- `--list-encoders`: show all registered encoder strategies with parameters.

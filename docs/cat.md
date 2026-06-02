# mm cat

Extract and describe file content — pipeline-driven, mode-aware, and LLM-capable.

`cat` is the primary extraction command. It auto-detects what to do from the file type and the selected mode. For raw file metadata (dimensions, EXIF, codec, hash), use [`peek`](peek.md) instead.

## Synopsis

```bash
mm cat FILE [FILE ...] [OPTIONS]
```

## Behavior by file type

|                           | `fast` (default)                          | `accurate`                              |
|---------------------------|-------------------------------------------|-----------------------------------------|
| **Images**                | Short VLM caption                         | Full VLM description + tags             |
| **Videos**                | Frame mosaic → short VLM description      | Mosaic + transcript → VLM description   |
| **Audio** (default: `transcribe`) | Whisper transcript         | Whisper transcript             |
| **Audio** (`-p base64`)   | 10-word description  | Detailed LLM description |
| **Audio** (`-p gemini`)   | 10-word description               | Detailed LLM description        |
| **PDFs**                  | Page-text extraction (pypdfium2)          | Text → LLM markdown structuring         |
| **Non-PDF docs** (.docx/.pptx) | Passthrough text (no LLM)           | Passthrough text (no LLM)               |
| **Code / text**           | Passthrough text (no LLM)                 | Passthrough text (no LLM)               |

`--mode` is a no-op for non-PDF documents, code, and text — they always return passthrough text regardless of mode.

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
| `--encode.backend BACKEND` | Transcription backend: `openai`, `mlx`, `ctranslate2` |
| `--encode.model MODEL` | Encoder model (e.g. Whisper model for audio transcription) |
| `--encode.strategy_opts KEY=VALUE` | Override individual strategy options. Repeatable. Values are coerced to int/float/bool where possible. |

### Generate overrides

Override the pipeline's LLM generation behavior. Right-most layer wins over pipeline YAML defaults.

| Flag | Alias | Description |
|------|-------|-------------|
| `--prompt TEXT` | `--generate.prompt` | Override the LLM prompt template |
| `--model MODEL` | `--generate.model` | Override the model for this call |
| `--generate.max-tokens N` | | Override max completion tokens |
| `--generate.temperature T` | | Override sampling temperature |
| `--generate.json-mode BOOL` | | Override JSON mode (true/false) |
| `--generate.extra-body JSON` | | JSON object deep-merged onto the pipeline's `extra_body` |

## Override hierarchy

Settings are applied in this order — right wins on conflict:

```
profile (mm.toml)  →  pipeline YAML (generate.*)  →  CLI flags
  base_url               prompt                         --prompt / --generate.prompt
  api_key                model                          --model  / --generate.model
  model (default)        max_tokens                     --generate.max-tokens
                         temperature                    --generate.temperature
                         json_mode                      --generate.json-mode
                         extra_body (deep-merged)       --generate.extra-body
```

## Caching

Extractions are cached in the SQLite database at `~/.local/share/mm/mm.db` keyed on:
- Content hash (xxh3) of the file
- Profile name
- Effective model
- Mode
- Override fingerprint

`--no-cache` bypasses the cache and forces a fresh extraction. A subsequent run without `--no-cache` will use the newly stored result.

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

When `--stream` is active, tokens are written to stdout incrementally as the
LLM generates them. `--stream` takes precedence over `--format` — formatted
output modes are bypassed. Multi-file streaming processes files sequentially
to avoid interleaved output.

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

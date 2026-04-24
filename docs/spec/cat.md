# mm cat

Unified content extraction. Behaviour driven by **file type × mode × pipeline**.

## Input

- **Multimodal**: auto-detects kind from extension → image, video, audio, document, text
- **Multi-file**: `mm cat a.jpg b.pdf c.mp4` — processes each sequentially
- **Large batches**: if the path count is **≥ 9** (i.e. more than 8 files; override with `MM_CAT_BATCH_CONFIRM_THRESHOLD`), `cat` asks for confirmation in a TTY; in non-interactive use it **exits with an error** unless you pass **`--yes` / `-y`**
- **Stdin**: `find . -name '*.pdf' | mm cat` — reads newline-delimited paths from stdin
- **Head/tail**: `-n 20` (first 20 lines), `-n -20` (last 20 lines)

## Modes

`--mode fast` (default) — local extraction, no LLM unless pipeline defines a `generate` step.
`--mode accurate` — LLM-powered descriptions via configured profile.

### Image

| | fast | accurate |
|---|---|---|
| Encoder | `resize` (max 512px) | `resize` (max 1024px) |
| Generate | 10-word description + 5 tags | ~200-word description + 10 tags + 10 objects |
| Tokens | 256 max | 2048 max |

### Video

Multi-file: `mm cat a.mp4 b.mp4 -y` runs each video sequentially; the same **≥ 9 paths** batch rule applies as for images.

| | fast | accurate |
|---|---|---|
| Encoder | `mosaic` (4×4 grid, 128 frames, up to 8 mosaics) | `frames-transcript` (1fps, whisper medium, no speedup) |
| Generate | 50-word description + tags | ~200-word summary + tags + scene breakdown |
| Tokens | 512 max | 1536 max |
| Audio | none | whisper medium, 1.0× speed |

### Audio

| | fast | accurate |
|---|---|---|
| Encoder | `transcribe` (whisper medium, 1.0×) | `transcribe` (whisper medium, 1.0×) |
| Generate | none — raw timestamped transcript | ~80-word summary from transcript |
| Tokens | — | 512 max |

### Document (PDF)

| | fast | accurate |
|---|---|---|
| Encoder | `page-text` (pypdfium2, 1 page/message) | `page-text` (pypdfium2, 1 page/message) |
| Generate | none — concatenated page text | lossless markdown restructuring |
| Tokens | — | 16384 max |

### Code / Text / Config

Passthrough in both modes — raw file content, no pipeline, no LLM.

## Caching

Unified L2 cache (SQLite at `~/.local/share/mm/mm.db`) for **both** fast and accurate modes.

- Cache key: `content_hash × profile × model × mode × overrides`
  - Same file with different modes/profiles/overrides → separate cache entries
- `--no-cache`: bypasses read, evicts existing entry, forces fresh run
- Cache hit indicator: footer shows `cached • 36ms • 412.8 KB • 7.0 MB/s`
- Embedding: on cache miss with accurate mode, `embed_file_chunks` auto-generates Gemini embeddings

## Verbose (`--verbose`/ `-v`)

Pipeline execution tree shown after content:

```
pipeline
  ├─ encode: resize • 0.0s → 1 parts (1 image)
  └─ generate: ollama • 2.3s • 354→195 tokens
```

- Encode-only pipelines (audio fast, document fast): single `└─` node
- Encode + generate: `├─` encode, `└─` generate
- Generate line: `profile_name • elapsed • prompt→completion tokens`

## Pipeline Customization

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

## Output Formats

- **TTY** (default): Rich-formatted with syntax highlighting for code files
- **Piped** (default): plain text, no ANSI codes
- `--format json`: `{"path", "mode", "content"}`
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
- `cached` prefix when served from L2 cache

## Introspection

- `--list-pipelines`: show all built-in and user-override pipeline YAML files
- `--list-encoders`: show all registered encoder strategies with parameters

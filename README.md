<div align="center">
<p align="center" style="width: 100%;">
    <img src="https://raw.githubusercontent.com/vlm-run/.github/refs/heads/main/profile/assets/vlm-black.svg" alt="VLM Run Logo" width="80" style="margin-bottom: -5px; color: #2e3138; vertical-align:
middle; padding-right: 5px;"><br>
</p>
  <h1>mm-ctx</h1>
</div>
<div align="center">
  <h3>Fast, multimodal context for agents</h3>
</div>
<div align="center">
  <a href="https://pypi.org/project/mm-ctx/"><img alt="PyPI Version" src="https://img.shields.io/pypi/v/mm-ctx.svg"></a>
  <a href="https://www.pepy.tech/projects/mm-ctx"><img alt="PyPI Downloads" src="https://img.shields.io/pypi/dm/mm-ctx"></a>
  <a href="https://pypi.org/project/mm-ctx/"><img src="https://img.shields.io/pypi/pyversions/mm-ctx.svg" alt="versions"></a>
  <a href="https://pypi.org/project/mm-ctx/"><img src="https://img.shields.io/pypi/l/mm-ctx" alt="License"></a>
  <a href="https://discord.gg/6aqcyvPF79"><img src="https://img.shields.io/badge/discord-chat-purple?color=%235765F2&label=discord&logo=discord" alt="Discord"></a>
  <a href="https://twitter.com/vlmrun"><img src="https://img.shields.io/twitter/follow/vlmrun.svg?style=social&logo=twitter" alt="Twitter Follow"></a>
  <a href="https://huggingface.co/spaces/vlm-run/mm-ctx"><img src="https://img.shields.io/badge/🤗%20Spaces-Try%20it-blue" alt="Try it on HF Spaces"></a>
</div>

<br />
<p align="center">
  <img src="https://vlm-run.github.io/mm/assets/mm-terminal-window-v2.png" alt="mm terminal demo" width="880" style="border-radius: 12px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);">
</p>

---

Familiar UNIX CLI tools like `find`, `grep`, `cat` — with multimodal powers.

`mm` offers both a CLI and a Python API that enable agents to work with file types that LLMs can't natively read, including images, video, audio, PDFs, and other binary formats. Rust core for speed, Python for dev-ex, UNIX philosophy for composability.

📖 **[Full documentation →](https://vlm-run.github.io/mm/)**

## Installation

```bash
# with pip
pip install mm-ctx

# with uv
uv pip install mm-ctx

# or run directly without installing
uvx --from mm-ctx mm --help
```

<details>
<summary>Alternative install methods (shell / PowerShell)</summary>

```bash
# macOS / Linux (shell installer)
curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh

# Windows (PowerShell)
irm https://vlm-run.github.io/mm/install/install.ps1 | iex
```
</details>

<details>
<summary>Optional extras for audio transcription (<code>mlx</code> / <code>gpu</code>)</summary>

| Install | Best for | Audio transcription path |
|---------|----------|--------------------------|
| `mm-ctx[mlx]` | Apple Silicon / macOS with MLX | `lightning-whisper-mlx` first, then OpenAI compatible transcription endpoints (`/audio/transcriptions`) |
| `mm-ctx[gpu]` | Linux/Windows GPU hosts | `ctranslate2/faster-whisper` first, then OpenAI compatible transcription endpoints (`/audio/transcriptions`) |
| `mm-ctx` default / CPU | Standard installs | OpenAI compatible transcription endpoints (`/audio/transcriptions`) |

`mm` defaults to OpenAI-compatible endpoints (`/audio/transcriptions`) for audio transcription.
With the `mlx` extra on Apple Silicon, MLX is tried first; with `gpu`, ctranslate2/faster-whisper is tried first.
Override explicitly with `--encode.backend`:

```bash
mm cat audio.mp3 --encode.backend mlx          # mlx on Apple Silicon
mm cat audio.mp3 --encode.backend ctranslate2  # ctranslate2
mm cat audio.mp3 --encode.backend openai       # force OpenAI-compatible endpoint
```
</details>

## CLI

Commands that mirror familiar Unix tools but operate on multimodal semantics.
Indexing is implicit — every command auto-builds a metadata index on first use, and
metadata commands (`find`, `wc` with `--format json`) run in **~60ms** on 700 files via the Rust fast path.

<details>
<summary>Grab sample files to follow along</summary>

Download sample files from vlm.run to try the examples below:

```bash
mkdir mm-samples && cd mm-samples
curl -LO https://storage.googleapis.com/vlm-data-public-prod/hub/examples/image.caption/bench.jpg
curl -LO https://storage.googleapis.com/vlm-data-public-prod/hub/examples/document.invoice/wordpress-pdf-invoice-plugin-sample.pdf
curl -LO https://storage.googleapis.com/vlm-data-public-prod/hub/examples/video/Timelapse.mp4
curl -LO https://storage.googleapis.com/vlm-data-public-prod/hub/examples/mixed-files/mp3_44100Hz_320kbps_stereo.mp3
```
</details>

With the four sample files downloaded, `mm` treats the folder as a multimodal workspace:

```bash
$ mm find mm-samples/ --tree
```
```
mm-samples  (4 files, 3.5 MB)
├── Timelapse.mp4  [3.0 MB]
├── bench.jpg  [253.8 KB]
├── mp3_44100Hz_320kbps_stereo.mp3  [286.0 KB]
└── wordpress-pdf-invoice-plugin-sample.pdf  [42.6 KB]
```

```bash
$ mm wc mm-samples/ --by-kind
```
```
kind      files  size      lines (est.)  tokens (est.)  tok_per_mb
audio     1      286.0 KB  0             85             304
document  1      42.6 KB   29            176            4.2K
image     1      253.8 KB  0             425            1.7K
video     1      3.0 MB    0             85             29
—————
total     4      3.5 MB    29            771            218
```

<details>
<summary>More walkthrough examples — <code>find</code>, <code>cat</code>, <code>grep</code></summary>

```bash
$ mm find mm-samples/ --columns name,kind,size,ext
```
```
name                                     kind      size     ext
bench.jpg                                image     259865   .jpg
Timelapse.mp4                            video     3113073  .mp4
mp3_44100Hz_320kbps_stereo.mp3           audio     292853   .mp3
wordpress-pdf-invoice-plugin-sample.pdf  document  43627    .pdf
```

```bash
$ mm cat mm-samples/wordpress-pdf-invoice-plugin-sample.pdf -n 10
```
```
wordpress-pdf-invoice-plugin-sample.pdf — pages 1-1 of 1:

--- Page 1 ---
INVOICE
Sliced Invoices
Suite 5a-1204 123 Somewhere Street
Your City AZ 12345
admin@slicedinvoices.com
Invoice Number: INV-3337
Invoice Date: January 25, 2016
Due Date: January 31, 2016
Total Due: $93.50
0.8s • 42.6 KB • 53.2 KB/s
```

```bash
$ mm cat mm-samples/bench.jpg -m accurate
```
```
<description>
This outdoor daytime photograph captures a peaceful park scene on a sunny day. The primary focus is a modern dark gray metal slat bench  positioned in the foreground on a patch of green grass. The bench is set upon a small concrete pad, and its curved backrest and armrests  create a sleek, contemporary silhouette. Behind the bench, a paved walkway cuts through a well-maintained lawn.
</description>

Tags: park, bench, outdoors, summer, grass, trees, street, urban, leisure, sunlight

Objects: metal bench, tree, car, white SUV, red car, concrete pad, walkway, grass, street, building
```

```bash
$ mm grep "invoice" mm-samples/
```
```
wordpress-pdf-invoice-plugin-sample.pdf
    2 Payment is due within 30 days from date of invoice. Late payment is subject to fees of 5% per month.
    3 Thanks for choosing DEMO - Sliced Invoices | admin@slicedinvoices.com
   10 admin@slicedinvoices.com
```
</details>

<details>
<summary>Quick-start command cheatsheet</summary>

```bash
mm --version                                                    # print version
mm find mm-samples/ --tree --depth 1                            # directory overview with sizes
mm wc mm-samples/ --by-kind                                     # file/byte/token counts by kind

# mm peek: raw file metadata (dimensions / EXIF / codec / mime / hash).
mm peek bench.jpg                                               # image dimensions, EXIF, hash
mm peek Timelapse.mp4                                           # video resolution, duration, codecs
mm peek wordpress-pdf-invoice-plugin-sample.pdf                 # mime, content hash
mm peek bench.jpg Timelapse.mp4 --format json                   # multi-file JSON
mm peek paper.pdf --full                                        # include document author / title / page count

# mm cat: content extraction. Default --mode fast.
mm cat wordpress-pdf-invoice-plugin-sample.pdf                  # PDF page-text via pypdfium2 (fast pipeline)
mm cat src/main.py                                              # passthrough text + chunk + embed (kind=text)
mm cat notes.docx                                               # libreoffice-rs text
mm cat bench.jpg                                                # short VLM caption (fast pipeline)
mm cat wordpress-pdf-invoice-plugin-sample.pdf -n 20            # first 20 lines
mm cat -y *.jpg *.png                                           # batch (skip ≥9-path confirmation)
mm cat photo.png --no-generate                                  # snapshot encoder output (no LLM call)

# --mode accurate: full LLM pipeline for image/video/audio/PDF (requires a configured profile)
mm cat bench.jpg -m accurate                                    # LLM caption + tags + objects
mm cat Timelapse.mp4 -m accurate                                # keyframe mosaic → LLM description
mm cat mp3_44100Hz_320kbps_stereo.mp3 -m accurate               # Whisper transcript only (use -p native or -p gemini-native for LLM description)
mm cat wordpress-pdf-invoice-plugin-sample.pdf -m accurate      # LLM-structured invoice
```
</details>

### Command reference

Every command mirrors a familiar Unix tool. Follow the links for the full flag reference on the docs site.

| Command | Purpose | Docs |
|---------|---------|------|
| [`find`](https://vlm-run.github.io/mm/find/)  | Find/list files; tabular, tree, or schema view | [find →](https://vlm-run.github.io/mm/find/) |
| [`peek`](https://vlm-run.github.io/mm/peek/)  | Local file metadata (dimensions / EXIF / codec / duration / mime / hash) | [peek →](https://vlm-run.github.io/mm/peek/) |
| [`cat`](https://vlm-run.github.io/mm/cat/)   | Content extraction (auto-detected by kind × mode); pipeline-driven | [cat →](https://vlm-run.github.io/mm/cat/) |
| [`grep`](https://vlm-run.github.io/mm/grep/)  | Text + semantic content search | [grep →](https://vlm-run.github.io/mm/grep/) |
| [`sql`](https://vlm-run.github.io/mm/sql/)   | SQL on `files` / `extractions` / `chunks` (auto-routed) | [sql →](https://vlm-run.github.io/mm/sql/) |
| [`wc`](https://vlm-run.github.io/mm/wc/)    | Count files, bytes, lines (est.), tokens (est.) | [wc →](https://vlm-run.github.io/mm/wc/) |
| [`bench`](https://vlm-run.github.io/mm/bench/) | Benchmark suite with statistical analysis | [bench →](https://vlm-run.github.io/mm/bench/) |
| [`config`](https://vlm-run.github.io/mm/config/) | Configuration & diagnostics | [config →](https://vlm-run.github.io/mm/config/) |
| [`profile`](https://vlm-run.github.io/mm/profile/) | LLM provider profiles | [profile →](https://vlm-run.github.io/mm/profile/) |

Top-level: `mm [-p / --profile NAME] [--color auto/always/never] [--debug] [-v / --version] <command>`.
See the [CLI overview](https://vlm-run.github.io/mm/cli/) for the complete flag matrix.

<details>
<summary><code>find</code> — locate/list, tree, and schema</summary>

```bash
mm find ~/data --kind image                               # all images
mm find ~/data --kind video --sort size --reverse         # videos by size
mm find ~/data --ext .pdf --min-size 10mb                 # large PDFs
mm find ~/data --kind image --limit 5 --format json       # JSON output
mm find ~/data --name "test_.*\.py"                       # regex name match
mm find ~/data -n config                                  # substring name match
mm find ~/data -n CONFIG -i                               # case-insensitive (-i)

mm find ~/data --sort size --reverse --limit 20        # tabular listing
mm find ~/data --kind document --columns name,size,ext
mm find ~/data --tree --depth 2                        # hierarchical tree view
mm find ~/data --tree --kind video                     # tree filtered to videos
mm find ~/data --schema                                # column names, types, descriptions
mm find ~/data --format json                           # full metadata JSON
mm find ~/data --no-ignore                             # include gitignored files
```

Full reference: [find docs →](https://vlm-run.github.io/mm/find/)
</details>

<details>
<summary><code>peek</code> — raw file metadata</summary>

`mm peek` returns locally-extracted metadata (dimensions / EXIF / codec / duration / mime / hash …).

```bash
mm peek bench.jpg                                                # image dims / EXIF / hash (Rich panel)
mm peek Timelapse.mp4                                            # video resolution, duration, codecs
mm peek wordpress-pdf-invoice-plugin-sample.pdf                  # mime, content hash
mm peek bench.jpg Timelapse.mp4 --format json                    # multi-file JSON
mm peek bench.jpg --format tsv                                   # flat TSV (every kind has the same column set)
mm peek paper.pdf --full                                         # include document author / title / subject / page count
```

Full reference: [peek docs →](https://vlm-run.github.io/mm/peek/)
</details>

<details>
<summary><code>cat</code> — content extraction</summary>

`--mode` is one of `fast` (default) or `accurate`. Mode is a no-op for `kind=text` and non-PDF documents (`.docx` / `.pptx`): they always return passthrough text.

```bash
mm cat wordpress-pdf-invoice-plugin-sample.pdf                  # PDF page-text via pypdfium2 (fast pipeline)
mm cat wordpress-pdf-invoice-plugin-sample.pdf -n 20            # first 20 lines (head)
mm cat src/main.py                                              # passthrough text
mm cat notes.docx                                               # libreoffice-rs text
mm cat bench.jpg                                                # short VLM caption (fast pipeline)
mm cat bench.jpg -m accurate                                    # full LLM caption + tags + objects
mm cat Timelapse.mp4 -m accurate                                # mosaic → LLM description
mm cat bench.jpg -p tile                                  # use named encoder
mm cat bench.jpg -m accurate -p my-pipeline.yaml                # custom pipeline YAML
mm cat Timelapse.mp4 -m accurate --no-cache                     # force fresh LLM call
mm cat bench.jpg -m accurate --no-generate                      # snapshot encoder output (no LLM)
mm cat bench.jpg -m accurate -v                                 # verbose (shows pipeline tree)
mm cat bench.jpg -m accurate --stream                            # stream LLM tokens to stdout
mm cat --list-pipelines                                         # list registered pipelines
mm cat --list-encoders                                          # list registered encoders
mm cat --print-pipeline image/accurate                          # print a built-in pipeline's YAML source
mm cat bench.jpg -m accurate --encode.strategy_opts max_width=768  # override a single strategy_opts entry
mm cat mp3_44100Hz_320kbps_stereo.mp3 -m accurate --encode.backend mlx          # force MLX transcription (Apple Silicon)
mm cat mp3_44100Hz_320kbps_stereo.mp3 -m accurate --encode.backend openai       # force OpenAI-compatible endpoint
mm cat mp3_44100Hz_320kbps_stereo.mp3 -m accurate --encode.model whisper-1      # override transcription model
```

**Override surfaces** — `mm cat` resolves each LLM call from three layers, with **right-most wins** on conflict: **Profile** (`mm.toml`: `base_url`, `api_key`, default `model`) → **Pipeline YAML** (`generate:` block) → **CLI flags on `cat`** (per-field overrides such as `--model`, `--prompt`, `--generate.max-tokens`, `--generate.extra-body`).

Use `--generate.extra-body` for provider-specific knobs (vlmrt's `method`, `method_params`, `video_fps`, `image_resolution`, etc.):

```bash
# Florence-2 — document OCR (skip server-side LLM refinement)
mm --profile vlmrt cat page.png -m accurate \
  --model florence-2-base-ft \
  --generate.extra-body '{"method":"ocr","refine_with_llm":false}'

# PaddleOCR-v6 — Chinese OCR with a tighter score threshold
mm --profile vlmrt cat storefront.jpg -m accurate \
  --model paddleocr-v6 \
  --generate.extra-body '{"method":"ocr","method_params":{"lang":"ch","score_threshold":0.6}}'
```

Full reference (all override flags + more model examples): [cat docs →](https://vlm-run.github.io/mm/cat/)
</details>

<details>
<summary><code>grep</code> — content + semantic search</summary>

```bash
mm grep "attention" ~/data --kind document
mm grep "TODO" ~/data --kind code
mm grep "invoice" ~/data --count               # match counts per file
mm grep "Quantum Phase" ~/data -i              # case-insensitive search
mm grep "secret" ~/data --no-ignore            # search gitignored files
mm grep "revenue forecast" ~/data -s             # semantic (vector) search
mm grep "architecture" ~/data -s --pre-index      # auto-index before search
mm grep -- "--release" ./Makefile                # pattern starting with - (see note)
```

> **Patterns starting with `-` or `--`:** the CLI parser treats them as options
> (`mm grep "--release"` fails with `No such option`). Put `--` before the
> pattern to mark the end of options: `mm grep -- "--release" ./Makefile`. This
> matches standard `grep`/`ripgrep` behavior.

Full reference: [grep docs →](https://vlm-run.github.io/mm/grep/)
</details>

<details>
<summary><code>sql</code> — query the index</summary>

Queries file metadata via scan + SQLite, or results and chunks from the persistent SQLite store.

```bash
mm find ~/data --schema                          # see available columns
mm sql "SELECT kind, COUNT(*) as n, ROUND(SUM(size)/1e6,1) as mb \
  FROM files GROUP BY kind ORDER BY mb DESC" --dir ~/data

# Query stored tables directly (auto-detected from table name)
mm sql "SELECT file_uri, summary FROM extractions LIMIT 10"
mm sql "SELECT file_uri, chunk_idx, LENGTH(chunk_text) FROM chunks"
mm sql "SELECT * FROM files WHERE kind='image'" --dir ~/data --pre-index  # index before query
mm sql --list-tables                              # show available tables
```

Full reference: [sql docs →](https://vlm-run.github.io/mm/sql/)
</details>

<details>
<summary><code>wc</code> — count files, size, tokens</summary>

```bash
mm wc ~/data --by-kind
mm wc ~/data --by-kind --format json
```

Full reference: [wc docs →](https://vlm-run.github.io/mm/wc/)
</details>

<details>
<summary><code>bench</code> — benchmarks with statistical analysis</summary>

<p align="center">
  <img src="https://vlm-run.github.io/mm/assets/mm-benchmarks-14052026.png" alt="mm bench output" width="880" style="border-radius: 12px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);">
</p>

`overhead + metadata` always run; `--mode` adds an extraction tier on top.

```bash
mm bench mm-samples/                                  # overhead + metadata (default)
mm bench mm-samples/ --mode fast                      # + fast-mode extractions
mm bench mm-samples/ --mode accurate                  # + accurate-mode extractions
mm bench mm-samples/ --mode all                       # full suite (fast + accurate)
mm bench mm-samples/ --rounds 5                       # more rounds for stability
mm bench mm-samples/ --format json                    # JSON output for archival
mm bench --host-info                                  # print host spec and exit
```

Filters combine via AND (`--command`, `--group`), custom benchfiles can be supplied with `--bench-file`, and
`--format stdout` emits raw stdout between `---` separators for refreshing golden-file snapshots.
Every non-dry-run `mm bench` auto-writes a per-row markdown recording to `benchmarks/results/`.

Full reference: [bench docs →](https://vlm-run.github.io/mm/bench/)
</details>

<details>
<summary>Output modes (<code>--format</code>) &amp; verbose mode</summary>

- **TTY**: Rich-formatted tables/panels.
- **Piped / non-TTY**: plain TSV/text (machine-readable, no ANSI).
- `--format json`: compact in pipes, indented in TTY.
- `--format pretty-json`: always indented (good for piping into markdown / docs).
- `--format tsv` / `csv`: delimited.
- `--format dataset-jsonl`: JSONL for fine-tuning datasets.
- `--format dataset-hf`: HuggingFace Datasets format (requires `--output-dir`).
- `--format stdout`: plain stdout (cat / config show / bench snapshot).

`mm cat <file> [OPTIONS] --verbose` shows the pipeline execution tree after content:

```
pipeline
  ├─ encode: resize · 0.0s → 1 parts (1 image)
  └─ generate: ollama · 2.3s · 354→195 tokens
```
</details>

## Python API

`mm` is also a library. `mm.Context` is the one class you need to build a multimodal prompt incrementally, then hand the whole thing to a VLM. Backed by a Rust core: O(1) insert/lookup, sub-millisecond render at 10K items.

The public namespace is intentionally tiny:

```python
import mm
mm.Context              # the one class you use
mm.Ref                  # Annotated[str, "mm.Ref"] typed alias for ref ids
mm.RefNotFoundError     # KeyError subclass raised by ctx.get on miss
mm.uuid7()              # UUIDv7 helper (time-ordered default session_id)
mm.render_context(ctx)  # Rich HTML rendering for notebooks (source-aware)
mm.render_messages(msgs)# Lightweight HTML rendering for any message list
```

### Build a prompt

```python
import mm
from pathlib import Path
from PIL import Image

ctx = mm.Context(session_id=mm.uuid7())      # or omit; auto-mints a UUIDv7

sys:  mm.Ref = ctx.add("You are a terse visual analyst.", role="system")
txt:  mm.Ref = ctx.add("Summarize these assets.", role="user")
img:  mm.Ref = ctx.add(Path("photo.jpg"), role="user")
doc:  mm.Ref = ctx.add(Path("paper.pdf"), role="user",
                       metadata={"summary": "Attention is all you need",
                                 "tags": ["nlp", "transformer"]})
```

`ctx.add(obj, *, role="user", metadata=...)` accepts free-form `str` text, a `pathlib.Path`, or a `PIL.Image.Image`. Strings can use `system`, `developer`, or `user`; media must use `user`. Every `add` returns a short kind-prefixed ref id like `img_a1b2c3`, typed as `mm.Ref`, and can be removed with `ctx.remove(ref)`.

### Emit VLM-ready messages (OpenAI / Gemini)

```python
messages_openai = ctx.to_messages(format="openai")
messages_gemini = ctx.to_messages(format="gemini")

# Per-kind encoder overrides
messages = ctx.to_messages(format="openai", encoders={"image": "tile", "video": "mosaic"})
```

Drop `messages_openai` directly into `client.chat.completions.create(messages=...)`, or `messages_gemini` into `model.generate_content(contents=...)`. Unspecified kinds fall back to sensible defaults (`resize`, `mosaic`, `rasterize`, `base64`).

<details>
<summary>Round-trip, resolve, and render</summary>

```python
obj = ctx.get(img)                                            # instance: returns the stored object
row = mm.Context.get(f"{ctx.session_id}/{img}")               # classmethod: cross-session DB lookup
```

Instance `ctx.get(ref)` returns the exact Python object you added — identity is preserved for in-memory items (no copy, no rehydrate). Classmethod `mm.Context.get("<session>/<ref>")` resolves against the global `~/.local/share/mm/mm.db` when you only have a ref string and no live `Context`. A miss raises `mm.RefNotFoundError` (a `KeyError` subclass) with a Levenshtein-based "did you mean" and the full context table inline.

```python
ctx.print_tree()                  # insertion-order tree with metadata
print(ctx.to_md(mode="metadata")) # markdown: ref | kind | source | content
print(repr(ctx))                  # markdown summary: ref | kind | source
```

```
Context(session=019da4…, items=4)
├── [1] img_a1b2c3  image     /abs/path/photo.jpg
├── [2] img_9f0e12  image     PIL.Image(RGB, 1024×768)
│        └─ note: "product hero shot"
├── [3] doc_d4e5f6  document  /abs/path/paper.pdf
│        ├─ summary: "Attention is all you need"
│        └─ tags: [nlp, transformer]
└── [4] vid_7890ab  video     /abs/path/clip.mp4
         ├─ scene: 3
         └─ actor: "A"
```
</details>

`Context("~/data")` also supports the directory-scan surface (`to_polars`, `to_pandas`, `to_arrow`, `sql`, `show`, `info`).
Full spec — `print_tree` layouts, cross-session resolution, the deferred `save()` API — in the [Python API docs →](https://vlm-run.github.io/mm/api/).

## Integrations

<details>
<summary>Claude Code, npx skills, and universal assistants</summary>

**Claude Code** — install the `mm-cli-skill` via the skill marketplace:

```bash
claude
> /plugin marketplace add vlm-run/skills
> /plugin install mm-cli-skill@vlm-run/skills
> Organize my ~/Downloads folder using mm
```

**npx skills** — install mm-cli-skill globally so any CLI assistant or agentic tool can discover it:

```bash
npx skills add vlm-run/skills@mm-cli-skill
```

**Universal assistants** (OpenClaw, NemoClaw, OpenCode, Codex, Gemini CLI) — install the skill globally, then start your preferred tool:

```bash
# One-time setup
npx skills add vlm-run/skills@mm-cli-skill

# Then use any CLI assistant — it will discover mm automatically
openclaw "Organize my ~/Downloads folder using mm"
codex "Find all PDFs in ~/docs and summarize them with mm"
```

The skill exposes mm's capabilities to any tool that supports the skills protocol.
</details>

## Processing tiers

`mm` separates **what** by command and **how much LLM** by mode. `mm peek` surfaces local file metadata; `mm cat` extracts content and accepts `--mode fast|accurate` (default `fast`).

| Tier            | Command          | What                                                                                | LLM?    |
| --------------- | ---------------- | ----------------------------------------------------------------------------------- | ------- |
| **metadata**    | `mm peek`        | image dims/EXIF/hash, video resolution/duration/codec, audio codec, mime, magika    | never   |
| **fast** (default) | `mm cat -m fast` | Output of the kind's `fast` pipeline                                                | maybe¹  |
| **accurate**    | `mm cat -m accurate` | Output of the kind's `accurate` pipeline                                            | yes     |

¹ Per-kind fast pipelines: image/video include a short LLM caption stage; audio/document/code do not.
Metadata-tier extraction (used by `find`, `wc`, the `cat` default, and as the input for fast/accurate pipelines) is Rust-native (~60ms / 700 files).

## Performance

Benchmarked on Apple Silicon (M-series), 702 files (7.2GB):

| Operation                                      | Latency |
| ---------------------------------------------- | ------- |
| Metadata scan (702 files)                      | 8ms     |
| CLI cold start (`find --format json`)          | 60ms    |
| CLI cold start (`find --schema --format json`) | 109ms   |
| CLI cold start (`sql`)                         | 300ms   |
| Fast code extraction                           | ~52ms   |
| Fast image extraction                          | ~61ms   |
| Fast PDF text extraction                       | ~220ms  |
| Fast video metadata                            | <100ms  |
| PDF page mosaic (per page)                     | ~10ms   |
| Video keyframe mosaic (48 frames)              | ~1s     |

## Pipelines & storage

Pipelines are YAML configs under `pipelines/{kind}/{mode}.yaml` that pair an **encoder** with optional LLM **generation** parameters. When `generate` is `null`, the pipeline is encode-only (no LLM call). Encoders are Python classes under `encoders/` that convert media files into VLM-ready Messages.

```bash
mm cat photo.jpg -m accurate --encode.strategy tile --generate.max-tokens 1024
mm cat --print-pipeline image/accurate            # print a built-in pipeline as a starting point
mm cat photo.jpg -p my-image-pipeline.yaml        # load an explicit pipeline YAML
```

See the [pipelines →](https://vlm-run.github.io/mm/pipelines/) and [encoders →](https://vlm-run.github.io/mm/encoders/) docs for the full reference.

<details>
<summary>Storage — global SQLite + sqlite-vec</summary>

mm uses a global SQLite database at `~/.local/share/mm/mm.db` with sqlite-vec for vector search:

| Table              | Contents                                                          | Relationship                |
| ------------------ | ----------------------------------------------------------------- | --------------------------- |
| `files`            | File metadata + content (one row per file, `uri` = absolute path) | —                           |
| `extractions`      | LLM-generated summaries (many per file)                           | FK → `files.uri`            |
| `chunks`           | Content chunks (mode = 'metadata', 'fast', or 'accurate')         | FK → `extractions.id`       |
| `chunks_vec`       | Embedding vectors (sqlite-vec virtual table)                      | FK → `chunks.id`            |
| `cache`            | Key-value result cache                                            | —                           |

The `files` table includes metadata columns (path, size, kind, etc.) and content columns (content_hash, text_preview, line_count, duration_s, exif_*, video_codec, etc.). Use `mm config reset-db` to clear all databases and caches.
</details>

## LLM configuration (profiles)

For accurate mode, `mm` uses the `openai` Python SDK to call any OpenAI-compatible API. Provider settings are managed through **profiles** — named configurations (`base_url`, `api_key`, `model`) stored in `~/.config/mm/mm.toml`.

```bash
mm config init                                                       # create config with default profile (local Ollama)
mm profile add openai --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o
mm profile use openai                                                # switch active profile
mm --profile openai cat photo.png -m accurate                        # one-off override (also: MM_PROFILE env)
```

The active profile resolves as: `--profile flag` > `MM_PROFILE env` > `active_profile` in config file > `"ollama"`.

<details>
<summary>Managing profiles &amp; config file format</summary>

```bash
mm profile add openrouter --base-url https://openrouter.ai/api/v1 --model qwen/qwen3.5-27b
mm profile update ollama --base-url http://localhost:11434 --model qwen3.5:9B
mm profile list                                              # list all profiles (● = active)
mm profile clone ollama my-ollama --model qwen3-vl:8b        # clone + override fields
mm profile remove openai                                     # cannot remove the active one
```

```toml
# ~/.config/mm/mm.toml
active_profile = "ollama"

[profile.ollama]
base_url = "http://localhost:11434"
api_key = ""
model = "qwen3.5:0.8"

[profile.gateway]
base_url = "https://gateway.vlm.run/v1/openai"
api_key = ""
model = "Qwen/Qwen3.5-0.8B"
```

Full reference: [profile →](https://vlm-run.github.io/mm/profile/) and [config →](https://vlm-run.github.io/mm/config/) docs.
</details>

## Contributing

We welcome and value any contributions and collaborations. Please check out [Contributing to mm-ctx](CONTRIBUTING.md) for how to get involved.

## License

MIT

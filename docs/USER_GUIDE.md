# mm — User Guide

Fast, multimodal context for agents.
Rust core for speed. Python for developer experience. Unix philosophy for composability.

---

## Prerequisites

### Installation

```bash
pip install mm-ctx

# with uv
uv pip install mm-ctx

# or run directly without installing
uvx --from mm-ctx mm --help
```

Alternative methods:

```bash
# macOS / Linux (shell installer)
curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://vlm-run.github.io/mm/install/install.ps1 | iex
```

### VLM access

mm requires access to a VLM on a live server for accurate-mode (LLM-powered) operations. Recommended models:

| Provider | Models |
|----------|--------|
| Qwen     | `qwen3vl-2b\|4b\|8b\|32b`, `qwen3.5:2b\|9b\|27b` |
| Gemini   | `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite-preview` |

### Profile setup

mm uses profiles to store provider credentials. There are 3 reserved profiles: `ollama`, `gemini`, and `vlmrun`.

You can populate a reserved profile or create a new one:

```bash
# Use an existing reserved profile
mm profile update ollama --base-url http://localhost:11434/v1 --model qwen3vl-8b

# Or create a custom profile
mm profile add fermi \
  --base-url https://openrouter.ai/api/v1 \
  --api-key "your-openrouter-api-key" \
  --model google/gemini-2.5-flash-lite

# Set the active profile
mm profile use fermi
```

---

## Integrations

### Claude Code

Install the `mm-cli-skill` via the skill marketplace:

```bash
claude
> /plugin marketplace add vlm-run/skills
> /plugin install mm-cli-skill@vlm-run/skills
> Organize my ~/Downloads folder using mm
```

### npx skills

Install mm-cli-skill globally so any CLI assistant or agentic tool can discover it:

```bash
npx skills add vlm-run/skills@mm-cli-skill
```

### Universal assistants (OpenClaw, NemoClaw, OpenCode, Codex, Gemini CLI)

Install the mm-cli-skill globally first, then start your preferred tool:

```bash
# One-time setup
npx skills add vlm-run/skills@mm-cli-skill

# Then use any CLI assistant — it will discover mm automatically
openclaw "Organize my ~/Downloads folder using mm"
codex "Find all PDFs in ~/docs and summarize them with mm"
```

The skill exposes mm's capabilities to any tool that supports the skills protocol.

---

## Use cases

Use mm directly or through a CLI assistant (e.g. `claude "Organize ~/Downloads using mm"`).

### Directory actions

- Organize files by type, date, or inferred content
- Flatten or restructure nested folders based on content signals
- Cluster photos by person, location, or event

### Semantic search

```bash
mm grep "photo of me and my dog in a park" ~/photos -s
mm grep "revenue forecast" ~/reports -s --kind document
mm grep "architecture overview" ~/docs -s --pre-index   # auto-index unindexed files
```

Returns matching files via vector similarity (embeddings). Use `--semantic/-s` for semantic search, `--pre-index` to auto-index unindexed files before searching.

### File inspection and extraction

```bash
# Default --mode metadata: local extraction only, no LLM call.
mm cat report.pdf              # PDF text via pypdfium2
mm cat image.jpg               # image dimensions, MIME, hash, EXIF
mm cat video.mp4               # video resolution, duration, codecs (<100ms)

# --mode fast: kind's fast pipeline (image/video include a short LLM caption stage).
mm cat image.jpg -m fast       # short VLM caption
mm cat video.mp4 -m fast       # mosaic → short VLM description

# --mode accurate: LLM-heavy pipeline (requires a configured profile).
mm cat image.jpg -m accurate   # LLM-powered caption + tags + objects
mm cat video.mp4 -m accurate   # keyframe mosaic → LLM description
mm cat audio.mp3 -m accurate   # transcript → LLM summary
```

### Pipeline customization

`-p`, `--encode.*`, and `--generate.*` only take effect under `--mode fast`
or `--mode accurate`; the default `metadata` mode skips the pipeline.

```bash
mm cat photo.png -m fast -p image-tile                     # use named encoder
mm cat photo.png -m accurate -p my-pipeline.yaml           # custom pipeline YAML
mm cat photo.png -m accurate --encode.strategy image-tile  # override encoder
mm cat photo.png -m accurate --generate.max-tokens 1024    # override generation
mm cat --list-encoders                                     # list all registered encoders
mm cat --list-pipelines                                    # list built-in pipelines
```

### Override surfaces

Every `mm cat` invocation resolves its LLM call from three layers, with
**CLI > pipeline YAML > profile** precedence on conflict:

1. **Profile** (`mm.toml`) — owns `base_url`, `api_key`, default `model`.
   Switch profiles globally per-call with `mm --profile <name> <subcommand>`.
2. **Pipeline YAML** (`generate:` block) — `model`, `prompt`, `max_tokens`,
   `temperature`, `json_mode`, `extra_body`. Each pipeline can pin
   provider-specific defaults so a single command stays terse.
3. **CLI flags on `cat`** — per-field, per-invocation overrides:

| Flag | Alias | Pipeline field |
|------|-------|----------------|
| `--model NAME` | `--generate.model` | `generate.model` |
| `--prompt TEXT` | `--generate.prompt` | `generate.prompt` |
| `--generate.max-tokens N` | — | `generate.max_tokens` |
| `--generate.temperature F` | — | `generate.temperature` |
| `--generate.json-mode BOOL` | — | `generate.json_mode` |
| `--generate.extra-body '<json>'` | — | `generate.extra_body` (deep-merged) |

`base_url` and `api_key` are profile-only — there is no CLI override for them.
The merged `model` + `extra_body` participate in the L2 cache key, so changing
a knob correctly invalidates cached results.

Using these flags to drive an arbitrary OpenAI-compatible deployment
(e.g. [vlmrt](https://github.com/vlm-run/vlm-playground/blob/main/projects/vlmrt/docs/openai-chat-completions-compat.md),
where each model dispatches by `extra_body.method`):

```bash
# Florence-2 — document OCR
mm --profile vlmrt cat page.png -m accurate \
  --model florence-2-base-ft \
  --generate.extra-body '{"method":"ocr"}'

# Qwen3.5-0.8B — free-form video summarisation, custom frame sampling
mm --profile vlmrt cat clip.mp4 -m accurate \
  --model qwen3.5-0.8b \
  --generate.extra-body '{"video_fps":1.0,"video_max_frames":8}'

# PaddleOCR-v5 — Chinese scene-text OCR with tighter score threshold
mm --profile vlmrt cat storefront.jpg -m accurate \
  --model paddleocr-v5 \
  --generate.extra-body '{"method":"ocr","method_params":{"lang":"ch","score_threshold":0.6}}'

# Moondream2 — multi-object detection with a custom prompt
mm --profile vlmrt cat photo.jpg -m accurate \
  --model moondream2 \
  --prompt "List every visible animal." \
  --generate.extra-body '{"method":"detect","method_params":{"object":"fish"}}'
```

### Batch operations

```bash
mm wc ~/docs                            # file count, bytes, lines, token estimate
mm find ~/videos                        # list with tags, duration, resolution
mm cat -m accurate video.mp4            # full context: transcript + scenes
mm find ~/images --kind image | mm cat -m accurate --format json  # batch captioning
mm find ~/images --kind image | mm cat --format json              # batch metadata (no LLM)
```

### Agentic integration

Use mm directly as a tool or as a skill for any coding assistants:

- *"Find all invoices in ~/Downloads and create a markdown table with totals"*
- *"Clip the first scene from video.mp4"*
- *"Extract all faces from ~/events/wedding"*

### Auto-labeling

Use mm as a labeling CLI for VLMs:

- Select provider with `--profile` or `MM_PROFILE` env for any OpenAI-compatible endpoint
- `--format dataset-jsonl` — outputs image (base64) + completion pairs for fine-tuning (OpenAI/Fireworks format)
- `--format dataset-hf` — builds HuggingFace datasets from input directories (requires `--output-dir`)

Pipeline: unlabeled media &#8594; `mm cat -m accurate --format dataset-jsonl` &#8594; fine-tuning

### Other examples

- Photo organization by topic or year, with highlighted selections from events
- *"Create a markdown file `260410.md` with a table of all invoices in ~/Downloads/invoices, including totals in USD"*

---

## Benchmark

Run the built-in benchmark suite:

```bash
mm bench ~/data/mmbench-mini --format rich
```

A standalone benchmark script is also available at `./benchmarks/bench_cli.sh`. It downloads public multimodal test data before running.

**Data sources:**
- `https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-mini.tar.gz`
- `https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz`

### Custom benchmark suites: `--bench-file`

For internal matrices, point `mm bench` at a Python file that exposes
`BenchCommand` entries:

```bash
mm bench ~/data/mmbench-tiny --bench-file benchmarks/vlmgw_bench_commands.py
mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py -r 1 -w 0
```

A benchfile must define **one** of:

```python
from mm.commands.bench_commands import BenchCommand

# (a) static list
COMMANDS: list[BenchCommand] = [...]

# (b) file-aware factory (preferred when commands depend on what's on disk)
def commands(files) -> list[BenchCommand]: ...
```

The factory takes precedence when both are present. The loaded set
**fully replaces** the built-in `overhead + metadata + <mode>` matrix —
`--mode` is ignored when `--bench-file` is set, and the benchfile's
own `BenchCommand.group` drives display grouping. `--command`
substring filtering and `--format` rendering still apply on top, so
you can scope a slow benchfile to a single row with
`--command image-resolution` or pipe its JSON to a custom renderer.

A worked example covering all `mm cat` override surfaces (model alias,
prompt overrides, `--generate.extra-body` deep-merge, video frame
sampling, cache cold/warm) lives in [`benchmarks/vlmgw_bench_commands.py`](../benchmarks/vlmgw_bench_commands.py).

### Inspecting a plan: `--dry-run`

`--dry-run` resolves the benchmark plan — directory pre-scan, file
selection, placeholder substitution — without invoking any
subprocess. Every row renders with `-` placeholders in the rich/tsv
table and `"dry_run": true` in JSON, with the resolved shell command
in `argv` for inspection:

```bash
mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py --dry-run
mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py --dry-run --format json
```

Useful for verifying a new benchfile before committing to a long run,
or for snapshotting the plan in CI without paying timing cost.

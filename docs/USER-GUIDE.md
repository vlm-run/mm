# mm — User Guide

High-performance multimodal context management library + CLI.
Rust core for speed. Python for developer experience. Unix philosophy for composability.

---

## Prerequisites

### Installation

Install mm via the pre-built wheels published to GitHub Pages:

```bash
# macOS / Linux
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
| Qwen     | `qwen3vl-2b\|4b\|8b\|32b`, `qwen3.5:0.8b\|2b\|9b\|27b` |
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

Install the `mm-skill` via the skill marketplace:

```bash
claude
> /plugin marketplace add vlm-run/skills
> /plugin install mm-skill@vlm-run/skills
> Organize my ~/Downloads folder using mm
```

### npx skill

Install mm-skill globally so any CLI assistant or agentic tool can discover it:

```bash
npx skill add vlm-run/mm-skill
```

### Other CLI assistants (OpenClaw, NemoClaw, OpenCode, Codex, Gemini CLI)

Install the mm-skill globally first, then start your preferred tool:

```bash
# One-time setup
npx skill add vlm-run/mm-skill

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
mm grep "photo of me and my dog in a park" ~/photos
```

Returns matching images and videos (via keyframe analysis).

### File inspection and extraction

```bash
mm cat report.pdf    # text summary + page count + embedded image count
mm cat image.jpg     # description + tags + EXIF metadata
mm cat video.mp4     # scene summary + transcript snippet + keyframe grid
```

### Batch operations

```bash
mm wc ~/docs              # file count, bytes, lines, token estimate
mm find ~/videos              # list with tags, duration, resolution
mm cat -m accurate video.mp4  # full context: transcript + scenes + metadata
```

### Agentic integration

Use mm directly as a tool or as a skill for any coding assistants:

- *"Find all invoices in ~/Downloads and create a markdown table with totals"*
- *"Clip the first scene from video.mp4"*
- *"Extract all faces from ~/events/wedding"*

### Auto-labeling (Planned)

Use mm as a labeling CLI for VLMs:

- Override provider with `--base-url` and `--model` for any OpenAI-compatible endpoint
- `--output-format dataset-jsonl` — outputs image (base64) + completion pairs for fine-tuning (OpenAI/Fireworks format)
- `--output-format dataset-hf` — builds HuggingFace datasets from input directories

Pipeline: unlabeled media &#8594; `mm` auto-label (JSONL) &#8594; fine-tuning

### Other examples

- Photo organization by topic or year, with highlighted selections from events
- *"Create a markdown file `260410.md` with a table of all invoices in ~/Downloads/invoices, including totals in USD"*

---

## Benchmarks

Benchmark mm against native Unix commands with hyperfine:

```bash
hyperfine --warmup 3 'grep -R TODO python' "mm grep 'TODO' python"
```

Or run the built-in benchmark suite:

```bash
mm bench ~/data/mmbench-mini --format rich
```

A standalone benchmark script is also available at `./benchmarks/bench_cli.sh`. It downloads public multimodal test data before running.

**Data sources:**
- `https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-mini.tar.gz`
- `https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz`

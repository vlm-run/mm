# vlmgw benchmark — 2026-05-01

Run: `mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py` (rounds=3, warmup=1) against the vlmgw gateway (`https://26bd-12-30-39-214.ngrok-free.app/v1/openai/`).

Every row uses `--mode fast --no-cache --format json` as the base command; per-row overrides live in **Extra Args** (`--prompt`, `--generate.extra-body`, `--encode.strategy_opts`).

Host: `Sudeeps-M3-Max.local` · Apple M3 Max (16 threads) · macOS 14.6 · Python 3.12.9 · mm v0.10.0.

---

## `mm bench` reference

`mm bench` is a statistical benchmarking harness for `mm` subcommands.
Every row in the table corresponds to a `BenchCommand` (a shell template
plus metadata: `group`, `requires_kind`, `tags`, `cmd_template`,
`smallest`, `batch`, `skip_reason`). The harness resolves each template
against the dataset, runs it `--warmup` then `--rounds` times, and
records mean / std / min / max / median latency per row. See
[`docs/USER_GUIDE.md`](../docs/USER_GUIDE.md) for the column layout
documentation; the `Group | Model | Base Command | Extra Args | <metrics>`
shape used here is the standard `--bench-file` rendering.

### Two modes

| Mode | What runs | When to use |
|---|---|---|
| **Default** | Built-in `overhead + metadata + <mode>` matrix from `python/mm/commands/bench_commands.py`. `--mode metadata` (default) skips the LLM tier entirely. | Local performance regression checks for the `mm find` / `mm cat` core surfaces. |
| **`--bench-file`** | A user-supplied Python module exposing `COMMANDS: list[BenchCommand]` (or `def commands(files) -> list[BenchCommand]`). **Replaces** the built-in matrix; `--mode` is ignored. | Custom matrices like this vlmgw run — compare across models, providers, override surfaces, and prompt variants. |

### Flags reference

| Flag | Description |
|---|---|
| `--rounds`, `-r` *INT* | Measurement rounds (default `3`). |
| `--warmup`, `-w` *INT* | Warmup rounds before timed runs (default `1`). Use `-w 0` for cold-only measurements. |
| `--mode`, `-m` *TEXT* | Default-suite tier: `metadata` (Unix-comparable, no LLM), `fast`, `accurate`, `all`. **Ignored when `--bench-file` is set.** |
| `--bench-file`, `-b` *PATH* | Replace the built-in matrix with a Python file's `COMMANDS` list. |
| `--dry-run` | Resolve the plan and render the same table with `-` placeholders. No commands execute. Useful for inspecting a new benchfile. |
| `--group`, `-g` *GROUP* | Keep rows where `BenchCommand.group == GROUP` (case-insensitive exact match). |
| `--model` *MODEL* | Keep rows where `tags['model'] == MODEL`. Cuts across groups. |
| `--command`, `-c` *TERM* | Substring filter on `BenchCommand.name`. Combines with `--group` / `--model` via AND. |
| `--format`, `-f` *FMT* | Output: `rich` (default Rich table), `json` (one host info line + one results line), `tsv`, `csv`, `stdout` (snapshot mode for `--command cat`). |
| `--host-info` | Print the host spec (CPU / RAM / GPU / Python / mm version) and exit. |

### Profile pinning

`mm bench` doesn't take a `--profile` flag itself — instead the
benchfile pins the profile inside each `cmd_template`. For this run:

```python
PROFILE = "vlmgw"
_CAT = f"mm --profile {PROFILE} cat"
_BASE_FLAGS = "--mode fast --no-cache --format json"
```

So every row resolves to `mm --profile vlmgw cat <file> --mode fast
--no-cache --format json [extras...]`. The profile (`base_url`,
`api_key`, default `model`) is read from `~/.config/mm/mm.toml`. See
[`docs/USER_GUIDE.md`](../docs/USER_GUIDE.md#table-layout-group--model--base-command--extra-args--metrics)
for the full override-surface contract: profile → pipeline yaml →
`mm cat` flags (`--model`, `--prompt`, `--generate.*`, `--encode.*`).

### Reproducing this run

```bash
# Plan inspection (no network):
mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py --dry-run

# Full run (rich table on stdout):
mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py

# Full run (machine-readable, used to regenerate this report):
mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py \
    --format json > /tmp/vlmgw-bench-260501.json

# Scope to one bucket / model:
mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py --group cache
mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py \
    --model qwen/qwen3.5-0.8b
mm bench ~/data/mmbench-tiny -b benchmarks/vlmgw_bench_commands.py \
    -g model --model facebook/sam3
```

### Benchfile structure

The benchfile (`benchmarks/vlmgw_bench_commands.py`) builds the
`COMMANDS` list from a higher-level `BenchSpec` matrix that mirrors the
upstream vlmgw model list, plus standalone `BenchCommand`s for the
`image-res`, `frames`, `cache`, `404`, and `validation` groups.
Each spec carries:

- `model` — the gateway model id (`<org>/<model-name>`).
- `prompt` — optional `--prompt` text. When omitted, the model
  receives no prompt (it relies on `extra_body.method` instead).
- `image` / `video` / `num_images` — drive the `requires_kind` /
  `batch` shape. Text-only specs (gliner, qwen/text) attach the
  smallest image as a no-op carrier because `mm cat` needs a file
  argument.
- `fps` / `max_frames` / `video_resolution` — folded into
  `--generate.extra-body` as `video_fps` / `video_max_frames` /
  `video_resolution`.
- `encode_max_width` — surfaces as `--encode.strategy_opts max_width=N`,
  a **client-side** PIL/Rust resize that runs before upload.
- `extra_body` — arbitrary dict deep-merged into the openai
  `extra_body` payload. Specs declaring an `llm` key route to
  `group="model+llm"` automatically.

---

## `noop` (3 rows)

Gateway round-trip cost. `noop/ping` is the smallest possible payload (text-only); `noop/image-{512,1024}` measure passthrough cost at two client-side encoder resolutions. (`vlm-run/noop` isn't in `/v1/openai/models` — these rows currently measure 404 round-trip cost on this gateway.)

| Name | Model | Base Command | Extra Args | Mean | ±Std | Min | Max | Speed | MB/s | bps |
|---|---|---|---|---|---|---|---|---|---|---|
| noop/ping | vlm-run/noop | `mm cat <img> --mode fast --no-cache --format json` | `--prompt ping` | 937ms | 36ms | 899ms | 970ms | 1.07x | — | 7.87 Mbps |
| noop/image-512 | vlm-run/noop | `mm cat <img> --mode fast --no-cache --format json` | `--encode.strategy_opts max_width=512` | 887ms | 11ms | 874ms | 897ms | 1.13x | — | 8.31 Mbps |
| noop/image-1024 | vlm-run/noop | `mm cat <img> --mode fast --no-cache --format json` | `--encode.strategy_opts max_width=1024` | 886ms | 7ms | 880ms | 894ms | 1.13x | — | 8.32 Mbps |

## `model` (29 rows)

Single-model variants — every entry from the upstream BenchSpec list.

| Name | Model | Base Command | Extra Args | Mean | ±Std | Min | Max | Speed | MB/s | bps |
|---|---|---|---|---|---|---|---|---|---|---|
| florence2/caption | microsoft/florence-2-base-ft | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"caption"}'` | 2.50s | 540ms | 2.13s | 3.12s | 0.40x | — | 2.95 Mbps |
| florence2/ocr | microsoft/florence-2-base-ft | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"ocr"}'` | 2.46s | 705ms | 2.03s | 3.27s | 0.41x | — | 3.00 Mbps |
| florence2/od | microsoft/florence-2-base-ft | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"od"}'` | 2.11s | 37ms | 2.09s | 2.16s | 0.47x | — | 3.49 Mbps |
| moondream/caption | vikhyatk/moondream2 | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"caption"}'` | 5.09s | 285ms | 4.88s | 5.41s | 0.20x | — | 1.45 Mbps |
| moondream/detect | vikhyatk/moondream2 | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"detect","method_params":{"object":"bench"}}'` | 3.47s | 9ms | 3.46s | 3.47s | 0.29x | — | 2.13 Mbps |
| moondream/video-caption | vikhyatk/moondream2 | `mm cat <vid> --mode fast --no-cache --format json` | `--generate.extra-body '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x336","method":"caption"}'` | 2.52s | 12ms | 2.51s | 2.54s | 100x | 11.1 | 53.11 Gbps |
| qwen/text | qwen/qwen3.5-0.8b | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'What is 2+2? Reply in one word.'` | 3.04s | 38ms | 3.00s | 3.07s | 0.33x | — | 2.43 Mbps |
| qwen/image | qwen/qwen3.5-0.8b | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'Describe this image briefly.'` | 3.66s | 73ms | 3.58s | 3.73s | 0.27x | — | 2.02 Mbps |
| qwen/multi-image | qwen/qwen3.5-0.8b | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'Compare these two images.'` | 6.73s | 477ms | 6.22s | 7.16s | 0.30x | 0.1 | 2.38 Mbps |
| qwen/video | qwen/qwen3.5-0.8b | `mm cat <vid> --mode fast --no-cache --format json` | `--prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x336"}'` | 6.27s | 511ms | 5.78s | 6.80s | 40.3x | 4.5 | 21.36 Gbps |
| rfdetr/detect | roboflow/rfdetr-nano | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"detect"}'` | 2.01s | 25ms | 1.99s | 2.04s | 0.50x | — | 3.67 Mbps |
| rfdetr-seg/segment | roboflow/rfdetr-seg-nano | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"segment"}'` | 2.19s | 142ms | 2.09s | 2.36s | 0.46x | — | 3.36 Mbps |
| vitpose/pose | usyd-community/vitpose-plus-small | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"pose"}'` | 1.98s | 54ms | 1.93s | 2.04s | 0.50x | — | 3.72 Mbps |
| sam3/segment | facebook/sam3 | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"segment","method_params":{"prompt":"soccer ball"}}'` | 2.83s | 157ms | 2.71s | 3.01s | 0.35x | — | 2.60 Mbps |
| sam3/segment_box | facebook/sam3 | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"segment_box","method_params":{"box":[50,50,400,400]}}'` | 2.72s | 93ms | 2.65s | 2.83s | 0.37x | — | 2.71 Mbps |
| sam3/track | facebook/sam3 | `mm cat <vid> --mode fast --no-cache --format json` | `--generate.extra-body '{"video_fps":2.0,"video_max_frames":30,"method":"track","method_params":{"prompt":"soccer ball","skip":1,"max_frames":30}}'` | 2.26s | 8ms | 2.25s | 2.27s | 112x | 12.4 | 59.21 Gbps |
| dots-ocr/parse_layout | rednote-hilab/dots.ocr | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"parse_layout"}'` | 3.02s | 100ms | 2.93s | 3.12s | 0.33x | — | 2.44 Mbps |
| dots-ocr/parse_layout_only | rednote-hilab/dots.ocr | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"parse_layout_only"}'` | 2.94s | 49ms | 2.90s | 2.99s | 0.34x | — | 2.50 Mbps |
| dots-ocr/ocr | rednote-hilab/dots.ocr | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"ocr"}'` | 2.86s | 117ms | 2.77s | 2.99s | 0.35x | — | 2.58 Mbps |
| dots-ocr/grounding_ocr | rednote-hilab/dots.ocr | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"grounding_ocr","method_params":{"box":[120,200,900,400]}}'` | 2.83s | 13ms | 2.82s | 2.85s | 0.35x | — | 2.60 Mbps |
| paddleocr/ocr | paddleocr/pp-ocrv5 | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"ocr"}'` | 2.04s | 76ms | 1.97s | 2.12s | 0.49x | — | 3.62 Mbps |
| paddleocr/detect | paddleocr/pp-ocrv5 | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"detect"}'` | 1.99s | 106ms | 1.90s | 2.10s | 0.50x | — | 3.71 Mbps |
| gliner/extract_entities | fastino/gliner2-multi-v1 | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'Vlm Run is hiring engineers in San Francisco.' --generate.extra-body '{"method":"extract_entities"}'` | 849ms | 10ms | 842ms | 861ms | 1.18x | — | 8.69 Mbps |
| gliner/classify_text | fastino/gliner2-multi-v1 | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'The fourth quarter earnings exceeded analyst expectations.' --generate.extra-body '{"method":"classify_text"}'` | 856ms | 11ms | 845ms | 867ms | 1.17x | — | 8.61 Mbps |
| smolvlm/256m-caption | ggml-org/smolvlm-256m-instruct-gguf | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'Describe this image briefly.'` | 2.80s | 179ms | 2.60s | 2.92s | 0.36x | — | 2.63 Mbps |
| smolvlm2/256m-image | ggml-org/smolvlm2-256m-video-instruct-gguf | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'What is in this image?'` | 2.25s | 76ms | 2.18s | 2.33s | 0.44x | — | 3.27 Mbps |
| smolvlm2/256m-video | ggml-org/smolvlm2-256m-video-instruct-gguf | `mm cat <vid> --mode fast --no-cache --format json` | `--prompt 'Summarise the video in one sentence.' --generate.extra-body '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x336"}'` | 2.28s | 11ms | 2.27s | 2.30s | 111x | 12.3 | 58.67 Gbps |
| smolvlm2/500m-image | ggml-org/smolvlm2-500m-video-instruct-gguf | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'Describe this image briefly.'` | 2.37s | 30ms | 2.33s | 2.39s | 0.42x | — | 3.11 Mbps |
| smolvlm2/500m-video | ggml-org/smolvlm2-500m-video-instruct-gguf | `mm cat <vid> --mode fast --no-cache --format json` | `--prompt 'Summarise the video in one sentence.' --generate.extra-body '{"video_fps":0.4,"video_max_frames":8,"video_resolution":"448x336"}'` | 2.51s | 65ms | 2.46s | 2.58s | 101x | 11.2 | 53.44 Gbps |

## `model+llm` (1 rows)

Cross-model pipelines: vision model output post-processed by an LLM via `extra_body.llm`.

| Name | Model | Base Command | Extra Args | Mean | ±Std | Min | Max | Speed | MB/s | bps |
|---|---|---|---|---|---|---|---|---|---|---|
| moondream/caption+llm | vikhyatk/moondream2 | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{"method":"caption","llm":"qwen/qwen3.5-0.8b"}'` | 4.75s | 56ms | 4.69s | 4.79s | 0.21x | — | 1.55 Mbps |

## `image-res` (3 rows)

Client-side image-resolution sweep on `qwen/qwen3.5-0.8b` (512 / 1024 / 1536 px).

| Name | Model | Base Command | Extra Args | Mean | ±Std | Min | Max | Speed | MB/s | bps |
|---|---|---|---|---|---|---|---|---|---|---|
| qwen/image-512 | qwen/qwen3.5-0.8b | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=512` | 3.19s | 161ms | 3.02s | 3.34s | 0.31x | — | 2.31 Mbps |
| qwen/image-1024 | qwen/qwen3.5-0.8b | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=1024` | 3.27s | 96ms | 3.16s | 3.33s | 0.31x | — | 2.25 Mbps |
| qwen/image-1536 | qwen/qwen3.5-0.8b | `mm cat <img> --mode fast --no-cache --format json` | `--prompt 'Describe the image in 1 sentence.' --encode.strategy_opts max_width=1536` | 3.28s | 113ms | 3.21s | 3.41s | 0.30x | — | 2.25 Mbps |

## `frames` (3 rows)

`video_fps` × `video_max_frames` sweep on `qwen/qwen3.5-0.8b`.

| Name | Model | Base Command | Extra Args | Mean | ±Std | Min | Max | Speed | MB/s | bps |
|---|---|---|---|---|---|---|---|---|---|---|
| qwen/video-fps=0.5-max=4 | qwen/qwen3.5-0.8b | `mm cat <vid> --mode fast --no-cache --format json` | `--prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body '{"video_fps":0.5,"video_max_frames":4}'` | 6.39s | 145ms | 6.28s | 6.55s | 39.6x | 4.4 | 20.98 Gbps |
| qwen/video-fps=1.0-max=8 | qwen/qwen3.5-0.8b | `mm cat <vid> --mode fast --no-cache --format json` | `--prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body '{"video_fps":1.0,"video_max_frames":8}'` | 6.23s | 95ms | 6.12s | 6.29s | 40.6x | 4.5 | 21.51 Gbps |
| qwen/video-fps=2.0-max=16 | qwen/qwen3.5-0.8b | `mm cat <vid> --mode fast --no-cache --format json` | `--prompt 'Summarise what happens in this video in one sentence.' --generate.extra-body '{"video_fps":2.0,"video_max_frames":16}'` | 6.11s | 254ms | 5.93s | 6.40s | 41.4x | 4.6 | 21.94 Gbps |

## `cache` (2 rows)

Cold (`--no-cache`) vs warm cache hit on the same prompt+model+file.

| Name | Model | Base Command | Extra Args | Mean | ±Std | Min | Max | Speed | MB/s | bps |
|---|---|---|---|---|---|---|---|---|---|---|
| cache/cold | qwen/qwen3.5-0.8b | `mm cat <doc> --mode fast --no-cache --format json` | `--prompt 'Summarize this document in one sentence.'` | 13.42s | 198ms | 13.24s | 13.63s | 0.07x | — | 208.06 kbps |
| cache/warm | qwen/qwen3.5-0.8b | `mm cat <doc> --mode fast --format json` | `--prompt 'Summarize this document in one sentence.'` | 130ms | 3ms | 128ms | 133ms | 7.66x | 2.6 | 21.39 Mbps |

## `404` (3 rows)

Guaranteed-unavailable model names — measures gateway 404 round-trip cost.

| Name | Model | Base Command | Mean | ±Std | Min | Max | Speed | MB/s | bps |
|---|---|---|---|---|---|---|---|---|---|
| 404/nonexistent-v0 | vlm-run/nonexistent-v0 | `mm cat <img> --mode fast --no-cache --format json` | 835ms | 33ms | 813ms | 872ms | 1.20x | — | 8.83 Mbps |
| 404/florence-2-NONEXISTENT | microsoft/florence-2-NONEXISTENT | `mm cat <img> --mode fast --no-cache --format json` | 832ms | 16ms | 815ms | 848ms | 1.20x | — | 8.87 Mbps |
| 404/paddleocr-v999 | paddlepaddle/paddleocr-v999 | `mm cat <img> --mode fast --no-cache --format json` | 826ms | 13ms | 811ms | 835ms | 1.21x | — | 8.93 Mbps |

## `validation` (2 rows)

CLI-side `--generate.extra-body` rejection paths (bad / non-object JSON).

| Name | Model | Base Command | Extra Args | Mean | ±Std | Min | Max | Speed | MB/s | bps |
|---|---|---|---|---|---|---|---|---|---|---|
| validation/bad-json | (default) | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '{not json}'` | 79ms | 1ms | 78ms | 80ms | 12.7x | 0.5 | 93.59 Mbps |
| validation/non-object-json | (default) | `mm cat <img> --mode fast --no-cache --format json` | `--generate.extra-body '[1,2,3]'` | 80ms | 2ms | 78ms | 83ms | 12.5x | 0.5 | 92.01 Mbps |

## Summary — median latency by group

| Group | Rows | Median Mean | Min Mean | Max Mean |
|---|---:|---:|---:|---:|
| `noop` | 3 | 887ms | 886ms | 937ms |
| `model` | 29 | 2.51s | 849ms | 6.73s |
| `model+llm` | 1 | 4.75s | 4.75s | 4.75s |
| `image-res` | 3 | 3.27s | 3.19s | 3.28s |
| `frames` | 3 | 6.23s | 6.11s | 6.39s |
| `cache` | 2 | 13.42s | 130ms | 13.42s |
| `404` | 3 | 832ms | 826ms | 835ms |
| `validation` | 2 | 80ms | 79ms | 80ms |

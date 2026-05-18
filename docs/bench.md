# mm bench

Benchmark all subcommands with statistical analysis — measure latency, throughput, and LLM token usage across the full command matrix.

## Synopsis

```bash
mm bench [DIRECTORY] [OPTIONS]
```

`DIRECTORY` defaults to `.` (current directory).

## Options

| Flag | Short | Type | Description |
|------|-------|------|-------------|
| `--rounds N` | `-r` | int | Number of measurement rounds (default: 3) |
| `--warmup N` | `-w` | int | Number of warmup rounds before timing (default: 1) |
| `--mode MODE` | `-m` | enum | Groups to include: `metadata` (default), `fast`, `accurate`, `all` |
| `--command SUBSTR` | `-c` | string | Substring filter on benchmark names (e.g. `cat`) |
| `--group NAME` | `-g` | string | Exact group name filter (case-insensitive) |
| `--model MODEL` | | string | Filter to rows whose `model` tag matches this value |
| `--task TASK` | | string | Filter to rows whose `task` tag matches this value |
| `--format FORMAT` | `-f` | enum | Output format: `rich` (default), `json`, `tsv`, `csv`, `stdout` |
| `--bench-file PATH` | `-b` | path | External Python benchfile that replaces the built-in command set |
| `--dry-run` | | flag | Resolve the benchmark plan without executing commands |
| `--host-info` | | flag | Print host system info and exit |
| `--timeout SECONDS` | | float | Per-command timeout for stdout snapshot mode (default: 600s) |
| `--with-generate` | | flag | Stdout snapshot mode: include the LLM generate step |

## Benchmark modes

The `--mode` flag selects which command groups to run:

| Mode | Groups included | Use case |
|------|----------------|----------|
| `metadata` (default) | `overhead` + `metadata` | Fast, no LLM required — Unix-comparable baseline |
| `fast` | `overhead` + `metadata` + fast pipelines | Encoder performance including short LLM calls |
| `accurate` | `overhead` + `metadata` + accurate pipelines | Full LLM pipeline benchmarks |
| `all` | All groups | Complete suite |

## Output metrics

Each benchmark row reports:

| Metric | Description |
|--------|-------------|
| `mean_ms` | Mean latency in milliseconds |
| `std_ms` | Standard deviation across rounds |
| `min_ms` | Minimum observed latency |
| `max_ms` | Maximum observed latency |
| `median_ms` | Median latency |
| `speed` | Realtime multiplier (Nx). For audio/video: media duration ÷ processing time. For files: files/second. |
| `mb_per_sec` | Throughput in MB/s |
| `bits_per_sec` | Uncompressed throughput in bits/s. Images/video: width × height × 24 bits × fps × duration. Other: file size × 8. |
| `prompt_tokens` | LLM prompt tokens consumed (accurate mode only) |
| `completion_tokens` | LLM completion tokens (accurate mode only) |

Latency values are color-coded in rich output: **green** = fast, **yellow** = acceptable, **red** = slow. Thresholds differ by group (`overhead` < `metadata` < `fast` < `accurate`).

## Filtering

Multiple filters combine with AND:

```bash
# only cat benchmarks
mm bench ~/data --command cat

# only metadata group
mm bench ~/data --group metadata

# only rows tagged with model=qwen3.5-0.8b
mm bench ~/data -b commands.py --model qwen3.5-0.8b

# only OCR task rows
mm bench ~/data -b commands.py --task ocr

# model AND task together
mm bench ~/data -b commands.py --task cap --model facebook/sam3
```

Conventional `task` tag values: `cap`, `ocr`, `det`, `seg`, `llm`, `pose`, `track`, `noop`.

## Examples

```bash
# overhead + metadata (no LLM)
mm bench ~/data

# only metadata group (Unix-comparable subset)
mm bench ~/data --mode metadata

# overhead + metadata + accurate (LLM required)
mm bench ~/data --mode accurate

# full suite
mm bench ~/data --mode all

# more rounds for statistical stability
mm bench ~/data --rounds 5

# no warmup
mm bench ~/data --warmup 0

# JSON output for archival
mm bench ~/data --format json

# TSV for spreadsheet import
mm bench ~/data --format tsv

# resolve the plan without running commands
mm bench ~/data --dry-run

# host system info only
mm bench --host-info
mm bench --host-info --format json
```

## Saving results

After each run, save results to the `benchmarks/` directory:

```bash
# full JSON output
mm bench ~/data/mmbench-mini --format json --rounds 3 > benchmarks/mm-bench-$(date +%Y%m%d).json

# TSV for spreadsheet import
mm bench ~/data/mmbench-mini --format tsv --rounds 3 > benchmarks/mm-bench-$(date +%Y%m%d).tsv
```

Naming convention: `mm-bench-YYYYMMDD` (e.g. `mm-bench-20260518`).

## External benchfiles

`--bench-file` loads a `.py` module that fully replaces the built-in command matrix. The module must expose one of:

- `COMMANDS: list[BenchCommand]` — static list of commands
- `def commands(files) -> list[BenchCommand]` — factory that receives the pre-scanned file list

`--mode` is ignored when a benchfile is provided; the `BenchCommand.group` field drives display grouping. Filters (`--group`, `--model`, `--task`, `--command`) still apply on top.

```bash
# load an external benchfile
mm bench ~/data -b benchmarks/vlmgw_bench_commands.py

# dry-run to inspect before running
mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --dry-run

# one round, no warmup (fast iteration)
mm bench ~/data -b benchmarks/vlmgw_bench_commands.py -r 1 -w 0

# filter by group from the benchfile
mm bench ~/data -b benchmarks/vlmgw_bench_commands.py --group cache
```

**`BenchCommand` structure:**

```python
from mm.commands.bench_commands import BenchCommand

COMMANDS = [
    BenchCommand(
        name="my-test",
        group="fast",
        cmd_template="mm cat {file} -m fast",
        requires_kind="image",
        tags={"model": "qwen3-vl:8b", "task": "cap"},
    )
]
```

| Field | Description |
|-------|-------------|
| `name` | Display name shown in the bench table |
| `group` | Group bucket: `overhead`, `metadata`, `fast`, `accurate`, or custom |
| `cmd_template` | Shell command template. Placeholders: `{file}`, `{files}`, `{dir}` |
| `requires_kind` | Kind of file to substitute: `image`, `video`, `audio`, `document`, `code` |
| `tags` | Arbitrary key-value tags for filtering (`model`, `task`, etc.) |
| `skip_reason` | Message shown when the command is skipped (no matching files) |
| `disabled` | If true, row is rendered but never executed |

## Stdout snapshot mode

`--format stdout` runs each `mm cat` command and captures output to a markdown snapshot file. Used to record expected encoder output for regression testing.

```bash
mm bench ~/data --command cat --format stdout > tests/stdout/cat.md
```

By default the LLM generate step is skipped (`--no-generate`) so snapshots are fast, deterministic, and offline-friendly. Pass `--with-generate` to include the LLM call:

```bash
mm bench ~/data --command cat --format stdout --with-generate
```

## Host information

`--host-info` prints the host system specification (CPU, RAM, OS, Python version, mm version) without running any benchmarks:

```bash
mm bench --host-info
mm bench --host-info --format json
```

This is useful for attaching system context to archived benchmark results.

## Notes

- `mm cat` invocations within bench always run with `--no-cache` to ensure measurements reflect actual extraction time, not cache reads.
- Warmup rounds run first and are discarded; only `--rounds` timed iterations contribute to statistics.
- Skipped rows (no matching files for the required kind) appear in rich output but are omitted from TSV/CSV.
- Disabled rows (`BenchCommand.disabled = True`) are rendered dimmed in dry-run and live tables to keep matrix coverage visible, but are never executed.
- `stdin` is closed for all subprocess invocations to prevent `mm cat`'s stdin pipe detection from deadlocking.
- Results saved to `benchmarks/` are tracked in `CHANGELOG.md` when they change performance numbers.

---
name: explore-mm-cli
description: Exercise the mm CLI end-to-end against ~/data/mmbench-tiny/, using docs/FIXTURES.md as the menu of options, and log every command + output to a dated mm-YYMMDD-output.txt file at the repo root. Use when the user asks to "explore mm", smoke-test the CLI surface, or regenerate the exploration log.
---

# Explore mm CLI

Systematic walkthrough of the `mm` CLI surface. The goal is coverage and a reproducible artifact, not deep analysis.

## Inputs

- **Dataset**: `~/data/mmbench-tiny/` (9 files, ~43 MB — images, PDFs, audio, video). Use this for every experiment unless a command needs a different target.
- **Reference**: `docs/FIXTURES.md` — canonical list of fixture commands and options. Read it first, then pick representative invocations from each section.
- **Binary**: always `uv run mm ...` (never bare `mm`).

## What to run

Cover each top-level command at least once, biasing toward flags shown in FIXTURES.md:

- `find` — default table, `--tree --depth 1`, `--schema`, `--columns`, `--kind`, `--name`, `--min-size --sort --reverse`, `--no-ignore`, `--format json`
- `wc` — default totals, `--by-kind`, `--kind <k> --format json`
- `cat` — one image, one video, one PDF with `-n`, one audio. Note that `cat` without `-m fast` may trigger accurate-mode pipelines against the active profile; that's expected coverage, not a bug.
- `grep` — a literal term scoped by `--kind document`, `-i` (case-insensitive)
- `sql` — at minimum `--list-tables`. Ad-hoc `SELECT ... FROM files --dir <path>` needs `--pre-index` on an unindexed directory; mention this in the log rather than fighting it.
- `profile list`, `config show`

Pipe composability: try one `mm find ... | mm wc` to exercise stdin chaining. If stdin paths don't propagate, record the observation — don't debug.

## Execution

- Batch independent commands into parallel Bash calls. Most `mm` subcommands finish in <200ms; `cat` on media is slower (seconds).
- Don't re-run commands that succeeded. If one errors, retry once individually, then move on.
- Capture stdout+stderr (`2>&1`) so the log reflects what the user would see.

## Logging

Write a single file at the repo root: `mm-YYMMDD-output.txt` (e.g. `mm-260413-output.txt` for 2026-04-13). Use the current date from the environment — do not hardcode.

### Required structure

Exact layout, in order:

1. **Header** (2 lines, no banner):
   ```
   mm CLI exploration — YYYY-MM-DD
   Dataset: ~/data/mmbench-tiny/ (9 files, 43.1 MB)
   ```

2. **Command entries** — one per invocation, in this order:
   - `ls ~/data/mmbench-tiny/`
   - `uv run mm --help`
   - `wc` variants (default, `--by-kind`, `--kind document --format json`)
   - `find` variants (default, `--tree --depth 1`, `--schema`, `--kind image --columns name,kind,size,ext`, `--kind video --format json`, `--kind image --format json`, `--min-size 1mb --sort size --reverse`, `--name "invoice"`)
   - `cat` variants (image, video, PDF with `-n 20`, second PDF with `-n 10`, audio transcript)
   - `grep "<term>" ... --kind document`
   - `sql` ad-hoc SELECT (note the pre-index caveat), `sql --list-tables`
   - `profile list`, `config show`
   - One pipe: `mm find ... | mm wc`

3. **Trailing sections** — two fenced headers at the bottom:
   ```
   ================================================================
   Summary of features exercised
   ================================================================
   - find: <flags covered>
   - wc:   <flags covered>
   - cat:  <file types covered>
   - grep: ...
   - sql:  ...
   - profile list, config show

   Observations
   - <surprising finding 1>
   - <surprising finding 2>
   ```

### Entry format

Each command uses a 64-char `=` delimiter above and below the command line, with raw output following:

```
================================================================
$ <exact command>
================================================================
<stdout/stderr, preserving the trailing timing line like "48ms" or
 "2.6s • 38.2 KB • 14.5 KB/s" that mm prints>
```

Rules for the output body:
- Preserve `mm`'s trailing metrics line (e.g. `48ms`, `2.6s • 38.2 KB • 14.5 KB/s`) — it's part of the signal.
- Trim verbose JSON arrays to an elided form like `[{...name 640x480 size...}, ...]` only when full output would bloat the file past readability. Tables and tree output are kept verbatim.
- For commands that failed or behaved unexpectedly (e.g. `sql` without `--pre-index`, `find | wc` pipe), replace the output with a parenthetical `(NOTE: ...)` explaining what happened instead of fighting it.
- Keep one blank line between entries.

Keep the log self-contained — a reader should be able to reproduce every command without seeing the conversation. Match the shape of `260413-output.txt` as the canonical reference.

## Final reply to the user

Two or three sentences: what was covered, where the log lives, and any notable findings. No bullet-by-bullet command recap — the log is the artifact.

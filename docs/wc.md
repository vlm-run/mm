# mm wc

Count files, bytes, estimated lines, and estimated tokens across a directory — like `wc` scaled up for LLM context budgeting.

## Synopsis

```bash
mm wc [DIRECTORY] [OPTIONS]
```

`DIRECTORY` defaults to `.` (current directory).

## Options

| Flag | Short | Type | Description |
|------|-------|------|-------------|
| `--kind KINDS` | `-k` | string | Filter by kind. Comma-separated. e.g. `code,text` |
| `--by-kind` | | flag | Break down metrics by file kind |
| `--format FORMAT` | `-f` | enum | Output format: `rich`, `tsv`, `csv`, `json` |

## Output metrics

| Metric | Description |
|--------|-------------|
| `files` | Total file count |
| `size` | Total disk usage (formatted: KB / MB / GB) |
| `lines (est.)` | Estimated line count for text/code/document files |
| `tokens (est.)` | Estimated token count (characters ÷ 4) |
| `tok_per_mb` | Token density: tokens per megabyte |

When `--by-kind` is active (or automatically activated when multiple kinds are present), an additional per-kind breakdown table is shown with a totals row.

For `image` files, `tok_per_img` (tokens per image) is also computed per-kind.

## Token estimation

Tokens are estimated using a character-to-token ratio of **4 characters per token** — a standard approximation for English text with typical tokenizers.

- **Text / code files**: full content read, character count ÷ 4
- **PDF documents**: text extracted via pypdfium2, then character count ÷ 4
- **Binary files (image, video, audio)**: 0 lines, 0 tokens — binary content is not text

## Examples

```bash
# summary panel for current directory
mm wc

# summary for a specific directory
mm wc ~/project

# code files only
mm wc ~/project --kind code

# images and video breakdown
mm wc ~/media --kind image,video --by-kind

# explicit breakdown by kind
mm wc ~/data --by-kind

# JSON output for scripting
mm wc ~/data --format json

# TSV for spreadsheet import
mm wc ~/data --by-kind --format tsv
```

## Pipe support

`mm wc` reads file paths from stdin when piped, computing stats only for those files:

```bash
# count tokens in files found by find
mm find ~/project --kind code | mm wc

# count tokens in specific PDF files
mm find ~/data --ext .pdf | mm wc

# compare token counts before and after filtering
mm find ~/data | mm wc
mm find ~/data --kind code | mm wc
```

## Auto-breakdown

When multiple file kinds are present in the scanned directory, `--by-kind` is enabled automatically — no flag needed. Pass `--kind` to filter to a single kind and suppress the per-kind table.

## Notes

- Document line counts are extracted from pypdfium2 text output, not page count.
- `tok_per_mb` is omitted (`—`) when a kind has zero bytes on disk.
- The Rust scanner handles all kinds except documents; PDF text extraction runs in Python via pypdfium2 and is overlaid onto the Rust results.

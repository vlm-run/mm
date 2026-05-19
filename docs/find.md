# mm find

List and filter files from a directory with rich metadata — like `fd` or `find`, but kind-aware and Arrow-backed.

## Synopsis

```bash
mm find [DIRECTORY] [OPTIONS]
```

`DIRECTORY` defaults to `.` (current directory).

## Modes

`find` operates in three modes selected by flags:

| Mode | Flag | Description |
|------|------|-------------|
| Table | *(default)* | Tabular listing with metadata columns |
| Tree | `--tree` | Hierarchical directory tree with file counts and sizes |
| Schema | `--schema` | Column names, Arrow types, descriptions, and sample values |

## Options

### Filtering

| Flag | Short | Type | Description |
|------|-------|------|-------------|
| `--name PATTERN` | `-n` | string | Filter by filename. Accepts a substring or regex. |
| `--ignore-case` | `-i` | flag | Case-insensitive `--name` matching. Requires `--name`. |
| `--kind KINDS` | `-k` | string | Filter by kind. Comma-separated. e.g. `image,document` |
| `--ext EXTS` | `-e` | string | Filter by extension. Comma-separated. e.g. `.pdf,.docx` |
| `--min-size SIZE` | | string | Minimum file size. e.g. `1kb`, `2.5mb`, `1gb` |
| `--max-size SIZE` | | string | Maximum file size. |
| `--depth N` | `-d` | int | Maximum directory depth (0 = top-level only). |
| `--no-ignore` | | flag | Include files excluded by `.gitignore`. |

### Display

| Flag | Short | Type | Description |
|------|-------|------|-------------|
| `--columns COLS` | `-c` | string | Comma-separated column names to display. |
| `--sort COL` | `-s` | string | Sort by column name (e.g. `size`, `name`, `modified`). |
| `--reverse` | `-r` | flag | Reverse sort order. |
| `--limit N` | | int | Maximum number of results to show. |
| `--tree` | | flag | Switch to hierarchical tree view. |
| `--size` | | flag | Show sizes in tree view (default: on). |
| `--schema` | | flag | Show column schema instead of file listing. |
| `--format FORMAT` | `-f` | enum | Output format: `rich`, `tsv`, `csv`, `json`, `dataset-jsonl`, `dataset-hf`. |

### Sessions and refs

| Flag | Type | Description |
|------|------|-------------|
| `--session ID` | string | Tag results with a session ID (enables `<session>/<ref_id>` refs). |
| `--refs` | flag | Include `ref_id` column. Requires `--session`. |

## Columns

These columns are available in table mode. Default display shows `path`, `kind`, `size`, `ext` — plus `width` and `height` when any media files have dimensions.

| Column | Type | Description |
|--------|------|-------------|
| `path` | string | Relative path from the scanned root |
| `name` | string | Filename with extension |
| `stem` | string | Filename without extension |
| `ext` | string | Extension including dot (`.png`, `.pdf`) |
| `size` | int64 | File size in bytes |
| `modified` | timestamp | Last modification timestamp (UTC) |
| `created` | timestamp | Creation timestamp (UTC) |
| `mime` | string | MIME type inferred from extension |
| `kind` | string | Semantic kind: `image`, `video`, `document`, `code`, `audio`, `data`, `config`, `text`, `other` |
| `is_binary` | bool | True if the file is binary content |
| `depth` | int | Directory depth from scan root (0 = top-level) |
| `parent` | string | Parent directory name |
| `width` | int | Pixel width (images from header, video via ffprobe). Null for non-media. |
| `height` | int | Pixel height. Null for non-media. |

Use `mm find DIR --schema` to see all columns with types and sample values for a given directory.

## Examples

### Basic listing

```bash
# list all files in current directory
mm find

# list files in a specific directory
mm find ~/data

# include gitignored files
mm find ~/data --no-ignore
```

### Filtering by kind and extension

```bash
# images only
mm find ~/data --kind image

# images and documents
mm find ~/data --kind image,document

# PDF and DOCX files sorted by size descending
mm find ~/data --ext .pdf,.docx --sort size --reverse

# videos larger than 100MB
mm find ~/data --kind video --min-size 100mb --sort size -r
```

### Name filtering

```bash
# substring match
mm find ~/project -n config

# regex match
mm find ~/data --name "test_.*\.py"

# case-insensitive match
mm find ~/data -n README -i
```

### Column selection and limits

```bash
# show specific columns
mm find ~/data --columns name,kind,size,modified

# top 20 largest files
mm find ~/data --sort size --reverse --limit 20

# just file paths (for piping)
mm find ~/data --columns path --format tsv
```

### Tree view

```bash
# full tree
mm find ~/data --tree

# tree limited to 2 levels deep
mm find ~/data --tree --depth 2

# tree showing only video files
mm find ~/data --tree --kind video

# tree without sizes
mm find ~/data --tree --no-size
```

### Schema introspection

```bash
# show all available columns with types and sample values
mm find ~/data --schema

# schema as JSON
mm find ~/data --schema --format json
```

### Machine-readable output

```bash
# TSV for scripting
mm find ~/data --format tsv

# JSON
mm find ~/data --kind image --format json

# pipe into jq
mm find ~/data --format json | jq '.[] | select(.size > 1048576) | .name'
```

### Composing with other mm commands

```bash
# count files found
mm find ~/data --kind document | mm wc

# cat all PDFs in a directory
mm find ~/data --ext .pdf | mm cat -m accurate

# grep only within code files
mm find ~/project --kind code | mm grep "def main"
```

## Notes

- `--name` accepts both plain substrings and regular expressions. If the pattern fails to compile as a regex, it falls back to substring matching.
- `--ignore-case` requires `--name` to be set; passing it alone is an error.
- `--refs` requires `--session`; the `ref_id` column is opt-in and hidden by default.
- In tree mode, when a directory contains more than 500 files and `--depth` is not set, depth is automatically capped at 1 to avoid overwhelming output. A note is shown indicating the cap.
- The fast path for non-rich, non-piped output (TSV/CSV/JSON without `--columns`) bypasses Python entirely and uses Rust's `to_json_fast` — this is the fastest route for scripting.

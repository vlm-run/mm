# mm grep

Search file contents with regex, full-text search, and semantic vector search — like `rg` or `grep`, but kind-aware and media-capable.

## Synopsis

```bash
mm grep PATTERN [DIRECTORY] [OPTIONS]
```

`PATTERN` is a regular expression. `DIRECTORY` defaults to `.` (current directory).

## Options

| Flag | Short | Type | Description |
|------|-------|------|-------------|
| `--kind KINDS` | `-k` | string | Filter by file kind. Comma-separated. e.g. `code,document` |
| `--ext EXTS` | `-e` | string | Filter by extension. Comma-separated. e.g. `.py,.rs` |
| `-C N` | | int | Show N lines of context around each match |
| `--count` | `-c` | flag | Show only match counts per file, not the matching lines |
| `--semantic` | `-s` | flag | Run semantic (vector) search alongside text search |
| `--pre-index` | | flag | Index unindexed files before semantic search (max 50 per run) |
| `--ignore-case` | `-i` | flag | Force case-insensitive matching |
| `--no-ignore` | | flag | Include files excluded by `.gitignore` |
| `--format FORMAT` | `-f` | enum | Output format: `rich`, `json`, `tsv`, `csv`, `dataset-jsonl`, `dataset-hf` |

## Search modes

`grep` combines three search strategies in a single invocation:

| Mode | Trigger | Scope |
|------|---------|-------|
| **Regex** | Always active | Text files and extracted document text |
| **FTS** | Always active (silent on empty index) | Indexed chunks in SQLite FTS5 |
| **Semantic** | `--semantic` / `-s` | Embedded vector chunks (images, video, audio, PDFs) |

Results from all three are merged and deduplicated before output.

## Smart-case matching

When `-i` is not passed, `grep` applies smart-case logic:

- Pattern contains **no uppercase letters** → case-insensitive match
- Pattern contains **any uppercase letter** → case-sensitive match

This matches the behavior of `ripgrep` and `vim`. Passing `-i` always forces case-insensitive matching regardless of pattern.

## File type handling

`grep` reads content based on file kind:

| Kind | How content is read |
|------|---------------------|
| `code`, `text`, `config`, `data` | Raw UTF-8 text |
| `document` (PDF, DOCX, etc.) | Extracted text via local document parser |
| `image`, `video`, `audio` | Binary — skipped for regex; searchable via FTS/semantic if indexed |

## Exit codes

`grep` follows standard Unix `grep` convention:

- `0` — one or more matches found
- `1` — no matches found

This makes it safe to use in conditionals and pipes:

```bash
mm grep "TODO" ~/src && echo "Found TODOs"
```

## Examples

```bash
# search all files in current directory
mm grep "TODO"

# search a specific directory
mm grep "import.*torch" ~/project

# code files only
mm grep "def main" ~/src --kind code

# search PDF text content
mm grep "attention" ~/papers --ext .pdf

# context lines around each match
mm grep "error|warn" ~/logs -C 2

# count matches per file
mm grep "TODO" ~/src --count

# case-insensitive (forced)
mm grep "quantum" ~/docs -i

# include gitignored files
mm grep "secret" ~/repo --no-ignore

# semantic search over indexed media
mm grep "Quantum Phase Transition" ~/data -s

# index unindexed files first, then semantic search
mm grep "protein folding" ~/papers -s --pre-index

# pipe from find
mm find ~/project --kind code | mm grep "deprecated"

# JSON output
mm grep "TODO" ~/src --kind code --format json
```

## Output format

### Rich (default in TTY)

Grouped by file, with matched text highlighted in bold. A summary line follows all matches:

```
main.py
    42  def main() -> None:
    87  if __name__ == "__main__":

utils.py
   113  # main entry point

3 matches in 2 files
```

### Non-rich (TSV/pipe default)

```
path/to/file.py:42:    def main() -> None:
path/to/file.py:87:    if __name__ == "__main__":
```

Format: `path:line_number:line_content`.

## Semantic search

When `--semantic` is active:

1. Vector embeddings are looked up in the `chunks_vec` SQLite-vec table.
2. Files must be indexed (`mm grep -s --pre-index`) for semantic results to appear.
3. Binary files (images, video, audio, PDFs) are searchable semantically even though regex cannot match them.
4. Up to 5 semantic results are returned per search.

`--pre-index` runs the fast-mode pipeline on unindexed files before searching, indexing at most 50 files per invocation.

## Notes

- Results from FTS and semantic search are deduplicated against regex matches using `(path, chunk_index)` as the key.
- The FTS search runs silently — no error is raised if the FTS5 index is empty or missing.
- `--count` with `--format json` emits `{"path": ..., "count": ...}` records; with `rich` it shows a sorted table.
- Regex compilation errors print to stderr and exit with code 1.

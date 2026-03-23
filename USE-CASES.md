Documents
 - Find where in the document "a specific term" is mentioned

## Benchmark commands (`vlmctx bench`)

Each benchmark is a real CLI invocation measured end-to-end via subprocess.

### L0 — Metadata (directory-level)

| Name | Command |
|------|---------|
| `vlmctx find .` | `vlmctx find {dir} --format json` |
| `vlmctx find . (table)` | `vlmctx find {dir} --format tsv` |
| `vlmctx wc .` | `vlmctx wc {dir} --format json` |
| `vlmctx sql 'GROUP BY kind'` | `vlmctx sql 'SELECT kind, COUNT(*) ...' --dir {dir} --format json` |
| `vlmctx sql 'SUM(size) BY kind'` | `vlmctx sql 'SELECT kind, COUNT(*), SUM(size), AVG(size) ...' --dir {dir} --format json` |
| `vlmctx sql 'TOP 10 largest'` | `vlmctx sql 'SELECT name, kind, size ... LIMIT 10' --dir {dir} --format json` |
| `vlmctx sql 'GROUP BY ext'` | `vlmctx sql 'SELECT ext, COUNT(*), SUM(size) ...' --dir {dir} --format json` |
| `vlmctx find --kind image` | `vlmctx find {dir} --kind image --format json` |
| `vlmctx find --kind audio` | `vlmctx find {dir} --kind audio --format json` (skipped if no audio) |
| `vlmctx find --kind document` | `vlmctx find {dir} --kind document --format json` (skipped if no documents) |

### L1 — Content extraction (file-level)

| Name | Command | Selection |
|------|---------|-----------|
| `vlmctx cat <code> (x20)` | `vlmctx cat {files} --format json` | first 20 code files |
| `vlmctx cat <image>` | `vlmctx cat {file} --format json` | first image |
| `vlmctx cat <image> (x20)` | `vlmctx cat {files} --format json` | first 20 images |
| `vlmctx cat <audio>` | `vlmctx cat {file} --format json` | first audio |
| `vlmctx cat <video>` | `vlmctx cat {file} --format json` | first video |
| `vlmctx cat <pdf>` | `vlmctx cat {file} --format json` | first document |
| `vlmctx cat <pdf> (x10)` | `vlmctx cat {files} --format json` | first 10 documents |
| `vlmctx grep /pattern/` | `vlmctx grep 'import\|include\|require' {dir} --format json` | all text files |

### L2 — Semantic (LLM-powered)

| Name | Command | Selection |
|------|---------|-----------|
| `vlmctx cat <image> -l2 --mode fast` | `vlmctx cat {file} -l 2 --mode fast --format json` | first image |
| `vlmctx cat <image> -l2 --mode accurate` | `vlmctx cat {file} -l 2 --mode accurate --format json` | first image |
| `vlmctx cat <video> -l2 --mode fast` | `vlmctx cat {file} -l 2 --mode fast --format json` | first video |
| `vlmctx cat <audio> -l2 --mode fast` | `vlmctx cat {file} -l 2 --mode fast --format json` | smallest audio |

### Placeholders

- `{dir}` — resolved absolute directory path
- `{file}` — single file auto-picked by kind (first match, or smallest for audio L2)
- `{files}` — space-separated list of files (batch commands, up to N)

Commands are skipped when the required file kind is absent from the target directory.

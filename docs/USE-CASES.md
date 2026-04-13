Documents
 - Find where in the document "a specific term" is mentioned

## Benchmark commands (`mm bench`)

Each benchmark is a real CLI invocation measured end-to-end via subprocess.

### Metadata scan (directory-level)

| Name | Command |
|------|---------|
| `mm find .` | `mm find {dir} --format json` |
| `mm find . (table)` | `mm find {dir} --format tsv` |
| `mm wc .` | `mm wc {dir} --format json` |
| `mm sql 'GROUP BY kind'` | `mm sql 'SELECT kind, COUNT(*) ...' --dir {dir} --format json` |
| `mm sql 'SUM(size) BY kind'` | `mm sql 'SELECT kind, COUNT(*), SUM(size), AVG(size) ...' --dir {dir} --format json` |
| `mm sql 'TOP 10 largest'` | `mm sql 'SELECT name, kind, size ... LIMIT 10' --dir {dir} --format json` |
| `mm sql 'GROUP BY ext'` | `mm sql 'SELECT ext, COUNT(*), SUM(size) ...' --dir {dir} --format json` |
| `mm find --kind image` | `mm find {dir} --kind image --format json` |
| `mm find --kind audio` | `mm find {dir} --kind audio --format json` (skipped if no audio) |
| `mm find --kind document` | `mm find {dir} --kind document --format json` (skipped if no documents) |

### Fast mode — content extraction (file-level)

| Name | Command | Selection |
|------|---------|-----------|
| `mm cat <code> (x20)` | `mm cat {files} --format json` | first 20 code files |
| `mm cat <image>` | `mm cat {file} --format json` | first image |
| `mm cat <image> (x20)` | `mm cat {files} --format json` | first 20 images |
| `mm cat <audio>` | `mm cat {file} --format json` | first audio |
| `mm cat <video>` | `mm cat {file} --format json` | first video |
| `mm cat <pdf>` | `mm cat {file} --format json` | first document |
| `mm cat <pdf> (x10)` | `mm cat {files} --format json` | first 10 documents |
| `mm grep /pattern/` | `mm grep 'import\|include\|require' {dir} --format json` | all text files |

### Accurate mode (LLM pipelines)

| Name | Command | Selection |
|------|---------|-----------|
| `mm cat <image> --mode fast` | `mm cat {file} --mode fast --format json` | first image |
| `mm cat <image> --mode accurate` | `mm cat {file} --mode accurate --format json` | first image |
| `mm cat <video> --mode fast` | `mm cat {file} --mode fast --format json` | first video |
| `mm cat <audio> --mode fast` | `mm cat {file} --mode fast --format json` | smallest audio |

### Placeholders

- `{dir}` — resolved absolute directory path
- `{file}` — single file auto-picked by kind (first match, or smallest for accurate-mode audio)
- `{files}` — space-separated list of files (batch commands, up to N)

Commands are skipped when the required file kind is absent from the target directory.

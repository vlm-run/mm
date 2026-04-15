# `mm` Fixtures and Examples

This document combines the reproducible fixture commands used by `mm bench`
with real example outputs across the CLI surface.

## Datasets

The fixture commands below assume one of these datasets is on disk:

- [mmbench-tiny](https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz) — 5 files, 42.4 MB
- [mmbench-mini](https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-mini.tar.gz) — 44 files, 1.3 GB

Every command supports `--format` for output control:

- **`rich`** (default in TTY) — formatted tables, panels, syntax highlighting
- **`tsv`** (default when piped) — tab-separated, no ANSI, maximum token efficiency
- **`csv`** — comma-separated, spreadsheet-friendly
- **`json`** — structured JSON (compact when piped, pretty in TTY)

---

## Fixture commands

### Image

```bash
# Extract images quickly (local encode, no LLM)
uv run mm cat input.png
# Multi-image extraction (batch=auto)
uv run mm cat images/*.png
# Extract images accurately (with VLMs)
uv run mm cat input.png -m accurate
# Custom image tiling (for extra-large resolution images)
uv run mm cat input.png --encode.strategy image-tile
# Custom image resizing (for smaller resolution images)
uv run mm cat input.png --encode.strategy image-resize -m accurate
# With verbose output (shows pipeline steps and token usage)
uv run mm cat input.png -v
```

### Document

```bash
# Extract PDF documents quickly
uv run mm cat input.pdf
# Extract multiple PDF documents quickly (batch=auto)
uv run mm cat *.pdf
# Extract PDF documents accurately (batched VLM inference, each page rasterized)
uv run mm cat input.pdf -m accurate
# Extract non-PDF documents accurately (single VLM inference, batch=1)
uv run mm cat input.docx -m accurate
# Extract per-page text only (no rasterization, no VLM)
uv run mm cat input.pdf --encode.strategy document-page-text
# Rasterize pages and interleave extracted text (hybrid, batch=auto)
uv run mm cat input.pdf --encode.strategy document-rasterize-text -m accurate
# With verbose output (shows pipeline steps and token usage)
uv run mm cat input.pdf -v
```

### Audio

```bash
# Extract audio quickly (Whisper transcript, default model=medium)
uv run mm cat input.mp3
# Extract audio accurately (Whisper transcript + LLM summary)
uv run mm cat input.mp3 -m accurate
# Extract audio accurately (pass audio directly to a Gemini-compatible VLM)
uv run mm cat input.mp3 --encode.strategy audio-gemini -m accurate
# With verbose output (shows pipeline steps and token usage)
uv run mm cat input.mp3 -v
```

### Video

```bash
# Extract video quickly (mosaic grids)
uv run mm cat input.mp4
# Extract video accurately (mosaic + whisper + VLM)
uv run mm cat input.mp4 -m accurate
# Extract video accurately (frame-sample encoder at fps=1)
uv run mm cat input.mp4 --encode.strategy video-frame-sample -m accurate
```

---

## `wc` — Token-aware counting

### Summary

```bash
$ mm wc ~/data/domains
```

```
files  size     lines (est.)  tokens (est.)
702    7.2 GB   52.9M         1.50B
```

### Breakdown by kind

```bash
$ mm wc ~/data/domains --by-kind
```

```
files  size     lines (est.)  tokens (est.)
702    7.2 GB   52.9M         1.50B

kind      files  size       lines (est.)  tokens (est.)
audio     2      570.5 MB   0             149.6M
document  545    3.9 GB     52.9M         792.9M
image     134    65.4 MB    0             231.0K
other     10     2.2 GB     0             585.0M
video     7      1.6 GB     0             595
```

### Filter to a single kind (JSON)

```bash
$ mm wc ~/data/domains --kind document --format json
```

```json
{
  "files": 545,
  "size": 3171525381,
  "lines (est.)": 52858497,
  "tokens (est.)": 792881131
}
```

---

## `find` — Structured file discovery

### Tabular listing

```bash
$ mm find ~/data/domains --kind video --columns name,kind,size,ext
```

```
name                                kind   size        ext
video-walkthrough-healthcare.mp4    video  56220815    .mp4
google_next_2025_keynote.mp4        video  511043010   .mp4
gooogle_gemini_intro video.mp4      video  11023464    .mp4
how_to_build_an_mvp.mp4             video  37341183    .mp4
bakery.mp4                          video  29346272    .mp4
```

### Tree view

```bash
$ mm find ~/data/domains --tree --depth 1
```

```
/Users/sudeep/data/domains  (702 files, 7.2 GB)
├── audio/  (2 files, 479.3 MB)
├── construction/  (532 files, 5.0 GB)
├── document-markdown/  (8 files, 10.6 MB)
├── document.invoice/  (6 files, 1.3 MB)
├── document.layout/  (12 files, 6.0 MB)
├── healthcare/  (22 files, 63.6 MB)
├── image.agent/  (51 files, 31.7 MB)
├── image.object-detection/  (23 files, 16.8 MB)
└── video.transcription/  (5 files, 1.0 GB)
```

### Schema introspection

```bash
$ mm find ~/data/domains --schema
```

```
column    type          description                                                    sample
path      string        Relative path from the scanned root directory                  construction/...
name      string        File name with extension                                       5001 Eisenhower...
size      uint64        File size in bytes                                             19114932
mime      string        MIME type inferred from extension                              application/pdf
kind      string        Semantic category: image | video | document | audio | ...      document
width     uint32        Pixel width (images from header, videos via ffprobe)           None
height    uint32        Pixel height (images from header, videos via ffprobe)          None
```

### Filter by name (regex)

```bash
$ mm find ~/data/domains --name "invoice" --format tsv
```

```
kind      size       path
document  1131508    document.invoice/sample-invoice.pdf
document  192580     document.invoice/hub_examples_document.invoice_google_invoice.pdf
document  47568      document.invoice/hub_examples_document.invoice_receipt.pdf
```

### Include gitignored files

```bash
$ mm find ~/data/domains --no-ignore --kind video
```

```
name                                kind   size        ext
bakery.mp4                          video  29346272    .mp4
google_next_2025_keynote.mp4        video  173208064   .mp4
```

By default, `mm find` respects `.gitignore` rules (using the `ignore` crate). Pass `--no-ignore` to bypass this and include all files regardless of gitignore patterns.

### Large documents (>10 MB)

```bash
$ mm find ~/data/domains --kind document --min-size 10mb --sort size --reverse
```

```
construction/5001 Eisenhower Avenue/Bid Documents/5001 Eisenhower Ave - 100_ Bid Documents.pdf
construction/large_500-page_document.pdf
construction/public/SFRD-172_BID SET-Architectural-Set_2024.01.05.pdf
healthcare-codegen-reports/longevity_intake_form_scanned.pdf
```

---

## `cat` — Type-aware content extraction

`cat` auto-detects the file type and extracts structured representations. No
flags needed for basic use — an image becomes dimensions + EXIF, a video
becomes resolution + codecs, a PDF becomes extracted text.

### PDF text extraction (fast mode)

```bash
$ mm cat ~/data/domains/document.invoice/sample-invoice.pdf -n 15
```

```
CPB Software (Germany) GmbH - Im Bruch 3 - 63897 Miltenberg/Main
Musterkunde AG
Mr. John Doe
Invoice WMACCESS Internet
VAT No. DE199378386
Invoice No 123100401
```

### Scanned PDF (no extractable text)

```bash
$ mm cat ~/data/domains/document.invoice/scanned.pdf
```

```
[No extractable text — this PDF may contain scanned images only]
```

### Image metadata (fast mode)

```bash
$ mm cat ~/data/domains/image.agent/tennis.jpg
```

```
Dimensions: 926x599
MIME:       image/jpeg
Hash:       0eae1d0b9767689c
```

### Video metadata (fast mode)

```bash
$ mm cat ~/data/domains/video.transcription/bakery.mp4
```

```
Resolution: 1280x720
Duration:   4m 12.7s
FPS:        23.974
Video:      h264
Audio:      aac
Frames:     48 (uniform)
Mosaic:     /tmp/mm_.../bakery_mosaic_1.jpg
```

### LLM caption (accurate mode)

```bash
$ mm cat photo.jpg -m accurate
```

```
A landscape photograph taken at golden hour showing rolling hills with a
vineyard in the foreground. A stone farmhouse sits mid-frame with cypress
trees lining a gravel path. Shot on Canon EOS R5, shallow depth of field.
```

### Video keyframe mosaic + LLM description (accurate mode)

```bash
$ mm cat demo.mp4 -m accurate
```

```
A 3-minute product demo video. Opens with a title card showing "v2.0 Release".
The presenter demonstrates a dashboard UI with real-time charts. Key segments:
0:00-0:15 intro/title, 0:15-1:30 feature walkthrough, 1:30-2:45 live demo
with data filtering, 2:45-3:00 closing with GitHub link.
```

---

## `grep` — Content search

### Search with context lines

```bash
$ mm grep "longevity" ~/data/domains --kind document -C 1
```

```
healthcare-codegen-reports/longevity_intake_form_scanned.pdf
    3  for a longevity screening patient. Combines:
  210  ...presenting for comprehensive longevity screening...
```

### Case-insensitive search

```bash
$ mm grep "Quantum Phase" ~/data/domains --kind document -i
```

```
document.science/paper.pdf
   34  Persistent homology maps the same quantum phase across decades...
```

The `-i` / `--ignore-case` flag makes the regex match case-insensitive, matching the standard `grep -i` behavior.

### Semantic search (vector similarity)

```bash
$ mm grep "financial projections" ~/data/domains --level 2
```

```
path                                                     index  distance  match
construction/5001 Eisenhower Avenue/Bid Documents/...    0      0.2341    The projected cost breakdown includes...
document.invoice/sample-invoice.pdf                      0      0.3012    Invoice total: 130,00 EUR...
```

```bash
$ mm grep "patient diagnosis" ~/data/domains --level 2 --kind document --format json
```

```json
[
  {"path": "healthcare/medical-report.pdf", "index": 0, "distance": 0.1823, "match": "Patient presents with..."},
  {"path": "healthcare/lab-results.pdf", "index": 1, "distance": 0.2156, "match": "Complete blood count analysis..."}
]
```

---

## `sql` — SQL analytics on the file index

`mm sql` auto-routes queries: `files` → ephemeral scan + SQLite,
`l2_results`/`chunks` → persistent SQLite.

### Kind breakdown with sizes

```bash
$ mm sql "SELECT kind, COUNT(*) as files, ROUND(SUM(size)/1e6,1) as mb \
  FROM files GROUP BY kind ORDER BY mb DESC" --dir ~/data/domains
```

```
kind      files  mb
document  545    3171.5
other     10     2340.0
video     7      1692.4
audio     2      502.6
image     134    68.5
```

### File size distribution

```bash
$ mm sql "SELECT \
  CASE WHEN size < 100*1024 THEN '<100KB' \
       WHEN size < 1024*1024 THEN '100KB-1MB' \
       WHEN size < 10*1024*1024 THEN '1-10MB' \
       WHEN size < 100*1024*1024 THEN '10-100MB' \
       ELSE '>100MB' END as bucket, \
  COUNT(*) as files FROM files GROUP BY bucket ORDER BY files DESC" \
  --dir ~/data/domains
```

```
bucket     files
100KB-1MB  341
1-10MB     214
<100KB     107
10-100MB   31
>100MB     9
```

### Listing stored tables

```bash
$ mm sql --list-tables
table        source         stored
files        scan + SQLite  ephemeral
l2_results   SQLite         2 rows
chunks       SQLite         2 rows
chunks_vec   sqlite-vec     2 rows
```

---

## Profile management

```bash
$ mm profile add openrouter --base-url https://openrouter.ai/api/v1 --api-key sk-... --model vlm-1
$ mm profile add openai     --base-url https://api.openai.com/v1   --api-key sk-... --model gpt-4o

$ mm profile list
              Profiles
╭────┬────────────┬──────────────────────────────┬───────────────────────────────╮
│    │ profile    │ base_url                     │ model                         │
├────┼────────────┼──────────────────────────────┼───────────────────────────────┤
│    │ gemini     │ https://openrouter.ai/api/v1 │ google/gemini-2.5-flash-lite  │
│ ●  │ ollama     │ http://localhost:11434        │ qwen3.5:0.8                   │
│    │ vlmrun     │ https://mm-ctx.ngrok.io/v1   │ Qwen/Qwen3.5-0.8B            │
╰────┴────────────┴──────────────────────────────┴───────────────────────────────╯

$ mm profile use openrouter
$ mm --profile openrouter cat photo.png -m accurate
$ MM_PROFILE=openai mm cat photo.png -m accurate
```

---

## Composability

### mm self-pipes

Every command reads paths from stdin, so mm commands chain naturally:

```bash
# How many tokens in all my PDFs?
$ mm find ~/research --kind document | mm wc

# Find the 5 largest images, get their EXIF metadata
$ mm sql "SELECT path FROM files WHERE kind='image' ORDER BY size DESC LIMIT 5" \
    --dir ~/photos | mm cat
```

### Unix pipes

```bash
# Count large PDFs
mm find ~/data/domains --kind document --min-size 10mb | wc -l

# JSON metadata for videos, pipe to jq
mm find ~/data/domains --kind video --format json | jq '.[].name'

# Find all PDFs → extract text → search for a term
mm find ~/papers --ext pdf | mm cat | grep "attention"
```

### Piping to `llm`

```bash
# Summarize a PDF
mm cat paper.pdf | llm -s "Summarize this paper in 3 bullet points"

# Describe a project structure
mm find ~/project --tree --depth 2 | llm -s "Describe this project structure"
```

---

## Design principles

1. **Token efficiency** — piped output uses minimal formatting. No borders, no color codes, no padding. Every byte carries information.
2. **Auto-detection** — `cat` knows a `.jpg` needs EXIF extraction, a `.mp4` needs codec/duration, a `.pdf` needs text extraction. No flags needed.
3. **Two modes** — fast mode (local extraction, <100ms, no external deps) and accurate mode (LLM pipelines via YAML, requires API).
4. **Composability** — `find` outputs paths → `cat` reads from stdin → `wc` counts tokens. Standard Unix pipes, multimodal awareness.
5. **Speed** — Rust core with `rayon` parallelism. Metadata scan indexes 249 files in 5 ms. Fast-mode image metadata in <1 ms/file. Video metadata without ffmpeg.

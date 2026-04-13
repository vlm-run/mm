# mm — Examples

Every command supports `--format` for output control:

- **`rich`** (default in TTY) — formatted tables, panels, syntax highlighting
- **`tsv`** (default when piped) — tab-separated, no ANSI, maximum token efficiency
- **`csv`** — comma-separated, spreadsheet-friendly
- **`json`** — structured JSON (compact when piped, pretty in TTY)

Real outputs below are from `~/data/domains` (702 files, 7.2 GB) unless noted otherwise.

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
code      4      205.5 KB   5.3K          52.6K
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

### Token budget check

```bash
$ mm wc ~/project --kind code
```

```
files  size     lines (est.)  tokens (est.)
156    1.2 MB   38K           285K
```

156 code files, ~285K tokens — fits in a 500K context window.

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
google_io_keynote_2024.mp4          video  536369719   .mp4
google_next_2025_keynote.mp4        video  511043010   .mp4
```

### Tree view

```bash
$ mm find ~/data/domains --tree --depth 1
```

```
/Users/sudeep/data/domains  (702 files, 7.2 GB)
├── audio/  (2 files, 479.3 MB)
│   ├── lex_fridman_podcast_459_deepseek_openai_nvidia_xai_tsmc_stargate_ai_megaclusters.mp3  [420.6 MB]
│   └── palantir_q3_2024_earnings_webcast.mp3  [58.6 MB]
├── chatgpt/  (1 files, 1.0 MB)
│   └── vision-checkup.png  [1.0 MB]
├── construction/  (532 files, 5.0 GB)
│   ├── 5001 Eisenhower Avenue/  (504 files, 2.6 GB)
│   ├── plans/  (15 files, 994.8 KB)
│   ├── public/  (6 files, 134.0 MB)
│   ├── ...
│   └── large_500-page_document.pdf  [62.6 MB]
├── document-markdown/  (8 files, 10.6 MB)
├── document.invoice/  (6 files, 1.3 MB)
├── document.layout/  (12 files, 6.0 MB)
├── document.table-markdown/  (13 files, 2.9 MB)
├── document.utility-bill/  (2 files, 785.3 KB)
├── healthcare/  (22 files, 63.6 MB)
├── healthcare-codegen-reports/  (12 files, 165.0 MB)
├── image.agent/  (51 files, 31.7 MB)
├── image.object-detection/  (23 files, 16.8 MB)
├── mcp-demos/  (1 files, 156.8 KB)
├── tv.news/  (1 files, 206.9 KB)
├── video.transcription/  (5 files, 1.0 GB)
├── web.ui-automation/  (6 files, 786.0 KB)
├── .DS_Store  [22.0 KB]
├── car.jpg  [38.2 KB]
├── google_next_2025_keynote.mp4  [487.4 MB]
├── remote-sensing-planet_labs_compound_da276d56f7.jpg  [177.8 KB]
└── tv-news-bbc_news_ukraine_screenshot_51637c69f4.jpg  [43.1 KB]
```

### Schema introspection

```bash
$ mm find ~/data/domains --schema
```

```
column    type          description                                                    sample
path      string        Relative path from the scanned root directory                  construction/5001 Eisenhower...
name      string        File name with extension                                       5001 Eisenhower Ave - 100_ B...
stem      string        File name without extension                                    5001 Eisenhower Ave - 100_ B...
ext       string        File extension including dot (.png, .pdf, .mp4)                .pdf
size      uint64        File size in bytes                                             19114932
modified  timestamp     Last modification timestamp (UTC)                              2025-05-18 05:19:16
created   timestamp     Creation timestamp (UTC)                                       2025-05-18 05:19:16
mime      string        MIME type inferred from extension                              application/pdf
kind      string        Semantic category: image | video | document | code | ...       document
is_binary bool          True if the file is detected as binary content                 False
depth     uint16        Directory depth relative to scan root (0 = top-level)          3
parent    string        Parent directory name (empty string for top-level)             construction/5001 Eisenhower...
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

```bash
$ mm find ~/data/domains --name "\.mp4$" --tree
```

```
/Users/sudeep/data/domains  (7 files, 1.6 GB)
├── healthcare/  (1 files, 53.6 MB)
│   └── video-walkthrough-healthcare.mp4  [53.6 MB]
├── video.transcription/  (5 files, 1.0 GB)
│   ├── bakery.mp4  [28.0 MB]
│   ├── google_io_keynote_2024.mp4  [511.4 MB]
│   ├── google_next_2025_keynote.mp4  [487.4 MB]
│   ├── gooogle_gemini_intro video.mp4  [10.5 MB]
│   └── how_to_build_an_mvp.mp4  [35.6 MB]
└── google_next_2025_keynote.mp4  [487.4 MB]
```

### Images sorted by size

```bash
$ mm find ~/data/domains --kind image --sort size --reverse --limit 10
```

```
image.object-detection/vehicles.png
image.agent/vehicles.png
image.agent/bottles.png
image.agent/containers.png
image.object-detection/basketball-1.png
image.agent/basketball-1.png
image.object-detection/people-walking.png
image.agent/people-walking.png
image.agent/Cupcakes.jpg
construction/construction-plan-tables.jpg
```

### Large documents (>10MB)

```bash
$ mm find ~/data/domains --kind document --min-size 10mb --sort size --reverse
```

```
construction/5001 Eisenhower Avenue/Bid Documents/5001 Eisenhower Ave - 100_ Bid Documents.pdf
construction/5001 Eisenhower Avenue/Bid Documents/Micellaneous Schedules and Cut Sheets - Combined.pdf
construction/5001 Eisenhower Avenue/Bid Documents/Design Reports/Victory Center Staff Report.pdf
healthcare-codegen-reports/sample_longevity_report_scanned.pdf
construction/large_500-page_document.pdf
construction/public/SFRD-172_BID SET-Architectural-Set_2024.01.05.pdf
healthcare-codegen-reports/longevity_intake_form_scanned.pdf
...
```

### JSON output

```bash
$ mm find ~/data/domains --kind image --ext .png --limit 5 --format json
```

```json
[
  {
    "path": "image.object-detection/basketball-1.png",
    "name": "basketball-1.png",
    "kind": "image",
    "size": 1880275,
    "ext": ".png",
    "width": 1920,
    "height": 1080,
    "mime": "image/png"
  },
  ...
]
```

---

## `cat` — Type-aware content extraction

`cat` auto-detects the file type and extracts structured representations. No flags needed for basic use — an image becomes dimensions + EXIF, a video becomes resolution + codecs, a PDF becomes extracted text.

### PDF text extraction

```bash
$ mm cat ~/data/domains/document.invoice/sample-invoice.pdf -n 15
```

```
CPB Software (Germany) GmbH - Im Bruch 3 - 63897 Miltenberg/Main
Musterkunde AG
Mr. John Doe
Musterstr. 23
12345 Musterstadt Name: Stefanie Müller
Phone: +49 9371 9786-0
Invoice WMACCESS Internet
VAT No. DE199378386
Invoice No
123100401
Amount
-without VAT- quantity
130,00 € 1
10,00 € 0
50,00 € 0
```

### Scanned PDF (no extractable text)

```bash
$ mm cat ~/data/domains/document.invoice/hub_examples_document.invoice_google_invoice.pdf
```

```
[No extractable text — this PDF may contain scanned images only]
```

### Image metadata

```bash
$ mm cat ~/data/domains/image.agent/tennis.jpg
```

```
Dimensions: 926x599
MIME:       image/jpeg
Hash:       0eae1d0b9767689c
```

### Video metadata

```bash
$ mm cat ~/data/domains/video.transcription/bakery.mp4
```

```
Resolution: 1280x720
Duration:   4m 12.7s (252.71s)
FPS:        23.974
Video:      h264
Audio:      aac
Hash:       70a5808a454ef93f
Frames:     48 (uniform)
Sampled:    992ms
Mosaic:     /tmp/mm_.../bakery_mosaic_1.jpg
```

### Head of a code file

```bash
$ mm cat ~/data/domains/healthcare-codegen-reports/create_longevity_report.py -n 10
```

```
"""
Generate a comprehensive multi-page Longevity Biomarker Report
similar to what Peak Health AI or longevity clinics would produce.
Covers: metabolic health, cardiovascular, inflammation, hormones,
organ function, vitamins/minerals, body composition, and biological age.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white, Color
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

### Count function definitions in code

```bash
$ mm grep "def " ~/data/domains --kind code --count
```

```
healthcare-codegen-reports/create_longevity_report.py:5
healthcare-codegen-reports/create_longevity_report_realistic.py:16
healthcare-codegen-reports/create_radiology_report.py:8
healthcare-codegen-reports/create_realistic_intake.py:21
```

### Search with context lines

```bash
$ mm grep "longevity" ~/data/domains --kind code -C 1
```

```
healthcare-codegen-reports/create_radiology_report.py
    3  for a longevity screening patient. Combines:

healthcare-codegen-reports/create_radiology_report.py
  210  ...presenting for comprehensive longevity screening...

healthcare-codegen-reports/create_longevity_report.py
    3  similar to what Peak Health AI or longevity clinics would produce.
  131      path = os.path.join(OUTPUT_DIR, "sample_longevity_biomarker_report.pdf")
  173      "Your overall longevity score reflects an integrated analysis of 60+ biomarkers..."
  ...
```

### Semantic search (accurate mode — vector similarity)

```bash
$ mm grep "financial projections" ~/data/domains
```

```
path                                                     index  distance  match
construction/5001 Eisenhower Avenue/Bid Documents/...    0      0.2341    The projected cost breakdown includes...
document.invoice/sample-invoice.pdf                      0      0.3012    Invoice total: 130,00 EUR...
```

```bash
$ mm grep "patient diagnosis" ~/data/domains --kind document --format json
```

```json
[
  {"path": "healthcare/medical-report.pdf", "index": 0, "distance": 0.1823, "match": "Patient presents with..."},
  {"path": "healthcare/lab-results.pdf", "index": 1, "distance": 0.2156, "match": "Complete blood count analysis..."}
]
```

---

## `sql` — SQL analytics on the file index

`mm sql` auto-routes queries: `files` → ephemeral scan + SQLite, `l2_results`/`chunks` → persistent SQLite.

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
code      4      0.2
```

### Extension analytics

```bash
$ mm sql "SELECT ext, COUNT(*) as files, ROUND(SUM(size)/1e6,1) as mb \
  FROM files GROUP BY ext ORDER BY files DESC LIMIT 10" --dir ~/data/domains
```

```
ext    files  mb
.pdf   454    3087.2
.PDF   91     84.3
.jpg   84     28.1
.png   32     38.2
       8      0.1
.jpeg  8      1.0
.mp4   7      1692.4
.webp  6      0.9
.py    4      0.2
.avif  3      0.3
```

### Storage by directory

```bash
$ mm sql "SELECT parent, COUNT(*) as files, ROUND(SUM(size)/1e6,1) as mb \
  FROM files GROUP BY parent ORDER BY mb DESC LIMIT 10" --dir ~/data/domains
```

```
parent                                                       files  mb
construction                                                 7      2412.2
construction/5001 Eisenhower Avenue/Bid Documents             17     1511.9
video.transcription                                          5      1125.1
                                                             5      511.3
audio                                                        2      502.6
construction/.../2007 Renovation/(5) Architectural           81     184.3
healthcare-codegen-reports                                   12     173.0
construction/public                                          6      140.5
construction/.../Existing Drawings                           2      132.1
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

### Querying stored tables

```bash
$ mm sql --list-tables
table        source         stored
files        scan + SQLite  ephemeral
l2_results   SQLite         2 rows
chunks       SQLite         2 rows
chunks_vec   sqlite-vec     2 rows

$ mm sql "SELECT file_uri, profile, model, summary FROM l2_results"
$ mm sql "SELECT file_uri, chunk_idx, LENGTH(chunk_text) as len FROM chunks"
$ mm sql "SELECT COUNT(*) as total FROM chunks"
```

---

## `config` — Configuration and database management

```bash
$ mm config reset-db
The following will be deleted:
  /Users/you/.local/share/mm/mm.db
This leads to irreversible data loss. Continue? [y/N]: y
All databases and caches have been reset.

# Skip confirmation
$ mm config reset-db --yes
```

---

## Profile management

```bash
# Set up profiles
$ mm profile add openrouter --base-url https://openrouter.ai/api/v1 --api-key sk-... --model vlm-1
$ mm profile add openai --base-url https://api.openai.com/v1 --api-key sk-or-... --model gpt-4o

# List profiles
$ mm profile list
              Profiles
╭────┬────────────┬──────────────────────────────┬─────────────────╮
│    │ profile    │ base_url                     │ model           │
├────┼────────────┼──────────────────────────────┼─────────────────┤
│ ●  │ default    │ https://api.vlm.run/v1       │ vlm-1           │
│    │ ollama     │ http://localhost:11434       │ qwen3-vl:2b     │
│    │ openrouter │ https://openrouter.ai/api/v1 │ qwen/qwen3.5-9b │
╰────┴────────────┴──────────────────────────────┴─────────────────╯

# Switch active profile
$ mm profile use openrouter

# Use a different profile for a single command
$ mm --profile openrouter cat photo.png -m accurate

# Update a field
$ mm profile update openrouter --model qwen/qwen3.5-27b

# Remove a profile
$ mm profile remove openrouter

# Environment variable override
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

### Piping to DuckDB

mm's TSV output is directly consumable by DuckDB via `/dev/stdin`:

```bash
# Full SQL power: window functions, CTEs, exports
mm find ~/data --columns name,kind,size,ext \
  | duckdb -c "
      SELECT kind, COUNT(*) AS n, SUM(size) AS bytes
      FROM read_csv('/dev/stdin', delim='\t', header=true)
      GROUP BY kind ORDER BY bytes DESC"

# Rank files within each kind
mm find ~/data --columns name,kind,size \
  | duckdb -c "
      WITH ranked AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY kind ORDER BY size DESC) AS rn
        FROM read_csv('/dev/stdin', delim='\t', header=true)
      )
      SELECT name, kind, size FROM ranked WHERE rn <= 3"

# Export to Parquet
mm find ~/data \
  | duckdb -c "
      COPY (SELECT * FROM read_csv('/dev/stdin', delim='\t', header=true))
      TO 'index.parquet' (FORMAT PARQUET)"
```

### Piping to `llm`

[`llm`](https://github.com/simonw/llm) by Simon Willison — mm extracts context, `llm` reasons over it:

```bash
# Describe a project structure
mm find ~/project --tree --depth 2 | llm -s "Describe this project structure"

# Summarize a PDF
mm cat paper.pdf | llm -s "Summarize this paper in 3 bullet points"

# Triage TODOs
mm grep "TODO" --kind code | llm -s "Triage these TODOs by priority (P0/P1/P2)"

# Morning digest
{
  echo "## File changes (last 24h)"
  mm sql "SELECT name, kind, size, modified FROM files WHERE modified > CURRENT_TIMESTAMP - INTERVAL 1 DAY ORDER BY modified DESC"
  echo ""
  echo "## TODOs"
  mm grep "TODO\|FIXME\|HACK" --kind code
} | llm -s "Generate a morning standup summary from this project state"
```

### External tools

```bash
# mm finds files, exiftool goes deep on metadata
mm find ~/photos --kind image --ext cr3,nef,arw \
  | cut -f3 | xargs exiftool -json -q \
  | jq '.[] | {file: .SourceFile, iso: .ISO, shutter: .ShutterSpeed}'

# rg finds pattern; mm counts the token cost
rg -l "unsafe" --type rust ~/project | mm cat | mm wc

# jq on JSON output
mm find ~/data --format json | jq '[.[] | select(.kind=="image")] | length'

# miller on TSV
mm find ~/data | mlr --tsvlite --from - then sort-by -nr size then head -n 10
```

---

## Design principles

1. **Token efficiency** — piped output uses minimal formatting. No borders, no color codes, no padding. Every byte carries information.
2. **Auto-detection** — `cat` knows a `.jpg` needs EXIF extraction, a `.mp4` needs codec/duration, a `.pdf` needs text extraction. No flags needed.
3. **Two modes** — fast mode (local extraction, <100ms, no external deps) and accurate mode (LLM pipelines via YAML, requires API).
4. **Composability** — `find` outputs paths → `cat` reads from stdin → `wc` counts tokens. Standard Unix pipes, multimodal awareness.
5. **Speed** — Rust core with `rayon` parallelism. Metadata scan indexes 249 files in 5ms. Fast-mode image metadata in <1ms/file. Video metadata without ffmpeg.

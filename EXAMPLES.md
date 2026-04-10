# mm examples

Real outputs from running mm against `~/data/domains` (702 files, 7.2 GB).

---

## wc — count files, size, lines, tokens

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

---

## find — locate/list files, tree view, schema

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

### Schema

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

---

### Filter by file name (regex or substring)

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

---

### Find images sorted by size

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

### Find large documents (>10MB)

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

### Find PNGs (JSON output)

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

### Find videos sorted by size

```bash
$ mm find ~/data/domains --kind video --sort size --reverse --limit 5
```

```
video.transcription/google_io_keynote_2024.mp4
video.transcription/google_next_2025_keynote.mp4
google_next_2025_keynote.mp4
healthcare/video-walkthrough-healthcare.mp4
video.transcription/how_to_build_an_mvp.mp4
```

---

## cat — content extraction

### Extract text from a PDF

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

### Video metadata + keyframes

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

### Head / tail of code files

```bash
$ mm cat ~/data/domains/healthcare-codegen-reports/create_longevity_report.py -n 10 --level 0
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

---

## grep — content search

### Count function definitions in code files

```bash
$ mm grep "def " ~/data/domains --kind code --count
```

```
healthcare-codegen-reports/create_longevity_report.py:5
healthcare-codegen-reports/create_longevity_report_realistic.py:16
healthcare-codegen-reports/create_radiology_report.py:8
healthcare-codegen-reports/create_realistic_intake.py:21
```

### Semantic search (L2 — vector similarity)

```bash
# Auto-index unindexed files before search
$ mm grep "financial projections" ~/data/domains -l 2 --index
Indexing 2 files...
Indexed 2 files.

[Search Result]
```

```bash
$ mm grep "financial projections" ~/data/domains -l 2
```

```
path                                                     index  distance  match
construction/5001 Eisenhower Avenue/Bid Documents/...    0      0.2341    The projected cost breakdown includes...
document.invoice/sample-invoice.pdf                      0      0.3012    Invoice total: 130,00 EUR...
```

```bash
$ mm grep "patient diagnosis" ~/data/domains -l 2 --kind document --format json
```

```json
[
  {"path": "healthcare/medical-report.pdf", "index": 0, "distance": 0.1823, "match": "Patient presents with..."},
  {"path": "healthcare/lab-results.pdf", "index": 1, "distance": 0.2156, "match": "Complete blood count analysis..."}
]
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

---

## sql — SQL queries on the file index

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
construction/5001 Eisenhower Avenue/Bid Documents/Design...  4      213.1
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

---

## sql — querying stored tables

```bash
# List available tables
$ mm sql --list-tables
table        source         stored
files        scan + SQLite  ephemeral
l2_results   SQLite         2 rows
chunks       SQLite         2 rows
chunks_vec   sqlite-vec     2 rows

# Query L2 results (auto-routes to persistent SQLite)
$ mm sql "SELECT file_uri, profile, model, summary FROM l2_results"

# Query chunks and embeddings
$ mm sql "SELECT file_uri, chunk_idx, LENGTH(chunk_text) as len FROM chunks"

# Count chunks
$ mm sql "SELECT COUNT(*) as total FROM chunks"

# Pre-index unindexed files before query
$ mm sql "SELECT kind, COUNT(*) as n FROM files GROUP BY kind" --dir ~/data/domains --pre-index
```

---

## config reset-db — clear all databases

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

## Pipe composability

```bash
# Count large PDFs
mm find ~/data/domains --kind document --min-size 10mb | wc -l

# Find images then list with metadata
mm find ~/data/domains --kind image | mm find ~/data/domains

# Get JSON metadata for videos, pipe to jq
mm find ~/data/domains --kind video --format json | jq '.[].name'
```

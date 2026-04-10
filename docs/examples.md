# mm — Prototypical Output Examples

Every command has three output modes controlled by `--format`:

- **`rich`** (default in TTY) — Rich formatted tables, panels, and syntax highlighting.
- **`tsv`** (default when piped) — Tab-separated values with header. Maximum token efficiency.
- **`csv`** — Comma-separated values with header. Spreadsheet-friendly.
- **`json`** — Structured JSON. Compact when piped (no indent), pretty in TTY.

When stdout is piped, mm auto-selects `tsv`. Override with `--format json` etc.

---

## 1. `find` — Structured listing with multimodal metadata | Multimodal-aware file discovery 

Traditional `find` knows nothing about file semantics. mm `find` classifies files by **kind** (image, video, document, code, audio, data, config, text) and filters by size, extension, and kind — all in ~5ms. 

> mm `find` exposes a full Arrow schema: dimensions, kind, depth, MIME — queryable columns that LLMs can reason over.

### Example 1: Find all images

```bash
$ mm find ~/project --kind image
```

**TTY output:**
```
┌──────────────────────────────────────────────┐
│ path                        kind   size  ext │
├──────────────────────────────────────────────┤
│ assets/hero.png             image  2.1 MB png │
│ assets/logo.svg             image  12 KB  svg │
│ docs/figures/arch.png       image  847 KB png │
│ data/photos/DSC_0042.jpg    image  4.8 MB jpg │
│ data/photos/DSC_0043.jpg    image  5.1 MB jpg │
│ screenshots/v2-ui.png       image  1.3 MB png │
└──────────────────────────────────────────────┘
```

**Piped output (LLM-consumable):**
```
assets/hero.png
assets/logo.svg
docs/figures/arch.png
data/photos/DSC_0042.jpg
data/photos/DSC_0043.jpg
screenshots/v2-ui.png
```

### Example 2: Find large video files

```bash
$ mm find ~/data --kind video --min-size 100MB --format json
```

```json
[
  {"path": "recordings/meeting-2024-03-15.mp4", "kind": "video", "size": 524288000, "ext": "mp4"},
  {"path": "demos/product-tour.mkv", "kind": "video", "size": 209715200, "ext": "mkv"},
  {"path": "raw/interview-final.mp4", "kind": "video", "size": 1073741824, "ext": "mp4"}
]
```

### Example 3: Find documents, limit 5

```bash
$ mm find ~/research --kind document --limit 5
```

**Piped:**
```
papers/attention-is-all-you-need.pdf
papers/scaling-laws.pdf
notes/experiment-log.pdf
slides/q4-review.pptx
reports/annual-2024.pdf
```

### Example 4: Find code by extension

```bash
$ mm find . --ext rs --sort size
```

**Piped:**
```
crates/core/src/walk.rs
crates/core/src/extract.rs
crates/core/src/table.rs
crates/core/src/meta.rs
crates/python/src/lib.rs
```

### Example 5: Composable pipe — find images, then cat metadata

```bash
$ mm find ~/photos --kind image --max-size 1MB | mm cat --level 1
```

**Piped (each file's L1 metadata emitted sequentially):**
```
Dimensions: 1920x1080
MIME:       image/png
Hash:       a3f7c2d91e4b0856

Dimensions: 640x480
MIME:       image/jpeg
Hash:       1bc9e4f0a7d523e1
Camera:     Canon EOS R5
Date:       2024-03-15T14:32:01
GPS:        37.7749,-122.4194
```

---

### Example 6: Default tabular listing

```bash
$ mm find ~/project/assets
```

**TTY output:**
```
┌─────────────────────────────────────────────────────┐
│ name              kind      size     ext             │
├─────────────────────────────────────────────────────┤
│ hero.png          image     2.1 MB   png             │
│ demo.mp4          video     48.3 MB  mp4             │
│ whitepaper.pdf    document  1.2 MB   pdf             │
│ main.py           code      4.2 KB   py              │
│ config.toml       config    892 B    toml            │
│ README.md         text      2.1 KB   md              │
│ data.parquet      data      12.4 MB  parquet         │
│ recording.mp3     audio     8.7 MB   mp3             │
└─────────────────────────────────────────────────────┘
```

**Piped:**
```
name	kind	size	ext
hero.png	image	2197504	png
demo.mp4	video	50647859	mp4
whitepaper.pdf	document	1258291	pdf
main.py	code	4301	py
config.toml	config	892	toml
README.md	text	2150	md
data.parquet	data	13002547	parquet
recording.mp3	audio	9122816	mp3
```

### Example 7: Extended columns with image dimensions

```bash
$ mm find ~/photos --columns name,kind,size,width,height --sort size
```

**Piped:**
```
name	kind	size	width	height
DSC_0042.jpg	image	5033164	4000	3000
DSC_0043.jpg	image	4915200	4000	3000
panorama.png	image	3145728	8000	2000
thumbnail.jpg	image	24576	320	240
icon.png	image	4096	64	64
```

### Example 8: Tree view

```bash
$ mm find ~/project --tree --depth 2
```

**TTY output:**
```
📁 project  (47 files, 82.3 MB)
├── 📁 src  (12 files, 48 KB)
│   ├── main.py
│   ├── utils.py
│   └── models/
├── 📁 data  (8 files, 71.2 MB)
│   ├── train.parquet
│   ├── photos/
│   └── recordings/
├── 📁 docs  (15 files, 4.8 MB)
│   ├── paper.pdf
│   ├── figures/
│   └── slides/
├── README.md
├── Makefile
└── pyproject.toml
```

**Piped (ASCII art, no color):**
```
project  (47 files, 82.3 MB)
├── src  (12 files, 48 KB)
│   ├── main.py
│   ├── utils.py
│   └── models/
├── data  (8 files, 71.2 MB)
│   ├── train.parquet
│   ├── photos/
│   └── recordings/
├── docs  (15 files, 4.8 MB)
│   ├── paper.pdf
│   ├── figures/
│   └── slides/
├── README.md
├── Makefile
└── pyproject.toml
```

### Example 9: Schema introspection

```bash
$ mm find ~/data --schema
```

**Piped:**
```
column	type	description
path	utf8	Relative file path (e.g. src/main.py)
name	utf8	File name (e.g. main.py)
stem	utf8	Name without extension (e.g. main)
ext	utf8	File extension (e.g. py)
size	int64	Size in bytes (e.g. 4,301 (4.2 KB))
modified	timestamp[us]	Last modified (e.g. 2024-03-15 14:32:01)
mime	utf8	MIME type (e.g. image/png)
kind	utf8	Semantic kind (e.g. image)
depth	int32	Directory nesting depth (e.g. 2)
width	int32	Image/video width in px (e.g. 1920)
height	int32	Image/video height in px (e.g. 1080)
```

### Example 10: JSON tree (for programmatic consumption)

```bash
$ mm find ~/project --tree --depth 1 --format json
```

```json
{
  "name": "project",
  "type": "directory",
  "files": 47,
  "bytes": 86292480,
  "children": [
    {"name": "src", "type": "directory", "files": 12, "bytes": 49152},
    {"name": "data", "type": "directory", "files": 8, "bytes": 74648986},
    {"name": "docs", "type": "directory", "files": 15, "bytes": 5033164},
    {"name": "README.md", "type": "file"},
    {"name": "Makefile", "type": "file"},
    {"name": "pyproject.toml", "type": "file"}
  ]
}
```

---

## 3. `cat` — Type-aware content extraction

Traditional `cat` dumps raw bytes. mm `cat` **auto-detects** the file type and extracts structured, token-efficient representations. An image becomes dimensions + EXIF. A video becomes resolution + duration + codecs. A PDF becomes extracted text. This is where multimodal understanding shines — every file type gets a representation an LLM can reason about.

### Example 1: Image → structured metadata (L1)

```bash
$ mm cat photo.jpg --level 1
```

**TTY output:**
```
╭─ photo.jpg ───────────────────── 4.8 MB · L1 ─╮
│ Dimensions: 4000x3000                          │
│ MIME:       image/jpeg                          │
│ Hash:       a3f7c2d91e4b0856                   │
│ Camera:     Canon EOS R5                        │
│ Date:       2024-03-15T14:32:01                 │
│ GPS:        37.7749,-122.4194                   │
│ Orientation: 1 (normal)                         │
╰────────────────────────────────────────────────╯
```

**Piped (LLM-consumable, 7 tokens-per-field):**
```
Dimensions: 4000x3000
MIME:       image/jpeg
Hash:       a3f7c2d91e4b0856
Camera:     Canon EOS R5
Date:       2024-03-15T14:32:01
GPS:        37.7749,-122.4194
Orientation: 1 (normal)
```

### Example 2: Video → native metadata (L1, no ffmpeg, <100ms)

```bash
$ mm cat interview.mp4 --level 1
```

**Piped:**
```
Resolution: 1920x1080
Duration:   45m 12.3s (2712.30s)
FPS:        30.0
Video:      h264
Audio:      aac
Hash:       e7b2f1a4c890d356
```

### Example 3: PDF → extracted text (L1)

```bash
$ mm cat paper.pdf --level 1
```

**Piped:**
```
Attention Is All You Need

Abstract

The dominant sequence transduction models are based on complex recurrent or
convolutional neural networks that include an encoder and a decoder. The best
performing models also connect the encoder and decoder through an attention
mechanism. We propose a new simple network architecture, the Transformer,
based solely on attention mechanisms, dispensing with recurrence and convolutions
entirely. Experiments on two machine translation tasks show these models to be
superior in quality while being more parallelizable and requiring significantly
less time to train.

1 Introduction

...
```

### Example 4: Code → syntax-highlighted (L0) or raw passthrough

```bash
$ mm cat src/main.rs --level 0 -n 15
```

**TTY output:**
```
╭─ src/main.rs ──────────── 2.1 KB · L0 · lines 1-15 ─╮
│  1 │ use std::path::PathBuf;                          │
│  2 │ use clap::Parser;                                │
│  3 │                                                  │
│  4 │ #[derive(Parser)]                                │
│  5 │ struct Args {                                    │
│  6 │     /// Input directory to scan                  │
│  7 │     #[arg(short, long)]                          │
│  8 │     dir: PathBuf,                                │
│  9 │ }                                                │
│ 10 │                                                  │
│ 11 │ fn main() {                                      │
│ 12 │     let args = Args::parse();                    │
│ 13 │     let scanner = Scanner::new(&args.dir);       │
│ 14 │     scanner.run();                               │
│ 15 │ }                                                │
╰───────────────────────────────────────────────────────╯
```

**Piped (raw text, no decoration):**
```
use std::path::PathBuf;
use clap::Parser;

#[derive(Parser)]
struct Args {
    /// Input directory to scan
    #[arg(short, long)]
    dir: PathBuf,
}

fn main() {
    let args = Args::parse();
    let scanner = Scanner::new(&args.dir);
    scanner.run();
}
```

### Example 5: Image → LLM caption (L2)

```bash
$ mm cat photo.jpg --level 2
```

**Piped:**
```
A landscape photograph taken at golden hour showing rolling hills with a
vineyard in the foreground. A stone farmhouse sits mid-frame with cypress
trees lining a gravel path. Shot on Canon EOS R5, shallow depth of field.
```

### Example 6: Video → keyframe mosaic + LLM description (L2)

```bash
$ mm cat demo.mp4 --level 2
```

**Piped:**
```
A 3-minute product demo video. Opens with a title card showing "v2.0 Release".
The presenter demonstrates a dashboard UI with real-time charts. Key segments:
0:00-0:15 intro/title, 0:15-1:30 feature walkthrough, 1:30-2:45 live demo
with data filtering, 2:45-3:00 closing with GitHub link.
```

### Example 7: Multiple files via pipe composition

```bash
$ mm find ~/data --kind image --max-size 500KB | mm cat -l 1 --format json
```

```json
[
  {"path": "icons/logo.png", "level": 1, "content": "Dimensions: 512x512\nMIME:       image/png\nHash:       b4e2a1f7c3d09856"},
  {"path": "thumbs/preview.jpg", "level": 1, "content": "Dimensions: 320x240\nMIME:       image/jpeg\nHash:       7f1c3e9a2b405d68\nCamera:     iPhone 15 Pro"}
]
```

---

## 4. `grep` — Content search across multimodal files

Traditional `grep` searches text. mm `grep` searches across **extracted content** — meaning you can grep inside PDFs, search code by kind, and filter by file type. At L1, it searches extracted metadata; at L0, raw content.

### Example 1: Search across all code files

```bash
$ mm grep "TODO" --kind code
```

**TTY output:**
```
src/extract.rs
   42  // TODO: add HEIF support
  187  // TODO: handle corrupted EXIF gracefully

src/walk.rs
  215  // TODO: benchmark with ignore vs walkdir

python/mm/llm.py
   89  # TODO: add retry with backoff

3 matches in 3 files
```

**Piped (grep-compatible):**
```
src/extract.rs:42:// TODO: add HEIF support
src/extract.rs:187:// TODO: handle corrupted EXIF gracefully
src/walk.rs:215:// TODO: benchmark with ignore vs walkdir
python/mm/llm.py:89:# TODO: add retry with backoff
```

### Example 2: Search documents for a term

```bash
$ mm grep "transformer" --kind document --level 1
```

**Piped:**
```
papers/attention.pdf:1:The Transformer, based solely on attention mechanisms
papers/attention.pdf:14:The Transformer follows this overall architecture
papers/scaling.pdf:8:We study empirical scaling laws for transformer language models
```

### Example 3: Count matches by file

```bash
$ mm grep "import" --kind code --count
```

**TTY output:**
```
╭──────────────────────────────────────────────╮
│ file                              matches    │
├──────────────────────────────────────────────┤
│ src/main.py                            12    │
│ src/utils.py                            8    │
│ src/models.py                           7    │
│ tests/test_main.py                      5    │
│ src/cli.py                              4    │
├──────────────────────────────────────────────┤
│ 36 matches in 5 files                        │
╰──────────────────────────────────────────────╯
```

**Piped:**
```
src/main.py:12
src/utils.py:8
src/models.py:7
tests/test_main.py:5
src/cli.py:4
```

### Example 4: Search with context lines

```bash
$ mm grep "def forward" --ext py -C 2
```

**Piped:**
```
models/transformer.py:44:    def __init__(self, d_model, nhead):
models/transformer.py:45:        super().__init__()
models/transformer.py:46:    def forward(self, src, tgt):
models/transformer.py:47:        attn = self.attention(src, tgt)
models/transformer.py:48:        return self.norm(attn + src)
```

### Example 5: JSON output for programmatic use

```bash
$ mm grep "attention" --kind document --format json
```

```json
[
  {"path": "papers/attention.pdf", "line_number": 1, "line": "The Transformer, based solely on attention mechanisms"},
  {"path": "papers/attention.pdf", "line_number": 7, "line": "Multi-head attention allows the model to jointly attend"},
  {"path": "papers/scaling.pdf", "line_number": 23, "line": "The attention pattern becomes increasingly sparse"}
]
```

### Example 6: Semantic search (L2 — vector similarity)

```bash
$ mm grep "neural network architecture" --kind document --level 2
```

**TTY output:**
```
╭──────────────────────────────────────────────────────────────────────────────────────╮
│ path                        index  distance  match                                   │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ papers/attention.pdf        0      0.1823    The Transformer follows this overall...  │
│ papers/scaling.pdf          1      0.2456    We study empirical scaling laws for...    │
│ notes/experiment-log.pdf    0      0.3891    ResNet-50 baseline training results...    │
╰───────────────────────────── 3 semantic matches ─────────────────────────────────────╯
```

**Piped:**
```
papers/attention.pdf:index0:0.1823:The Transformer follows this overall...
papers/scaling.pdf:index1:0.2456:We study empirical scaling laws for...
notes/experiment-log.pdf:index0:0.3891:ResNet-50 baseline training results...
```

### Example 7: Semantic search with pipe composition

```bash
$ find <dir> -name *  | mm grep "revenue forecast" -l 2 --format json
```

```json
[
  {"path": "reports/annual-2024.pdf", "index": 0, "distance": 0.1245, "match": "Revenue projections for Q4 indicate..."},
  {"path": "slides/q4-review.pptx", "index": 2, "distance": 0.2103, "match": "Year-over-year revenue growth of 23%..."}
]
```

---

## 5. `sql` — SQL analytics on the file index

No traditional Unix equivalent. mm exposes the scanned file index as a SQLite table called `files`, enabling arbitrary SQL analytics on your multimodal directory.

### Example 1: Storage breakdown by kind

```bash
$ mm sql "SELECT kind, COUNT(*) as n, SUM(size) as bytes FROM files GROUP BY kind ORDER BY bytes DESC"
```

**TTY output:**
```
╭──────────────────────────────────────────────╮
│ kind       n      bytes                      │
├──────────────────────────────────────────────┤
│ video      12     2.4 GB                     │
│ image      89     347 MB                     │
│ data       15     128 MB                     │
│ document   23     45 MB                      │
│ audio      8      38 MB                      │
│ code       156    1.2 MB                     │
│ config     34     48 KB                      │
│ text       18     32 KB                      │
╰──────────────────────────────────────────────╯
```

**Piped:**
```
kind	n	bytes
video	12	2576980378
image	89	363855462
data	15	134217728
document	23	47185920
audio	8	39845888
code	156	1258291
config	34	49152
text	18	32768
```

### Example 2: Find largest files per kind

```bash
$ mm sql "SELECT kind, name, size FROM files WHERE size = (SELECT MAX(size) FROM files f2 WHERE f2.kind = files.kind) ORDER BY size DESC"
```

**Piped:**
```
kind	name	size
video	interview-final.mp4	1073741824
image	panorama.png	15728640
data	train.parquet	134217728
document	thesis.pdf	12582912
audio	podcast-ep12.mp3	18874368
code	generated.rs	524288
```

### Example 3: Image resolution statistics

```bash
$ mm sql "SELECT MIN(width) as min_w, MAX(width) as max_w, AVG(width) as avg_w, MIN(height) as min_h, MAX(height) as max_h FROM files WHERE kind='image' AND width IS NOT NULL"
```

**Piped:**
```
min_w	max_w	avg_w	min_h	max_h
64	8000	1847.3	64	4000
```

### Example 4: Files modified in last 7 days

```bash
$ mm sql "SELECT name, kind, size, modified FROM files WHERE modified > CURRENT_TIMESTAMP - INTERVAL 7 DAY ORDER BY modified DESC LIMIT 10"
```

**Piped:**
```
name	kind	size	modified
results.json	data	45231	2024-03-20 09:15:42
model.py	code	8192	2024-03-19 16:22:01
fig3.png	image	1048576	2024-03-19 14:08:33
notes.md	text	2048	2024-03-18 11:45:00
```

### Example 5: Extension frequency distribution

```bash
$ mm sql "SELECT ext, COUNT(*) as n, SUM(size) as total_bytes FROM files GROUP BY ext ORDER BY n DESC LIMIT 10" --format json
```

```json
[
  {"ext": "py", "n": 89, "total_bytes": 524288},
  {"ext": "png", "n": 67, "total_bytes": 234881024},
  {"ext": "rs", "n": 45, "total_bytes": 327680},
  {"ext": "json", "n": 34, "total_bytes": 49152},
  {"ext": "mp4", "n": 12, "total_bytes": 2576980378},
  {"ext": "pdf", "n": 11, "total_bytes": 47185920},
  {"ext": "md", "n": 10, "total_bytes": 20480},
  {"ext": "jpg", "n": 8, "total_bytes": 41943040},
  {"ext": "toml", "n": 7, "total_bytes": 8192},
  {"ext": "mp3", "n": 5, "total_bytes": 26214400}
]
```

---

## 6. `wc` — Token-aware counting

Traditional `wc` counts bytes, words, lines. mm `wc` estimates **tokens** — the unit that matters for LLM context windows. It breaks down by kind, giving you an information-theoretic view of your data.

### Example 1: Summary panel

```bash
$ mm wc ~/project
```

**TTY output:**
```
╭───────────────────────────────╮
│   355  files                  │
│   3.0 GB  total size          │
│   142K  lines (est.)          │
│   1.2M  tokens (est.)         │
╰───────────────────────────────╯
```

**Piped:**
```
files	size	lines (est.)	tokens (est.)
355	3221225472	142000	1200000
```

### Example 2: Breakdown by kind

```bash
$ mm wc ~/project --by-kind
```

**TTY output:**
```
╭──────────────────────────────────────────────────────────────────╮
│ kind       files    size      lines (est.)  tokens (est.)       │
├──────────────────────────────────────────────────────────────────┤
│ video         12    2.4 GB           0              0           │
│ image         89    347 MB           0              0           │
│ data          15    128 MB        245K           820K           │
│ document      23    45 MB          12K            89K           │
│ audio          8    38 MB           0              0            │
│ code         156    1.2 MB        38K           285K            │
│ config        34    48 KB        1.2K           4.8K            │
│ text          18    32 KB         980           3.2K            │
│──────────────────────────────────────────────────────────────────│
│ total        355    3.0 GB       297K           1.2M            │
╰──────────────────────── 355 files  3.0 GB ──────────────────────╯
```

**Piped:**
```
files	size	lines (est.)	tokens (est.)
355	3221225472	297000	1200000

kind	files	size	lines (est.)	tokens (est.)
video	12	2.4 GB	0	0
image	89	347 MB	0	0
data	15	128 MB	245K	820K
document	23	45 MB	12K	89K
audio	8	38 MB	0	0
code	156	1.2 MB	38K	285K
config	34	48 KB	1.2K	4.8K
text	18	32 KB	980	3.2K
```

### Example 3: JSON output

```bash
$ mm wc ~/project --by-kind --format json
```

```json
{
  "files": 355,
  "size": 3221225472,
  "lines (est.)": 297000,
  "tokens (est.)": 1200000,
  "tok_per_mb": 400,
  "by_kind": {
    "video": {"files": 12, "size": 2576980378, "lines (est.)": 0, "tokens (est.)": 0},
    "image": {"files": 89, "size": 363855462, "lines (est.)": 0, "tokens (est.)": 0, "tok_per_img": 85},
    "data": {"files": 15, "size": 134217728, "lines (est.)": 245000, "tokens (est.)": 820000, "tok_per_mb": 6144},
    "document": {"files": 23, "size": 47185920, "lines (est.)": 12000, "tokens (est.)": 89000, "tok_per_mb": 1896},
    "code": {"files": 156, "size": 1258291, "lines (est.)": 38000, "tokens (est.)": 285000, "tok_per_mb": 237568},
    "config": {"files": 34, "size": 49152, "lines (est.)": 1200, "tokens (est.)": 4800, "tok_per_mb": 100000},
    "text": {"files": 18, "size": 32768, "lines (est.)": 980, "tokens (est.)": 3200, "tok_per_mb": 100000}
  }
}
```

### Example 4: Quick token budget check

```bash
$ mm wc ~/project --kind code
```

**Piped:**
```
files	size	lines (est.)	tokens (est.)
156	1258291	38000	285000
```

One line: 156 code files, ~285K tokens. Fits in a 500K context window? Yes. This is the kind of instant decision-making mm enables.

### Example 5: Composable — count tokens for grep results

```bash
$ mm find ~/project --kind document | mm wc
```

**Piped:**
```
files	size	lines (est.)	tokens (est.)
23	47185920	12000	89000
```

---

## Composability: Unix Pipes

The real power is chaining commands. Every command's piped output is designed to be consumed by the next:

```bash
# Find all PDFs → extract text → search for "attention"
mm find ~/papers --ext pdf | mm cat -l 1 | grep "attention"

# Count tokens in just the code files
mm find ~/project --kind code | mm wc

# SQL query → pipe to jq for further processing
mm sql "SELECT name, size FROM files WHERE kind='image'" --format json | jq '.[].name'

# Find large images → get their metadata as JSON for an LLM
mm find ~/data --kind image --min-size 1MB | mm cat -l 1 --format json
```

---

## `config` — Configuration and Profile Management

mm uses **profiles** to manage multiple LLM provider configurations. Each profile stores `base_url`, `api_key`, and `model`. Switch between them instantly — no env vars, no file editing.

### Example 1: Set up profiles

```bash
$ mm config init
Created /Users/you/.config/mm/mm.toml

$ mm profile add openrouter --base-url https://openrouter.ai/api/v1 --api-key sk-... --model vlm-1
Added profile: openrouter  (/Users/you/.config/mm/mm.toml)

$ mm profile add openai --base-url https://api.openai.com/v1--api-key sk-or-... --model gpt-4o
Added profile: openai  (/Users/you/.config/mm/mm.toml)
```

### Example 2: List profiles

```bash
$ mm profile list
```

**TTY output:**
```
              Profiles
╭────┬────────────┬──────────────────────────────┬─────────────────╮
│    │ profile    │ base_url                     │ model           │
├────┼────────────┼──────────────────────────────┼─────────────────┤
│ ●  │ default    │ https://api.vlm.run/v1       │ vlm-1           │
│    │ ollama     │ http://localhost:11434       │ qwen3-vl:2b     │
│    │ openrouter │ https://openrouter.ai/api/v1 │ qwen/qwen3.5-9b │
╰────┴────────────┴──────────────────────────────┴─────────────────╯
```

**JSON output:**
```bash
$ mm profile list --format json
```
```json
{
  "active": "default",
  "profiles": {
    "default": {"base_url": "https://api.vlm.run/v1 ", "api_key": "", "model": "vlm-1"},
    "ollama": {"base_url": "http://localhost:11434", "api_key": "", "model": "qwen3-vl:2b"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key": "••••", "model": "qwen/qwen3.5-9b"},
  }
}
```

### Example 3: Switch and use profiles

```bash
# Switch the active profile
$ mm profile use openrouter
Switched to profile: openrouter  (/Users/you/.config/mm/mm.toml)

# Use a different profile for a single command (does not change active)
$ mm --profile openrouter cat photo.png -l 2
╭─ photo.png ──────────────────────╮
│ Sagittal MRI of a human brain    │
│ showing the cerebrum, cerebellum,│
│ and brainstem.                   │
╰─── 214.7 KB  L2 semantic  3s   ──╯

# Compare results across providers
$ mm --profile default cat photo.png -l 2
╭─ photo.png ───────────────────────╮
│ An MRI scan of a human brain,     │
│ displaying cerebral cortex,       │
│ brainstem, and surrounding        │
│ structures.                       │
╰─── 214.7 KB  L2 semantic  6s    ──╯
```

### Example 4: Update and remove profiles

```bash
# Update a single field
$ mm profile update openrouter --model qwen/qwen3.5-27b
Updated profile: openrouter (model=vlm-2)  (/Users/you/.config/mm/mm.toml)

# Update multiple fields at once
$ mm profile update openrouter --api-key sk-new --model qwen/qwen-2.5-vl-7b-instruct
Updated profile: openrouter (api_key=••••, model=qwen/qwen-2.5-vl-7b-instruct)

# Remove a profile (must switch away from it first)
$ mm profile remove openrouter
Removed profile: openrouter  (/Users/you/.config/mm/mm.toml)
```

### Example 5: View resolved config

```bash
$ mm config show
```

**TTY output:**
```
 Extraction Modes                   
╭──────────┬───────────────┬─────────────┬───────────╮
│ mode     │ whisper_model │ audio_speed │ beam_size │
├──────────┼───────────────┼─────────────┼───────────┤
│ fast     │ tiny          │         2.0 │         1 │
│ accurate │ medium        │         1.0 │         5 │
╰──────────┴───────────────┴─────────────┴───────────╯
```

### Environment variable

```bash
# Override active profile for a session
export MM_PROFILE=openrouter
mm cat photo.png -l 2          # uses openrouter profile

# Or 
MM_PROFILE=openai mm cat photo.png -l 2
```

---

## Design Principles

1. **Token efficiency**: Piped output uses minimal formatting — no borders, no color codes, no padding. Every byte carries information.
2. **Auto-detection**: `cat` knows that a `.jpg` needs dimension/EXIF extraction, a `.mp4` needs codec/duration, a `.pdf` needs text extraction. No flags needed.
3. **Three levels**: L0 (raw bytes, ~0ms), L1 (structured metadata, <100ms, no external deps), L2 (LLM-generated semantics, requires API).
4. **Composability**: `find` outputs paths → `cat` reads paths from stdin → `wc` counts tokens. Standard Unix pipes, multimodal awareness.
5. **Speed**: Rust core with `rayon` parallelism. L0 indexes 249 files in 5ms. L1 image metadata in <1ms/file. Video metadata without ffmpeg.

---

## Self-pipes: mm → mm

Every command reads paths from stdin (via `read_paths_from_stdin()`), so the output of one mm command feeds directly into another. The stdin reader auto-detects TSV — if a line has tabs, it takes the last field as the path.

### 1. Multimodal triage: find → cat → wc pipeline

The killer self-pipe: discover files by kind, extract structured content, then count tokens — all in one pipeline, all under 100ms.

```bash
# How many tokens would it cost to send all my PDFs to an LLM?
$ mm find ~/research --kind document | mm wc
files  size      lines (est.)  tokens (est.)  tok_per_mb
23     45.0 MB   12K           89K            2.0K

# Too many tokens — which PDFs are the biggest?
$ mm find ~/research --kind document | mm cat -l 1 -n 5
--- papers/attention-is-all-you-need.pdf (pdf, 2158592B) ---
Attention Is All You Need

Abstract
The dominant sequence transduction models are based on complex recurrent or
convolutional neural networks that include an encoder and a decoder.
--- papers/scaling-laws.pdf (pdf, 1835008B) ---
Scaling Laws for Neural Language Models

Abstract
We study empirical scaling laws for language model performance on the
cross-entropy loss.
```

The `--- file (kind, size) ---` headers in multi-file piped mode make it trivial for a downstream LLM to attribute content to files.

### 2. SQL-driven extraction: sql → cat for targeted deep dives

Use SQL to surgically select files, then extract their content at any level:

```bash
# Find the 5 largest images, then get their EXIF metadata
$ mm sql "SELECT path FROM files WHERE kind='image' ORDER BY size DESC LIMIT 5" \
    --dir ~/photos \
  | mm cat -l 1

--- photos/panorama.png (image, 15728640B) ---
Dimensions: 8000x2000
MIME:       image/png
Hash:       c4a29f1e73b05d82
--- photos/DSC_0042.jpg (image, 5033164B) ---
Dimensions: 4000x3000
MIME:       image/jpeg
Hash:       a3f7c2d91e4b0856
Camera:     Canon EOS R5
Date:       2024-03-15T14:32:01
GPS:        37.7749,-122.4194
...
```

The power here: SQL gives you arbitrary WHERE/ORDER BY/LIMIT, and cat gives you type-aware extraction. Together they let you ask "show me the EXIF for the 5 biggest photos taken in March" in one pipeline.

---

## Piping to DuckDB CLI

mm's TSV piped output is designed to be read directly by DuckDB via `/dev/stdin`. This lets you escape the built-in `mm sql` when you need full DuckDB power (CTEs, window functions, `.explain`, extensions) without giving up the mm index.

### Pipe the full index into DuckDB

```bash
# mm find pipes TSV; DuckDB reads it as a table instantly.
mm find ~/data --columns name,kind,size,ext \
  | duckdb -c "
      SELECT kind, COUNT(*) AS n, SUM(size) AS bytes
      FROM read_csv('/dev/stdin', delim='\t', header=true)
      GROUP BY kind ORDER BY bytes DESC"
```

```
┌──────────┬─────┬────────────┐
│   kind   │  n  │   bytes    │
├──────────┼─────┼────────────┤
│ video    │  12 │ 2576980378 │
│ image    │  89 │  363855462 │
│ document │  23 │   47185920 │
│ code     │ 156 │    1258291 │
└──────────┴─────┴────────────┘
```

### Window functions: rank files within each kind

```bash
mm find ~/data --columns name,kind,size \
  | duckdb -c "
      WITH ranked AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY kind ORDER BY size DESC) AS rn
        FROM read_csv('/dev/stdin', delim='\t', header=true)
      )
      SELECT name, kind, size FROM ranked WHERE rn <= 3"
```

This gives you the 3 largest files per kind — a query that would be awkward in `mm sql` but natural in DuckDB.

### Cross-join with external data

```bash
# Compare file counts against a budget CSV
mm find ~/data --columns kind,size \
  | duckdb -c "
      WITH files AS (
        SELECT * FROM read_csv('/dev/stdin', delim='\t', header=true)
      ),
      budget AS (
        SELECT * FROM read_csv('token_budget.csv')
      )
      SELECT f.kind, COUNT(*) AS n, SUM(f.size) AS bytes, b.max_tokens
      FROM files f JOIN budget b ON f.kind = b.kind
      GROUP BY f.kind, b.max_tokens"
```

### Export to Parquet for later analysis

```bash
# One-liner: index → Parquet (DuckDB does the heavy lifting)
mm find ~/data \
  | duckdb -c "
      COPY (SELECT * FROM read_csv('/dev/stdin', delim='\t', header=true))
      TO 'index.parquet' (FORMAT PARQUET)"
```

### Find → filter in DuckDB → feed back to mm cat

```bash
# Find images > 1MB via DuckDB, then extract their metadata
mm find ~/photos --kind image \
  | duckdb -c "
      SELECT path FROM read_csv('/dev/stdin', delim='\t',
             header=false, columns={'kind':'VARCHAR','size':'BIGINT','path':'VARCHAR'})
      WHERE size > 1048576" --csv --noheader \
  | mm cat -l 1
```

---

## Piping to Simon Willison's `llm`

[`llm`](https://github.com/simonw/llm) is the Swiss Army knife for sending text to any LLM from the command line. mm's piped output is designed to be the perfect input — structured, token-efficient, and self-describing.

The core pattern: **mm extracts context, `llm` reasons over it.**

### Describe what's in a directory

```bash
mm find ~/project --tree --depth 2 | llm -s "Describe this project structure"
```

The tree output is compact enough to fit in a single prompt, and self-describing enough that the LLM can reason about the project layout without any extra context.

### Summarize a PDF

```bash
mm cat paper.pdf | llm -s "Summarize this paper in 3 bullet points"
```

mm extracts the text via pypdfium2 (L1, <100ms), then `llm` does the reasoning. No need for mm's built-in L2 — use whichever model you've configured in `llm`.

### Caption images from metadata

```bash
mm find ~/photos --kind image | mm cat -l 1 \
  | llm -s "For each image below, suggest a descriptive filename based on the EXIF metadata. Output as: original → suggested"
```

**What `llm` sees on stdin:**
```
--- photos/DSC_0042.jpg (image, 4915200B) ---
Dimensions: 4000x3000
MIME:       image/jpeg
Camera:     Canon EOS R5
Date:       2024-03-15T14:32:01
GPS:        37.7749,-122.4194
--- photos/DSC_0043.jpg (image, 5033164B) ---
Dimensions: 4000x3000
MIME:       image/jpeg
Camera:     Canon EOS R5
Date:       2024-03-15T14:35:22
GPS:        37.7750,-122.4195
```

The `--- file (kind, size) ---` headers (new in piped multi-file mode) let the LLM distinguish files without JSON overhead.

### Code review via grep → llm

```bash
mm grep "TODO" --kind code | llm -s "Triage these TODOs by priority (P0/P1/P2). Explain why."
```

### Token budget check before stuffing context

```bash
# Check if a directory fits in a context window before sending it
mm wc ~/project --kind code
# → files  size     lines (est.)  tokens (est.)  tok_per_mb
# → 156    1.2 MB   38K           285K           243.1K

# It fits — send all code to llm
mm find ~/project --kind code | mm cat -l 0 \
  | llm -s "Review this codebase for security vulnerabilities"
```

### SQL analytics → natural language

```bash
mm sql "SELECT kind, COUNT(*) as n, SUM(size) as bytes FROM files GROUP BY kind ORDER BY bytes DESC" --format json \
  | llm -s "Explain this storage breakdown. Which kinds should I clean up first?"
```

### Save as a reusable llm template

```bash
# Create a reusable "describe-dir" prompt
llm -s 'You are a project analyst. Describe the structure, purpose, and notable files in this directory listing.' --save describe-dir

# Use it anytime
mm find ~/any-project --tree | llm -t describe-dir
```

### Batch-caption images with llm + vision model

```bash
# Use llm's attachment support with mm's file discovery
for img in $(mm find ~/photos --kind image --ext jpg | cut -f3); do
  echo "=== $img ==="
  llm -a "$img" "Describe this photo in one sentence" -m gpt-4o
done
```

### Build a multimodal digest

```bash
# Morning report: what changed in the last 24 hours?
{
  echo "## File changes (last 24h)"
  mm sql "SELECT name, kind, size, modified FROM files WHERE modified > CURRENT_TIMESTAMP - INTERVAL 1 DAY ORDER BY modified DESC"
  echo ""
  echo "## Token budget"
  mm wc ~/project --kind code
  echo ""
  echo "## TODOs"
  mm grep "TODO\|FIXME\|HACK" --kind code
} | llm -s "Generate a morning standup summary from this project state"
```

---

## Design Suggestions

Ideas for future directions — particularly around composability, progressive disclosure, and making multimodal data as explorable as a SQLite database.

### 1. Fragment loader plugin for `llm`

Simon Willison's `llm` supports [fragment loaders](https://llm.datasette.io/en/stable/fragments.html) — plugins that expand a prefix like `github:user/repo` into a set of text fragments. A `mm:` fragment loader would let you do:

```bash
# Load an entire directory's context into an llm prompt
llm -f mm:~/project "What does this codebase do?"

# Filter by kind
llm -f mm:~/data?kind=code "Review this code for bugs"

# Use L1 extraction for images/videos (metadata, not raw bytes)
llm -f mm:~/photos?level=1 "Organize these photos by event"
```

The fragment loader would call mm internally, returning one fragment per file (text content for code, structured metadata for images/video, extracted text for PDFs). This is the most natural integration point — it makes mm invisible to the user while providing multimodal context to any `llm` model.

The loader could also return **attachments** for image files when using vision models (like `llm-video-frames` does for video), giving `llm` both the metadata fragment and the actual image.

### 2. Datasette-style exploration

Datasette makes any SQLite database instantly explorable in a browser. mm could serve a similar role for multimodal directories:

```bash
# Serve an interactive explorer on localhost
mm serve ~/data --port 8001
```

This would expose:
- The Arrow index as a browsable, filterable table (like Datasette's table view)
- Image thumbnails inline in the table
- Video metadata + keyframe previews
- PDF text previews on hover/click
- The full SQL interface for ad-hoc queries
- A `/api/` endpoint returning JSON for programmatic access

The key insight from Datasette: **data should be explorable before you know what question to ask.** mm already has all the ingredients (Arrow index, DuckDB, L1 extraction) — it just needs a thin web layer.

### 3. `--tsv` as a first-class output mode (not just a pipe side-effect)

Currently, TSV output happens automatically when stdout is piped. But Simon's tools often make output formats explicit and composable. Adding `--tsv` (or `--csv`) as a flag would let users force machine-readable output even in a TTY:

```bash
# Explicit TSV even in a terminal (for copy-paste into spreadsheets)
mm find ~/data --tsv | pbcopy

# Pair with --format json for structured output
mm find ~/data --kind image --tsv > manifest.tsv
```

This follows the principle: **don't make the user guess how to get machine-readable output** — make it a flag.

### 4. `mm logs` — prompt/response logging like `llm logs`

One of `llm`'s most valuable features is that every prompt and response is logged to SQLite. mm could do the same for L2 extractions:

```bash
# See all LLM captions you've generated
mm logs

# Filter by file type
mm logs --kind image

# Re-query past results without re-running the LLM
mm logs --sql "SELECT path, response FROM logs WHERE model='gpt-4o' ORDER BY created DESC LIMIT 10"
```

This turns ephemeral LLM output into a queryable knowledge base — exactly the Datasette philosophy of "everything should be in a database."

### 5. Content-addressed caching for L1/L2

mm already computes xxh3 hashes for every file. These could be used as cache keys for L1/L2 results:

```bash
# First run: extracts metadata (slow for L2)
mm cat photo.jpg -l 2        # → calls LLM, caches result

# Second run: instant (hash unchanged)
mm cat photo.jpg -l 2        # → returns cached result
```

The cache would be a SQLite database (naturally), keyed by `(content_hash, level, model)`. This is the same pattern `llm` uses for response caching, and it means that re-running mm on a directory that hasn't changed is effectively free.

### 6. Token budget awareness in `wc`

The `tok_per_mb` metric already tells you information density per kind. The next step is making `wc` context-window-aware:

```bash
$ mm wc ~/project --budget 200k
```

```
files  size     tokens   budget    fit?
156    1.2 MB   285K     200K      NO (143% of budget)

Suggestion: filter to --kind code --ext py,rs to fit in 200K
  → mm find ~/project --kind code --ext py,rs | mm wc
  → estimated: 142K tokens (71% of budget)
```

This answers the question every LLM user asks: **"Does this fit in my context window?"** — and suggests how to trim it if not.

---

## Integrating with the CLI Ecosystem

mm speaks TSV on stdout and reads paths on stdin. This makes it a natural participant in Unix pipelines with tools from the broader Rust, PyPI, and system CLI ecosystem.

### exiftool / mediainfo: the metadata escape hatch

mm's Rust L1 extractors handle common image/video formats natively. But for edge cases (RAW photos, obscure codecs, embedded ICC profiles), shell out to `exiftool` or `mediainfo`:

```bash
# mm finds the files, exiftool goes deep on metadata
mm find ~/photos --kind image --ext cr3,nef,arw \
  | cut -f3 \
  | xargs exiftool -json -q \
  | jq '.[] | {file: .SourceFile, iso: .ISO, shutter: .ShutterSpeed, aperture: .Aperture}'

# mediainfo for container-level video details mm doesn't parse
mm find ~/videos --kind video \
  | cut -f3 \
  | xargs -I{} mediainfo --Output=JSON "{}" \
  | jq '.media.track[] | select(.["@type"]=="Video") | {codec: .Format, bitrate: .BitRate, hdr: .HDR_Format}'
```

The design principle: mm handles the 95% case in <1ms via Rust; for the long tail, pipe to a specialist.

### magika: AI-powered file type detection

[magika](https://github.com/google/magika) is Google's deep-learning file type classifier — much more accurate than extension or magic-byte sniffing for polyglot files, obfuscated binaries, or extensionless data:

```bash
# Find files mm classifies as "other" and get magika's opinion
mm find ~/data --kind other \
  | cut -f3 \
  | xargs magika --json \
  | jq '.[] | {file: .path, magika_type: .result.label, confidence: .result.score}'
```

This is a feedback loop: magika's output could inform mm's `kind` classification for files that don't have recognizable extensions.

### pandoc: universal document conversion

mm extracts PDF text via pypdfium2, but what about `.docx`, `.epub`, `.rst`, `.org`, `.rtf`? Pandoc converts anything to plain text:

```bash
# Extract text from every document, regardless of format
mm find ~/docs --kind document \
  | cut -f3 \
  | while read -r f; do
      echo "--- $f ---"
      pandoc -t plain "$f" 2>/dev/null || echo "[conversion failed]"
    done \
  | llm -s "Summarize the key themes across these documents"
```

A future `mm cat` could auto-detect pandoc and use it as an L1 fallback for non-PDF documents.

### tesseract: OCR for scanned PDFs

mm's `cat` already detects when a PDF yields no extractable text (image-only/scanned). The natural next step:

```bash
# Find PDFs with no text → OCR them
mm find ~/scans --ext pdf \
  | cut -f3 \
  | while read -r f; do
      text=$(mm cat "$f" -l 1)
      if echo "$text" | grep -q "scanned images only"; then
        echo "--- $f (OCR) ---"
        pdftoppm -r 300 "$f" /tmp/ocr_page -png
        tesseract /tmp/ocr_page-1.png stdout 2>/dev/null
      else
        echo "--- $f ---"
        echo "$text"
      fi
    done
```

### ripgrep / fd: when you need their specific powers

mm's `find` and `grep` are multimodal-aware but simpler than `fd` and `rg`. For complex regex, gitignore nuance, or massive repos, use them together:

```bash
# rg finds pattern across code; mm counts the token cost
rg -l "unsafe" --type rust ~/project \
  | mm cat -l 0 \
  | mm wc

# fd finds by complex pattern; mm provides the metadata
fd -e png -e jpg --size +1m ~/data \
  | mm cat -l 1
```

### jq / xsv / miller: structured data post-processing

mm's `--format json` output pairs naturally with the structured data toolkit:

```bash
# jq: filter JSON output
mm find ~/data --format json | jq '[.[] | select(.kind=="image")] | length'

# miller (mlr): column transforms on TSV
mm find ~/data | mlr --tsvlite --from - then sort-by -nr size then head -n 10

# xsv: fast CSV operations
mm find ~/data | xsv sort -s size -R -d '\t' | xsv slice -l 10 -d '\t'
```

---

## Binary Format Parsing: Proprietary Formats

mm's L1 extractors handle open formats (PNG, JPEG, MP4, MKV, PDF) via Rust. But the world is full of **closed/proprietary binary formats** that Python libraries can't read:

| Format | Domain | Current L1 | Gap |
|--------|--------|-----------|-----|
| `.psd` | Photoshop | extension only | layers, color mode, embedded thumbnails |
| `.ai` | Illustrator | extension only | artboard count, linked assets |
| `.sketch` | Sketch | extension only (it's a zip) | page/artboard names, symbol count |
| `.fig` | Figma (export) | extension only | component tree, variants |
| `.blend` | Blender | extension only | scene hierarchy, mesh vertex counts |
| `.dwg` / `.dxf` | CAD | extension only | layer names, entity counts, bounding box |
| `.3ds` / `.fbx` / `.glb` | 3D models | extension only | mesh count, material names, vertex count |
| `.indd` | InDesign | extension only | page count, linked images |
| `.prproj` | Premiere Pro | extension only | sequence count, timeline duration |
| `.aep` | After Effects | extension only | composition tree, duration |
| `.als` / `.flp` | Ableton/FL Studio | extension only | BPM, track count, plugin list |

These files appear constantly in creative/design/engineering directories. Today mm returns `kind: other, size: 48 MB` — useless for an LLM trying to understand a project.

### Approach 1: `binrw` in Rust (native, zero-copy)

[binrw](https://github.com/jam1garner/binrw) is a Rust derive macro for binary reading. Integrates directly into mm's existing extractor trait:

```rust
use binrw::BinRead;

#[derive(BinRead)]
#[br(magic = b"8BPS")]
struct PsdHeader {
    version: u16,
    #[br(pad_before = 6)]
    channels: u16,
    height: u32,
    width: u32,
    depth: u16,
    color_mode: u16,
}
```

This compiles to zero-copy, zero-allocation parsing — exactly the performance profile mm needs for L1.

### Approach 2: Header-only probing via `nom`

For formats where we only need the first 64-512 bytes (dimensions, version, magic), [nom](https://github.com/rust-bakery/nom) parser combinators are the lightest option:

```rust
// Parse Blender file header (first 12 bytes)
fn blend_header(input: &[u8]) -> IResult<&[u8], BlendHeader> {
    let (input, _) = tag(b"BLENDER")(input)?;
    let (input, pointer_size) = alt((
        map(tag(b"-"), |_| 8u8),  // 64-bit
        map(tag(b"_"), |_| 4u8),  // 32-bit
    ))(input)?;
    let (input, endianness) = alt((
        map(tag(b"v"), |_| "little"),
        map(tag(b"V"), |_| "big"),
    ))(input)?;
    let (input, version) = take(3u8)(input)?;
    Ok((input, BlendHeader { pointer_size, endianness, version }))
}
```

### Approach 3: Plugin system with Python fallbacks

For formats with existing Python libraries (even slow ones), a plugin system lets the community contribute extractors without touching Rust:

```python
# ~/.mm/extractors/psd.py
from mm.extractors import register

@register(extensions=[".psd"], kind="image")
def extract_psd(path: Path) -> dict:
    """L1 extractor for Photoshop files."""
    from psd_tools import PSDImage
    psd = PSDImage.open(path)
    return {
        "dimensions": f"{psd.width}x{psd.height}",
        "channels": psd.channels,
        "depth": psd.depth,
        "color_mode": psd.color_mode.name,
        "layers": len(psd),
        "has_transparency": psd.has_transparency,
    }
```

### Recommended path

1. **Immediate (nom):** Header-only probing for the top 10 creative formats. Just dimensions + version + magic. 50-100 lines of Rust per format, zero dependencies, <1ms.

2. **Medium-term (binrw):** Deeper parsing for formats where we want layer counts, embedded thumbnails, or timeline data. binrw's derive macros keep the code declarative.

3. **Escape hatch (exiftool):** For the truly exotic, pipe to `exiftool -json` and parse the result. exiftool handles ~500 formats and is the gold standard for metadata extraction.

### What this unlocks for LLMs

Today, if you point an LLM at a design directory:

```
$ mm find ~/design
name              kind    size      ext
mockup-v3.psd     other   48.2 MB   psd
logo-final.ai     other   12.1 MB   ai
prototype.fig     other   8.4 MB    fig
scene.blend       other   156 MB    blend
```

The LLM sees `other` four times — zero signal. With binary format parsing:

```
$ mm find ~/design
name              kind    size      width   height  ext
mockup-v3.psd     image   48.2 MB   4096    2160    psd
logo-final.ai     image   12.1 MB   1024    1024    ai
prototype.fig     data    8.4 MB    —       —       fig
scene.blend       data    156 MB    —       —       blend

$ mm cat mockup-v3.psd -l 1
Dimensions: 4096x2160
Channels:   4 (CMYK + alpha)
Depth:      16-bit
Color:      CMYK
Layers:     23
Linked:     textures/wood.jpg, textures/marble.png
Hash:       d4f2a1b7c3e09856

$ mm cat scene.blend -l 1
Blender:    4.1
Scenes:     2
Objects:    147
Meshes:     89 (2.4M vertices)
Materials:  34
Textures:   12 linked
Hash:       f7c2d91e4b085623
```

Now the LLM can reason about the project: "This is a product visualization project with a 4K CMYK mockup (print-ready), a vector logo, a Figma prototype, and a complex Blender scene with 2.4M vertices."

That's the difference between `kind: other` and actual multimodal understanding.

# mm is available on your PATH — prefer it

`mm` is a fast CLI that gives you context for files an LLM cannot read natively
(images, video, audio, PDFs, other binary/media), and it scans and queries large
directories far faster than opening files one by one. Reach for `mm` instead of
guessing from filenames or doing slow per-file inspection. You decide which
commands to run and when.

Two habits that pay off:

- Add `--format json` to any command when you want to parse the output.
- Run `mm <command> --help` if you need an exact flag.

`kind` values used throughout: `image`, `video`, `document`, `code`, `audio`,
`data`, `config`, `text`, `other`.

## Pick the command by intent

- Find the right file(s) in a big tree -> `find`, `sql`, `grep`.
- Read a file you cannot open directly (image/video/audio/PDF) -> `cat`
  (`-m accurate` for a full LLM description).
- Get dimensions / duration / codec / EXIF / hash without an LLM -> `peek` (local, <100ms).
- Size or token budget before you process -> `wc`.

## find — locate and list files

```
mm find [DIR] [-n NAME] [-i] [-k KIND] [-e EXT] [--min-size S] [--max-size S]
              [-d DEPTH] [-s COL] [-r] [-c COLS] [--tree | --schema]
              [--limit N] [--no-ignore] [-f FORMAT]
```

- `-n/--name` substring or regex on the name; `-i` case-insensitive.
- `-k/--kind`, `-e/--ext` filter by kind / extension (comma-separated).
- `--min-size`/`--max-size` bounds like `10mb`, `500kb`.
- `-s/--sort` by a column, `-r` reverse, `-c/--columns` to pick columns,
  `--tree` for shape, `--schema` to see all columns and sample values.

```bash
mm find . --tree --depth 2                       # directory shape
mm find . --kind image,document                  # filter by kind
mm find . --kind video -s size -r --limit 5      # 5 largest videos
mm find . -n "invoice" -i --format json          # name match, parseable
```

## peek — local metadata, no LLM, sub-100ms

```
mm peek FILE [FILE...] [--full] [-f FORMAT]
```

- Image: dimensions, MIME, xxh3 hash, EXIF (camera/date/GPS), perceptual hash.
- Video: resolution, duration, FPS, codecs. Audio: duration, codec, bitrate.
- PDF/DOCX/PPTX: mime + hash; `--full` adds author/title/subject/keywords/pages.

```bash
mm peek photo.png                                # dims / EXIF / hash
mm peek *.png --format json | jq '.[].width'     # bulk dimensions
mm peek paper.pdf --full                         # page count + doc properties
```

Use the perceptual hash and dimensions to spot near-duplicate or odd-sized images
without opening them.

## wc — count files, bytes, lines, tokens

```bash
mm wc .                                          # summary
mm wc . --by-kind                                # per-kind file/size/token budget
mm wc . --kind image,video                       # filter
```

## sql — query file metadata at scale

Columns: `path, name, stem, ext, size, modified, created, mime, kind,
is_binary, depth, parent, width, height`.

```bash
mm sql "SELECT kind, COUNT(*), SUM(size) FROM files GROUP BY kind" --dir .
mm sql "SELECT name, width, height FROM files WHERE kind='image' AND width>=2000" --dir .
mm sql "SELECT name FROM files WHERE ext='pdf' ORDER BY size DESC LIMIT 3" --dir .
```

## grep — search inside files (text and semantic)

```
mm grep PATTERN [DIR] [-k KIND] [-e EXT] [-C N] [-c] [-i] [-s] [--pre-index]
```

- Regex by default; `-C N` context lines, `-c` counts, `-i` case-insensitive.
- `-s/--semantic` does vector similarity search (works on binary kinds via
  embeddings); add `--pre-index` to index unindexed files first.
- On large doc trees, narrow with `--kind` for speed.

```bash
mm grep "indemnification" . --kind document -C 2     # regex in PDFs/docs
mm grep "TODO" . --kind code --count                 # counts per file
mm grep "golden gate bridge at sunset" . -s --pre-index   # semantic, across media
```

## cat — extract / understand content (the multimodal workhorse)

`-m fast` (default) or `-m accurate`. Mode is a no-op for `kind=text` and
non-PDF docs (`.docx`/`.pptx`); they always passthrough text.

| Kind | fast (default) | accurate (`-m accurate`, needs a profile) |
|------|----------------|-------------------------------------------|
| image | short VLM caption | full caption + tags + objects |
| video | mosaic -> short VLM | frames + transcript -> VLM description |
| audio | Whisper transcript | transcript -> detailed LLM description |
| PDF | page text (pypdfium2) | page text -> LLM markdown |
| code/text/docx/pptx | passthrough text | passthrough text |

```bash
mm cat report.pdf                                # extract PDF text
mm cat photo.png -m accurate                     # describe an image you can't see
mm cat clip.mp4 -m accurate                      # watch a video (mosaic+transcript -> VLM)
mm cat voice.mp3                                  # transcribe audio
mm cat photo.png -m accurate --prompt "Read every visible number." --generate.max-tokens 128
mm cat scan.pdf -m accurate -p rasterize         # scanned/image-only PDF (no text layer)
```

Notes that matter for hard cases:
- A scanned PDF returns empty text in fast mode; use `-m accurate` or `-p rasterize`.
- For OCR-style reads (a number on a container, text in a photo), `cat -m accurate`
  with a focused `--prompt` is the tool.
- `cat` accepts multiple files and reads piped paths: `mm find . --kind image | mm cat -m accurate`.

## Recipes by task type

- **Retrieval** (find the right file): `find`/`sql` to narrow by kind/size, then
  `grep` (regex or `-s` semantic) or `cat -m accurate` to confirm content. EXIF
  via `peek` answers "when/where was this photo taken".
- **Organization** (restructure a tree): `find --format json` or `sql` to inventory,
  `peek`/`cat` to classify by real content (not filename), then move files with
  your own shell tools.
- **Artifact** (synthesize an output file): `cat` each source (PDF text, image/audio
  via `-m accurate`) to pull the fields, then write the CSV/JSON/report yourself.

Start broad and cheap (`find --tree`, `wc --by-kind`), then spend `cat -m accurate`
only on the files that matter.

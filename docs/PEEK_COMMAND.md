# mm peek

Surface locally-extracted file metadata — dimensions, EXIF, codec, duration, content hash — directly from the file, without any LLM calls or cache reads.

Use `peek` for **"what is this file?"**. Use [`cat`](CAT_COMMAND.md) for **"what does this file say?"**.

## Synopsis

```bash
mm peek FILE [FILE ...] [OPTIONS]
```

## Options

| Flag | Short | Type | Description |
|------|-------|------|-------------|
| `--full` | | flag | Include all document metadata fields (author, title, subject, keywords, creator, producer, pages). Off by default. |
| `--format FORMAT` | `-f` | enum | Output format: `rich`, `json`, `pretty-json`, `tsv`, `csv` |

## Metadata fields

Fields populated depend on the file kind. All formats emit the same flat column set; fields not applicable to a given kind are `null`.

### Universal fields

| Field | Description |
|-------|-------------|
| `name` | Filename |
| `kind` | File kind: `image`, `video`, `audio`, `document`, `code`, `text`, `data`, `config`, `other` |
| `size` | File size in bytes |
| `mime` | MIME type inferred from extension |
| `magic_mime` | MIME type detected by content inspection (magika). Shown only when it differs from `mime`. |
| `content_hash` | xxh3 content hash (hex) |

### Image fields

| Field | Description |
|-------|-------------|
| `dimensions` | `WxH` pixel dimensions |
| `phash` | Perceptual hash (16-digit hex) for similarity detection |
| `exif_camera` | Camera make and model |
| `exif_date` | Date/time original from EXIF |
| `exif_gps` | GPS coordinates (lat, lon) |
| `exif_orientation` | EXIF orientation tag |

### Video fields

| Field | Description |
|-------|-------------|
| `dimensions` | `WxH` pixel resolution |
| `duration_s` | Duration in seconds |
| `fps` | Frames per second |
| `video_codec` | Video codec (e.g. `h264`, `av1`) |
| `audio_codec` | Audio codec (e.g. `aac`, `opus`) |
| `has_audio` | Whether an audio track is present |

### Audio fields

| Field | Description |
|-------|-------------|
| `duration_s` | Duration in seconds |
| `audio_codec` | Audio codec |

### Document fields (always shown)

| Field | Description |
|-------|-------------|
| `mime` | MIME type |
| `content_hash` | Content hash |

### Document fields (`--full` only)

| Field | Description |
|-------|-------------|
| `pages` | Page count |
| `doc_author` | Document author |
| `doc_title` | Document title |
| `doc_subject` | Document subject |
| `doc_keywords` | Document keywords |
| `doc_creator` | Creating application |
| `doc_producer` | PDF producer |

## Examples

```bash
# basic image metadata
mm peek photo.png

# video metadata
mm peek clip.mp4

# audio metadata
mm peek recording.mp3

# PDF with full document metadata
mm peek paper.pdf --full

# multi-file inspection
mm peek *.png --format tsv

# multi-file JSON output
mm peek photo.png clip.mp4 paper.pdf --format json

# pipe-friendly TSV
mm peek photo.png --format tsv
```

## Rich panel output

In TTY mode the default output is a Rich panel per file, showing only populated fields. `None` fields are hidden to keep output dense and scannable.

A typical image panel:

```
╭─── photo.jpg ───╮
│ kind       image │
│ size       2.4 MB│
│ mime   image/jpeg│
│ hash   a3f2...   │
│ dimensions 4032x3024 │
│ camera  iPhone 15 Pro │
│ date  2024-03-15 14:22 │
│ gps  37.7749° N, 122.4194° W │
╰──────────────────╯
```

## Performance

`peek` is always a direct, fresh scan — no cache reads, no database. Every invocation re-reads the file.

Video metadata uses native Rust parsers (`mp4parse` for MP4/MOV, `matroska` for MKV/WebM) — no `ffmpeg` dependency for `peek`. Duration, codec, and resolution are extracted in under 100 ms.

## Notes

- `peek` accepts paths from stdin when piped (one path per line).
- `--full` only adds document-specific fields; it has no effect on images, video, or audio.
- `magic_mime` is displayed only when it differs from the extension-inferred `mime` — a discrepancy indicates a misnamed or modified file.
- `phash` is available for images only. Displayed as a 16-digit hex string.
- GPS coordinates are shown when present in EXIF; many photos from modern smartphones include them.

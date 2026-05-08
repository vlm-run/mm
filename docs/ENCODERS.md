# Encoders

Encoders transform media files into OpenAI-compatible Message dicts ready for VLM chat/completions APIs. Each encoder is registered via `@register_encoder` and can be used with `mm cat -p <name>`.

```
file → encoder → [{"role": "user", "content": [...]}] → LLM (if pipeline has generate step)
```

## Current Encoders

### Image

| Name | Description | Parameters |
|------|-------------|------------|
| `image-resize` | Resize to bounding box, base64 encode. Uses Rust fast-path when available, Pillow fallback. EXIF orientation applied. | `max_width=1024` |
| `image-tile` | Resized overview + tile crops in a single message. Gives VLMs both global context and fine detail. Falls back to overview-only when image fits in one tile. | `max_width=1024` |

#### `image-resize`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  img["🖼️ image"]:::input

  subgraph encode ["Encode"]
    exif["EXIF orient"]:::encode
    resize["Resize"]:::encode
  end

  msg["1 Message\n(1 image_url)"]:::output

  img --> exif --> resize --> msg

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `image-tile`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  img["🖼️ image"]:::input

  subgraph encode ["Encode"]
    exif["EXIF orient"]:::encode
    overview["Resize overview image\n(global context)"]:::encode
    tiles["Crop NxM tile images\n(fine detail)"]:::encode
  end

  msg["1 Message\n(tile metadata + overview image\n+ N tile images)"]:::output

  img --> exif
  exif --> overview
  exif --> tiles
  overview --> msg
  tiles --> msg

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```


### Video

| Name | Description | Parameters |
|------|-------------|------------|
| `video-mosaic` | Scene-aware frame extraction + tiled mosaic grids. Default for fast mode. Uses PySceneDetect when available, falls back to uniform sampling. | `tile_cols=4`, `tile_rows=4`, `thumb_width=160`, `num_mosaics=8`, `num_frames=128` |
| `video-mosaic-w-transcript` | `video-mosaic` + Whisper transcript prepended. | + transcript opts |
| `video-frames` | Extract frames at N fps via parallel ffmpeg seeking, batch into messages (max 16 frames each). Text header with time range per batch. | `fps=1.0`, `max_width=1024`, `max_frames_per_message=16` |
| `video-frames-w-transcript` | Frame sampling + Whisper audio transcription. Transcript yielded first as context, then batched frames. Default for accurate mode. Falls back to frame-only when Whisper is unavailable. | `fps=1.0`, `max_width=1024`, `max_frames_per_message=16`, `whisper_model=medium`, `language=auto`, `audio_speed=1.0` |
| `video-keyframes` | Extract I-frames (keyframes) directly from the video bitstream. | `max_keyframes=None`, `max_width=1024`, `max_keyframes_per_message=16` |
| `video-keyframes-w-transcript` | `video-keyframes` + Whisper transcript prepended. | + transcript opts |
| `video-shots` | PySceneDetect shot detection, extract representative frames per shot. One message per shot. | `threshold=27.0`, `max_frames_per_shot=8`, `max_width=1024` |
| `video-shots-w-transcript` | `video-shots` + Whisper transcript prepended. | + transcript opts |
| `video-shot-mosaic` | PySceneDetect shot detection, build a mosaic grid per shot. One message per shot. | `threshold=27.0`, `tile_cols=4`, `tile_rows=4`, `thumb_width=160` |
| `video-shot-mosaic-w-transcript` | `video-shot-mosaic` + Whisper transcript prepended. | + transcript opts |
| `video-chunks` | Split into overlapping time-based chunks, extract frames per chunk. One message per chunk with time range header. | `chunk_duration=60`, `overlap=20`, `max_width=1024`, `frames_per_chunk=16` |
| `video-clips` | Base64-encode video clips of uniform duration (no frame extraction). | `duration=0`, `max_size_mb=None` |
| `video-clips-w-transcript` | `video-clips` + Whisper transcript prepended. | + transcript opts |
| `video-summary` | Adaptive N-frame visual summary of a video. | `num_frames=12`, `use_scene_detection=True`, `max_width=1024` |
| `video-summary-w-transcript` | `video-summary` + Whisper transcript prepended. | + transcript opts |
| `video-transcript` | Whisper transcript only (no frames / no images). | `whisper_model=medium`, `language=auto`, `audio_speed=1.0` |
| `video-captions` | Extract embedded subtitle stream from video; falls back to Whisper. | `subtitle_stream=0`, `fallback_to_whisper=True`, `whisper_model=medium`, `language=auto`, `audio_speed=1.0` |
| `video-gemini` | Gemini native `inline_data` passthrough. Sends the entire video file. Rust fast-path with Python fallback. | — |
| `video-gemini-chunked` | Gemini passthrough with duration-based chunking via ffmpeg. Each chunk as a separate Gemini Part. | `max_seconds=120`, `overlap=10` |

#### `video-mosaic`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  video["🎬 video"]:::input

  subgraph encode ["Encode"]
    detect["Scene detect\n(or uniform)"]:::encode
    frames["Extract\nN frames"]:::encode
    tile["Tile into\n4x4 mosaics"]:::encode
  end

  msg["1 Message\n(text + mosaic\nimages)"]:::output

  video --> detect --> frames --> tile --> msg

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `video-frames`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  video["🎬 video"]:::input

  subgraph encode ["Encode"]
    ts["Uniform timestamps\nat fps"]:::encode
    ffmpeg["ffmpeg seek\n+ extract"]:::encode
    batch["Batch ≤16\nframes/msg"]:::encode
  end

  msgs["N Messages\n(text header\n+ frame images)"]:::output

  video --> ts --> ffmpeg --> batch --> msgs

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `video-frames-w-transcript`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  video["🎬 video"]:::input

  subgraph encode ["Encode"]
    direction TB
    audio["ffmpeg\nextract audio"]:::encode
    whisper["Whisper\ntranscribe"]:::encode
    frames["Extract frames\nat fps"]:::encode
    batch["Batch ≤16\nframes/msg"]:::encode
  end

  transcript["Msg 1:\ntranscript"]:::output
  frame_msgs["Msgs 2..N:\nframe batches"]:::output

  video --> audio --> whisper --> transcript
  video --> frames --> batch --> frame_msgs

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `video-chunks`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  video["🎬 video"]:::input

  subgraph encode ["Encode"]
    split["Split by duration\n(overlap)"]:::encode
    c1["Chunk 1\n16 frames"]:::encode
    c2["Chunk 2\n16 frames"]:::encode
    c3["Chunk N\n16 frames"]:::encode
  end

  m1["Message 1"]:::output
  m2["Message 2"]:::output
  m3["Message N"]:::output

  video --> split
  split --> c1 --> m1
  split --> c2 --> m2
  split --> c3 --> m3

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `video-shots`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  video["🎬 video"]:::input

  subgraph encode ["Encode"]
    detect["PySceneDetect\nshot boundaries"]:::encode
    s1["Shot 1\n≤8 frames"]:::encode
    s2["Shot 2\n≤8 frames"]:::encode
    s3["Shot N\n≤8 frames"]:::encode
  end

  m1["Message 1"]:::output
  m2["Message 2"]:::output
  m3["Message N"]:::output

  video --> detect
  detect --> s1 --> m1
  detect --> s2 --> m2
  detect --> s3 --> m3

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `video-shot-mosaic`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  video["🎬 video"]:::input

  subgraph encode ["Encode"]
    detect["PySceneDetect\nshot boundaries"]:::encode
    s1["Shot 1 frames\n→ tile mosaic"]:::encode
    s2["Shot 2 frames\n→ tile mosaic"]:::encode
    s3["Shot N frames\n→ tile mosaic"]:::encode
  end

  m1["Message 1\n(mosaic grid)"]:::output
  m2["Message 2\n(mosaic grid)"]:::output
  m3["Message N\n(mosaic grid)"]:::output

  video --> detect
  detect --> s1 --> m1
  detect --> s2 --> m2
  detect --> s3 --> m3

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `video-gemini`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  video["🎬 video"]:::input

  subgraph encode ["Encode"]
    read["Read file bytes\n(Rust fast-path)"]:::encode
    b64["Base64 encode\ninline_data"]:::encode
  end

  msg["1 Message\n(Gemini Part)"]:::output

  video --> read --> b64 --> msg

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `video-gemini-chunked`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  video["🎬 video"]:::input

  subgraph encode ["Encode"]
    probe["Probe duration"]:::encode
    c1["ffmpeg segment\nChunk 1"]:::encode
    c2["ffmpeg segment\nChunk 2"]:::encode
    c3["ffmpeg segment\nChunk N"]:::encode
  end

  m1["Message 1\n(Gemini Part)"]:::output
  m2["Message 2\n(Gemini Part)"]:::output
  m3["Message N\n(Gemini Part)"]:::output

  video --> probe
  probe --> c1 --> m1
  probe --> c2 --> m2
  probe --> c3 --> m3

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

### Audio

| Name | Description | Parameters |
|------|-------------|------------|
| `audio-base64` | Send the raw audio file as a base64-encoded `input_audio` part. Default for Python `Context.to_messages()`. | `format` (auto-detected from extension) |
| `audio-transcribe` | Extract audio via ffmpeg, transcribe with Whisper (lightning-whisper-mlx / faster-whisper). Returns timestamped transcript as text message. | `whisper_model=medium`, `language=auto`, `audio_speed=1.0`, optional `backend`/`base_url`/`api_key` for remote |
| `audio-gemini` | Gemini native `inline_data` passthrough for audio files. Splits into overlapping chunks for files longer than `max_seconds`. | `max_seconds=120`, `overlap=10` |

#### `audio-transcribe`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  audio["🎵 audio"]:::input

  subgraph encode ["Encode"]
    extract["ffmpeg\nextract audio"]:::encode
    whisper["Whisper\ntranscribe"]:::encode
    fmt["Format timestamped\nsegments"]:::encode
  end

  msg["1 Message\n(text transcript)"]:::output

  audio --> extract --> whisper --> fmt --> msg

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `audio-gemini`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  audio["🎵 audio"]:::input

  subgraph encode ["Encode (short ≤120s)"]
    read["Read file bytes"]:::encode
    b64["Base64 encode\ninline_data"]:::encode
  end

  subgraph encode2 ["Encode (long >120s)"]
    probe["Probe duration"]:::encode
    c1["ffmpeg segment\nChunk 1"]:::encode
    c2["ffmpeg segment\nChunk N"]:::encode
  end

  msg1["1 Message\n(Gemini Part)"]:::output
  msgN["N Messages\n(Gemini Parts)"]:::output

  audio --> read --> b64 --> msg1
  audio --> probe
  probe --> c1 --> msgN
  probe --> c2 --> msgN

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
  style encode2 fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

### Document

| Name | Description | Parameters |
|------|-------------|------------|
| `document-page-text` | Text-per-page extraction from PDF/DOCX/PPTX as structured text messages (no rasterization). Default for fast mode. Much lighter than `rasterize`. | `pages_per_message=4`, `max_pages=None` |
| `document-rasterize` | Render PDF pages as JPEG images via pypdfium2, batch into messages. Text header with page range per batch. | `max_width=1024`, `pages_per_message=4`, `max_pages=None` |
| `document-rasterize-text` | Rasterize pages + interleave extracted text after each image. Useful when VLM benefits from OCR fallback. | `max_width=1024`, `pages_per_message=4`, `max_pages=None` |
| `document-gemini` | Gemini native `inline_data` passthrough. Sends the entire document file. Rust fast-path with Python fallback. | — |

#### `document-page-text`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  doc["📄 PDF/DOCX/PPTX"]:::input

  subgraph encode ["Encode"]
    open["Open document\n(pypdfium2 / docx)"]:::encode
    extract["Extract text\nper page"]:::encode
    batch["Batch ≤4\npages/msg"]:::encode
  end

  msgs["N Messages\n(text per page\nbatch)"]:::output

  doc --> open --> extract --> batch --> msgs

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `document-rasterize`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  doc["📄 PDF"]:::input

  subgraph encode ["Encode"]
    open["Open PDF\n(pypdfium2)"]:::encode
    render["Render pages\nas JPEG"]:::encode
    batch["Batch ≤4\npages/msg"]:::encode
  end

  msgs["N Messages\n(text header\n+ page images)"]:::output

  doc --> open --> render --> batch --> msgs

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `document-rasterize-text`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  doc["📄 PDF"]:::input

  subgraph encode ["Encode"]
    open["Open PDF\n(pypdfium2)"]:::encode
    render["Render pages\nas JPEG"]:::encode
    text["Extract text\nper page"]:::encode
    interleave["Interleave\nimage + text"]:::encode
    batch["Batch ≤4\npages/msg"]:::encode
  end

  msgs["N Messages\n(image + text\nper page)"]:::output

  doc --> open
  open --> render --> interleave
  open --> text --> interleave
  interleave --> batch --> msgs

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

#### `document-gemini`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  doc["📄 document"]:::input

  subgraph encode ["Encode"]
    read["Read file bytes\n(Rust fast-path)"]:::encode
    b64["Base64 encode\ninline_data"]:::encode
  end

  msg["1 Message\n(Gemini Part)"]:::output

  doc --> read --> b64 --> msg

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
```

---

## Planned Encoders

### Image

| Name | Description | Parameters |
|------|-------------|------------|
| `image-crop-grid` | Fixed NxM grid crop (e.g. 3x3). Unlike `tile` which uses fixed pixel size, this always produces exactly N\*M tiles regardless of image dimensions. | `rows=3`, `cols=3`, `max_width=1024` |
| `image-metadata` | EXIF metadata, dimensions, and histogram stats as a structured text message. Analysis without sending pixel data. | `include_exif=true`, `include_histogram=false` |

### Video

| Name | Description | Parameters |
|------|-------------|------------|
| `video-transcript` | Extract audio → Whisper transcription only, no visual frames. For podcasts, talks, interviews. | `whisper_model=medium`, `audio_speed=1.0` |

### Document

| Name | Description | Parameters |
|------|-------------|------------|
| `document-ocr` | OCR fallback for scanned/image-only PDFs where pypdfium2 returns empty text. Rasterize then OCR via tesseract or VLM. | `max_width=1024`, `ocr_engine=tesseract`, `max_pages=None` |

---

## Writing Custom Encoders

Drop a `.py` file in `encoders/image/`, `encoders/video/`, or `~/.config/mm/encoders/`. Use the `@register_encoder` decorator:

```python
from pathlib import Path
from mm.encoders import register_encoder

@register_encoder(name="my-custom", media_types=("video",))
def my_custom(path: Path, **kw):
    yield {"role": "user", "content": [
        {"type": "text", "text": f"Processing {path.name}"}
    ]}
```

### Multi-chunk encoders

Encoders that yield multiple Messages (e.g. one per video shot) are processed sequentially via `generate_chunked`. Each Message gets its own LLM call and results are concatenated. This avoids OOM from loading all chunks into memory simultaneously.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'primaryColor': '#e8f4fd', 'primaryBorderColor': '#4a90d9', 'lineColor': '#666'}}}%%
graph LR
  video["🎬 video"]:::input

  subgraph encode ["Encode"]
    s1["Shot 1"]:::encode
    s2["Shot 2"]:::encode
    s3["Shot N"]:::encode
  end

  subgraph generate ["Generate"]
    g1["LLM"]:::generate
    g2["LLM"]:::generate
    g3["LLM"]:::generate
  end

  concat["Concat"]:::output
  out["stdout"]:::output

  video --> s1
  video --> s2
  video --> s3
  s1 --> g1
  s2 --> g2
  s3 --> g3
  g1 --> concat
  g2 --> concat
  g3 --> concat
  concat --> out

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef generate fill:#fce4ec,stroke:#e57373,stroke-width:1.5px,color:#6a1b1b,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
  style generate fill:#fff0f0,stroke:#ef9a9a,stroke-width:1px,rx:10
```

### Encoder Protocol

```python
class MessageStrategy(Protocol):
    name: str
    media_types: tuple[str, ...]

    def encode(self, path: Path, **kwargs) -> Iterable[Message]:
        ...
```

Where `Message = dict[str, Any]` is an OpenAI-compatible message dict: `{"role": "user", "content": [...]}`.

---

## Gaps

Python's `FileKind` recognizes 5 kinds (`image`, `video`, `audio`, `document`, `text`) while the Rust core recognizes 9 (`Code`, `Image`, `Document`, `Video`, `Audio`, `Data`, `Config`, `Text`, `Other`). The Python `file_kind()` function collapses `code`, `data`, `config`, and `other` into `text`. Pipelines only exist for image, video, audio, and document — text and code files pass through as raw content without an encoder or pipeline.

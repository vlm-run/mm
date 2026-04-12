# Encoders

Encoders transform media files into OpenAI-compatible Message dicts ready for VLM chat/completions APIs. Each encoder is registered via `@register_encoder` and can be used with `mm cat -p <name>`.

```
file → encoder → [{"role": "user", "content": [...]}] → LLM (if pipeline has generate step)
```

## Current Encoders

### Image (2)

| Name | Description | Parameters |
|------|-------------|------------|
| `image-resize` | Resize to bounding box, base64 encode. Uses Rust fast-path when available, Pillow fallback. EXIF orientation applied. | `max_width=1024` |
| `image-tile` | Resized overview + tile crops in a single message. Gives VLMs both global context and fine detail. Falls back to overview-only when image fits in one tile. | `max_width=1024` |

### Video (8)

| Name | Description | Parameters |
|------|-------------|------------|
| `video-mosaic` | Scene-aware frame extraction + tiled mosaic grids. Default for fast mode. Uses PySceneDetect when available, falls back to uniform sampling. | `tile_cols=4`, `tile_rows=4`, `thumb_width=160`, `num_mosaics=8`, `num_frames=128` |
| `video-frame-sample` | Extract frames at N fps via parallel ffmpeg seeking, batch into messages (max 16 frames each). Text header with time range per batch. | `fps=1.0`, `max_width=1024`, `max_frames_per_message=16` |
| `video-frames-transcript` | Frame sampling + Whisper audio transcription. Transcript yielded first as context, then batched frames. Default for accurate mode. Falls back to frame-only when Whisper is unavailable. | `fps=1.0`, `max_width=1024`, `max_frames_per_message=16`, `whisper_model=medium`, `language=auto`, `audio_speed=1.0` |
| `video-chunk` | Split into overlapping time-based chunks, extract frames per chunk. One message per chunk with time range header. | `chunk_duration=60`, `overlap=20`, `max_width=1024`, `frames_per_chunk=16` |
| `video-shot-frames` | PySceneDetect shot detection, extract representative frames per shot. One message per shot, processed sequentially to avoid OOM. | `threshold=27.0`, `max_frames_per_shot=8`, `max_width=1024` |
| `video-shot-mosaic` | PySceneDetect shot detection, build a mosaic grid per shot via `tile_frames_to_mosaics`. One message per shot. | `threshold=27.0`, `tile_cols=4`, `tile_rows=4`, `thumb_width=160` |
| `video-gemini` | Gemini native `inline_data` passthrough. Sends the entire video file. Rust fast-path with Python fallback. | — |
| `video-gemini-chunked` | Gemini passthrough with duration-based chunking via ffmpeg. Each chunk as a separate Gemini Part. | `max_seconds=120`, `overlap=10` |

### Audio (2)

| Name | Description | Parameters |
|------|-------------|------------|
| `audio-transcribe` | Extract audio via ffmpeg, transcribe with Whisper (lightning-whisper-mlx / faster-whisper). Returns timestamped transcript as text message. | `whisper_model=medium`, `language=auto`, `audio_speed=1.0` |
| `audio-gemini` | Gemini native `inline_data` passthrough for audio files. Splits into overlapping chunks for files longer than `max_seconds`. | `max_seconds=120`, `overlap=10` |

### Document (4)

| Name | Description | Parameters |
|------|-------------|------------|
| `document-page-text` | Text-per-page extraction from PDF/DOCX/PPTX as structured text messages (no rasterization). Default for fast mode. Much lighter than `rasterize`. | `pages_per_message=4`, `max_pages=None` |
| `document-rasterize` | Render PDF pages as JPEG images via pypdfium2, batch into messages. Text header with page range per batch. | `max_width=1024`, `pages_per_message=4`, `max_pages=None` |
| `document-rasterize-text` | Rasterize pages + interleave extracted text after each image. Useful when VLM benefits from OCR fallback. | `max_width=1024`, `pages_per_message=4`, `max_pages=None` |
| `document-gemini` | Gemini native `inline_data` passthrough. Sends the entire document file. Rust fast-path with Python fallback. | — |

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

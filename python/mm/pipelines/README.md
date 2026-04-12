# mm Pipelines

Pipelines configure a 2-stage flow for LLM-based media understanding:
**encode** (via an encoder) then **generate** (LLM call) to produce text output.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'lineColor': '#666'}}}%%
graph LR
  file["Media File"]:::input

  subgraph encode ["Encode"]
    encoder["Encoder"]:::encode
  end

  subgraph generate ["Generate"]
    llm["MLLM"]:::generate
  end

  out["stdout"]:::output

  file --> encoder --> llm --> out

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef generate fill:#fce4ec,stroke:#e57373,stroke-width:1.5px,color:#6a1b1b,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
  style generate fill:#fff0f0,stroke:#ef9a9a,stroke-width:1px,rx:10
```

Each pipeline is a YAML file under `pipelines/{kind}/{mode}.yaml` that references
an encoder from `mm/encoders/` and configures LLM generation parameters.

```bash
mm cat photo.jpg -p resize          # named encoder
mm cat video.mp4 -p shot-mosaic     # scene-aware video encoder

# Override pipeline config from CLI
mm cat photo.jpg -m accurate --encode.strategy tile-overview
mm cat photo.jpg -m accurate --generate.max-tokens 1024 --generate.temperature 0.5

# Load explicit pipeline YAML (repeatable, dispatched by kind)
mm cat photo.jpg -p ~/my-image-pipeline.yaml
mm cat *.jpg *.mp4 -p image.yaml -p video.yaml

# Custom Python transform via pyfunc
mm cat photo.jpg -m accurate --encode.pyfunc ~/my_filter.py
```

## Built-in Encoders

### Image

| Name | Location | Description | Key Params |
|------|----------|-------------|------------|
| `resize` | [`encoders/image/__init__.py`](../encoders/image/__init__.py) | Fit image to bounding box (default 1024px), base64 JPEG. Rust fast-path with Pillow fallback. | `max_width` |
| `tile` | [`encoders/image/__init__.py`](../encoders/image/__init__.py) | Split image into `tile_size x tile_size` tiles, one Message per tile. | `tile_size` |
| `tile-overview` | [`encoders/image/tile_overview.py`](../encoders/image/tile_overview.py) | Resized overview + all tiles in a single Message. E.g. 4096px image -> 1 overview + 16 tiles = 17 images. | `max_width` |

### Video

| Name | Location | Description | Key Params |
|------|----------|-------------|------------|
| `frame-sample` | [`encoders/video/__init__.py`](../encoders/video/__init__.py) | Extract frames at N fps via parallel ffmpeg seeking, batch into Messages (max 16 frames each). | `fps`, `max_width`, `max_frames_per_message` |
| `video-chunk` | [`encoders/video/__init__.py`](../encoders/video/__init__.py) | Split video into overlapping time chunks (default 60s), extract frames per chunk. One Message per chunk. | `chunk_duration`, `overlap`, `max_width`, `frames_per_chunk` |
| `shot-frames` | [`encoders/video/shot.py`](../encoders/video/shot.py) | Detect shots via PySceneDetect, extract representative frames per shot, yield one Message per shot. Sequential to avoid OOM. | `threshold`, `max_frames_per_shot`, `max_width` |
| `shot-mosaic` | [`encoders/video/shot.py`](../encoders/video/shot.py) | Detect shots via PySceneDetect, build a mosaic grid per shot using `tile_frames_to_mosaics`. One Message per shot. | `threshold`, `tile_cols`, `tile_rows`, `thumb_width` |
| `gemini-video` | [`encoders/gemini.py`](../encoders/gemini.py) | Pass entire video as Gemini `inline_data` Part. Single Message. Rust fast-path. | -- |
| `gemini-video-chunked` | [`encoders/gemini.py`](../encoders/gemini.py) | Chunk video by duration (default 120s), each chunk as Gemini `inline_data`. | `max_seconds`, `overlap` |

### Document

| Name | Location | Description | Key Params |
|------|----------|-------------|------------|
| `rasterize` | [`encoders/document.py`](../encoders/document.py) | Render PDF pages as JPEG images via pypdfium2, batch 4 pages per Message. | `max_width`, `pages_per_message`, `max_pages` |
| `rasterize-text` | [`encoders/document.py`](../encoders/document.py) | Same as rasterize but interleaves extracted text alongside each page image. | `max_width`, `pages_per_message`, `max_pages` |
| `gemini-doc` | [`encoders/gemini.py`](../encoders/gemini.py) | Pass entire document as Gemini `inline_data` Part. Rust fast-path. | -- |

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

## Encoder Protocol

```python
class MessageStrategy(Protocol):
    name: str
    media_types: tuple[str, ...]

    def encode(self, path: Path, **kwargs) -> Iterable[Message]:
        ...
```

Where `Message = dict[str, Any]` is an OpenAI-compatible message dict: `{"role": "user", "content": [...]}`.

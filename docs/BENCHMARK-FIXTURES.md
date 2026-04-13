# `mm` Benchmark Fixtures

## Dataset 
We use the following 2 datasets for benchmarking:
 - [mmbench-tiny](https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz) - 5 files, 42.4MB
 - [mmbench-mini](https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-mini.tar.gz) - 44 files, 1.3GB


## Image Examples
```bash
# Extract images quickly
uv run mm cat input.png
# Multi-image extraction (batch=auto)
uv run mm cat images/*.png
# Extract images accurately (with VLMs)
uv run mm cat input.png -m accurate
```

## Custom Image Pipeline

```bash
# Custom image tiling (for extra-large resolution images)
uv run mm cat input.png --encode.strategy tile
# Custom image resizing (for smaller resolution images)
uv run mm cat input.png --encode.strategy resize --mode accurate
```

## Document Examples

```bash
# Extract PDF documents quickly
uv run mm cat input.pdf
# Extract multiple PDF documents quickly (batch=auto)
uv run mm cat *.pdf
# Extract PDF documents accurately (with VLMs)
# Uses batched VLM inference (batch=auto) - each page is rasterized
uv run mm cat input.pdf -m accurate
# Extract non-PDF documents accurately (with VLMs)
# Uses single VLM inference (batch=1)
uv run mm cat input.docx -m accurate
# Extract per-page text only (no rasterization, no VLM)
uv run mm cat input.pdf --encode.strategy page-text
# Rasterize pages and interleave extracted text (hybrid, batch=auto)
uv run mm cat input.pdf --encode.strategy rasterize-text -m accurate
```

## Audio Examples
```bash
# Extract audio quickly (Whisper transcript, default model=medium)
uv run mm cat input.mp3
# Extract audio accurately (Whisper transcript + LLM summary)
uv run mm cat input.mp3 -m accurate
# Extract audio accurately (pass audio directly to a Gemini-compatible VLM)
uv run mm cat input.mp3 --encode.strategy audio-gemini -m accurate
```

## Video Examples
```bash
# Extract video quickly
uv run mm cat input.mp4
# Extract video accurately (with VLMs)
uv run mm cat input.mp4 -m accurate
# Extract video accurately (frame-sample encoder at fps=1)
uv run mm cat input.mp4 --encode.strategy frame-sample -m accurate

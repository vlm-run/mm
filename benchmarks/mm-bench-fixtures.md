# `mm` Benchmark Fixtures

## Dataset 
We use the following 2 datasets for benchmarking:
 - [mmbench-tiny](https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-tiny.tar.gz)
 - [mmbench-mini](https://storage.googleapis.com/vlm-data-public-prod/mmbench/mmbench-mini.tar.gz)


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
uv run mm cat input.png --encoder.strategy image-tiled
# Custom image resizing (for smaller resolution images)
uv run mm cat input.png --encoder.strategy resize --mode accurate
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
# Uses OCR inference (batch=1)
uv run mm cat input.pdf --encoder.strategy ocr -m accurate
```

## Video Examples
```bash
# Extract video quickly
uv run mm cat input.mp4
# Extract video accurately (with VLMs)
uv run mm cat input.mp4 -m accurate
# Extract video accurately (with video chunking)
uv run mm cat input.mp4 --encoder.strategy video-chunk -m accurate
```

        - cat
            - pipelines
                - PDF
                    - doc -> pages -> concat txt
                    - doc -> enc=docling-markdown/html -> txt
                    - doc -> pages -> image (batch=4) -> vlm summary -> concat txt (with page id)
                    - doc -> pages -> image (batch=1) -> glm-ocr -> concat txt (with page id)
                - image
                    - img -> enc=blip -> txt (w/ vocab lookup)
                    - Img -> enc=orion -> txt
                - video
                - audio

```

### mmbench-mini

- 45 files, 588MB
- 10 images, 10 videos, 10 audio files, 10 documents
- 10 code files
- 10 text files
- 10 config files
- 10 data files
- 10 other files
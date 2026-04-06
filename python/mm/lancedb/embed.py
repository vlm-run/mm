"""Embedding generation for mm via the mm inference server.

The server at /embeddings accepts google.genai Part dicts and returns vectors.
This avoids leaking API keys into the CLI.

Supported content types:
  - Text: any string
  - Image: PNG, JPEG (max 6 per request)
  - Audio: MP3, WAV (max 80s)
  - Video: MP4, MOV (max 120s — longer videos are chunked)
  - Document: PDF (max 6 pages)
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from google.genai import types

# Gemini embedding limits
_VIDEO_MAX_SECONDS = 120
_VIDEO_OVERLAP_SECONDS = 10
_AUDIO_MAX_SECONDS = 80
_AUDIO_OVERLAP_SECONDS = 5
_EMBEDDINGS_PATH = "/embeddings"


# ---------------------------------------------------------------------------
# Part constructors — return validated google.genai types.Part dicts
# ---------------------------------------------------------------------------


def text_part(text: str) -> dict[str, Any]:
    """Construct a text Part."""
    return types.Part(text=text).to_json_dict()


def image_part(path: Path) -> dict[str, Any]:
    """Construct an image Part from a file path."""
    return types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type=_mime_for(path, fallback="image/png"),
    ).to_json_dict()


def _audio_part(path: Path) -> dict[str, Any]:
    """Construct an audio Part from a file path (max 80s)."""
    return types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type=_mime_for(path, fallback="audio/mpeg"),
    ).to_json_dict()


def audio_parts(path: Path) -> list[dict[str, Any]]:
    """Chunk audio into overlapping segments and return Parts.

    Each segment is extracted via ffmpeg. For audio <=80s, returns a single Part.
    """
    from mm.ffmpeg import extract_segment, probe_duration

    duration_s = probe_duration(path)
    if duration_s <= _AUDIO_MAX_SECONDS:
        return [_audio_part(path)]

    import tempfile

    parts: list[dict[str, Any]] = []
    step = _AUDIO_MAX_SECONDS - _AUDIO_OVERLAP_SECONDS
    start = 0.0
    while start < duration_s:
        end = min(start + _AUDIO_MAX_SECONDS, duration_s)
        with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
            seg_path = Path(tmp.name)
        extract_segment(str(path), str(seg_path), start, end)
        parts.append(_audio_part(seg_path))
        seg_path.unlink(missing_ok=True)
        start += step
    return parts


def document_part(path: Path) -> dict[str, Any]:
    """Construct a document Part from a PDF (max 6 pages)."""
    return types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type="application/pdf",
    ).to_json_dict()


def _video_part(path: Path) -> dict[str, Any]:
    """Construct a video Part from a file (max 120s)."""
    return types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type=_mime_for(path, fallback="video/mp4"),
    ).to_json_dict()


def video_parts(path: Path) -> list[dict[str, Any]]:
    """Chunk a video into overlapping segments and return Parts.

    Each segment is extracted via ffmpeg and returned as a separate Part.
    For videos <=120s, returns a single Part.
    """
    from mm.ffmpeg import probe_duration

    duration_s = probe_duration(path)
    if duration_s <= _VIDEO_MAX_SECONDS:
        return [_video_part(path)]

    import tempfile

    from mm.ffmpeg import extract_segment

    parts: list[dict[str, Any]] = []
    step = _VIDEO_MAX_SECONDS - _VIDEO_OVERLAP_SECONDS
    start = 0.0

    while start < duration_s:
        end = min(start + _VIDEO_MAX_SECONDS, duration_s)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            seg_path = Path(tmp.name)
        extract_segment(str(path), str(seg_path), start, end)

        parts.append(_video_part(seg_path))
        seg_path.unlink(missing_ok=True)
        start += step

    return parts


# ---------------------------------------------------------------------------
# Server communication
# ---------------------------------------------------------------------------


def embed_parts(parts: list[dict[str, Any]]) -> list[list[float]]:
    """Send Parts to the server and return embedding vectors."""
    import httpx

    from mm import __version__
    from mm.profile import DEFAULTS

    url = DEFAULTS["base_url"] + _EMBEDDINGS_PATH
    response = httpx.post(
        url,
        json=parts,
        headers={"User-Agent": f"mm-ctx/{__version__}", "Content-Type": "application/json"},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of text strings via the server."""
    return embed_parts([text_part(t) for t in texts])


# ---------------------------------------------------------------------------
# High-level: embed L2 chunks for a file
# ---------------------------------------------------------------------------


def embed_file_chunks(
    uri: str,
    content_hash: str,
    profile: str,
    model: str,
    *,
    embed_model: str = "gemini-embedding-2-preview",
) -> int:
    """Embed all chunks for a file's L2 result. Returns number of chunks embedded."""
    from mm.lancedb.db import MmDatabase, _esc
    from mm.lancedb.schema import ChunkCol

    db = MmDatabase()
    ct = db._chunks_table()
    where = (
        f"{ChunkCol.URI} = '{_esc(uri)}' "
        f"AND {ChunkCol.CONTENT_HASH} = '{_esc(content_hash)}' "
        f"AND {ChunkCol.PROFILE} = '{_esc(profile)}' "
        f"AND {ChunkCol.MODEL} = '{_esc(model)}'"
    )
    results = ct.search().where(where).to_arrow()
    if results.num_rows == 0:
        return 0

    import pyarrow.compute as pc

    indices = pc.sort_indices(results.column(ChunkCol.CHUNK_IDX))
    sorted_results = results.take(indices)
    texts: list[str] = [
        sorted_results.column(ChunkCol.CHUNK_TEXT)[i].as_py()
        for i in range(sorted_results.num_rows)
    ]

    vectors = embed_texts(texts)
    db.upsert_embeddings(uri, content_hash, profile, model, embed_model, vectors)
    return len(vectors)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mime_for(path: Path, fallback: str) -> str:
    return mimetypes.guess_type(path.name)[0] or fallback

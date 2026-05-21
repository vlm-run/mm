"""High-performance video reader backed by PyAV.

Replaces subprocess-based ffmpeg/ffprobe calls with in-process decoding
for frame extraction, keyframe reading, and metadata probing. Provides
a streaming ``FrameStream`` API that supports three consumption patterns:

    # Iterate one frame at a time (constant memory)
    for frame in reader.frames(timestamps, width=1024):
        process(frame)

    # Materialize to list (small extractions)
    frames = reader.frames(timestamps, width=1024).collect()

    # Batch for encoder messages
    for batch in reader.frames(timestamps, width=1024).batched(16):
        yield build_message(batch)

Audio extraction and segment copying remain ffmpeg CLI operations
where stream-copy outperforms re-encoding.
"""

from __future__ import annotations

import base64
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from PIL import Image

from mm.cache import memoize_file

logger = logging.getLogger(__name__)

_JPEG_QUALITY = 85
# 4:2:0 chroma subsampling halves JPEG encode time (and bytes) vs 4:4:4
# without perceptible quality loss for VLM thumbnails. PIL accepts:
#   0 → 4:4:4, 1 → 4:2:2, 2 → 4:2:0  (or "keep" / -1 to copy from source)
_JPEG_SUBSAMPLING = 2


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """Container-level metadata read via PyAV. No subprocess."""

    path: Path
    duration: float
    fps: float
    width: int
    height: int
    num_frames: int
    codec: str
    has_audio: bool


@dataclass(frozen=True, slots=True)
class Frame:
    """A decoded video frame with its timestamp.

    Lightweight value object — holds a PIL Image and the presentation
    timestamp in seconds. Provides convenience methods for encoding
    to base64 JPEG (the format all video encoders need).
    """

    timestamp: float
    image: Image.Image

    def encode_jpeg(
        self,
        quality: int = _JPEG_QUALITY,
        *,
        subsampling: int = _JPEG_SUBSAMPLING,
    ) -> tuple[str, str]:
        """Encode to base64 JPEG string.

        Args:
            quality: JPEG quality 1-95 (default 85).
            subsampling: Chroma subsampling — 0=4:4:4, 1=4:2:2, 2=4:2:0
                (default). 4:2:0 is ~1.7× faster than 4:4:4 and produces
                ~30% smaller payloads with no visible loss for VLM use.

        Returns:
            ``(base64_str, "image/jpeg")`` tuple ready for ``_image_part()``.
        """
        img = self.image
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, subsampling=subsampling)
        return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"


class FrameStream:
    """Lazy, parallel-batched frame stream with three consumption modes.

    Internally decodes frames in parallel batches (one ``av.open()``
    per worker thread). Callers choose how to consume:

        for frame in stream:          # one at a time
        frames = stream.collect()     # materialize all
        for batch in stream.batched(n):  # fixed-size chunks
    """

    __slots__ = ("_factory", "_count")

    def __init__(
        self,
        factory: Callable[[], Iterator[Frame]],
        count: int,
    ) -> None:
        self._factory = factory
        self._count = count

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Iterator[Frame]:
        return self._factory()

    def collect(self) -> list[Frame]:
        """Materialize all frames into a list.

        Use for small, bounded extractions (summaries, per-shot frames).
        For large timestamp sets, prefer iteration or ``.batched()``.
        """
        return list(self._factory())

    def batched(self, n: int) -> Iterator[list[Frame]]:
        """Yield fixed-size batches of frames.

        Each batch is decoded in parallel before being yielded.
        Maps directly to encoder ``max_frames_per_message`` patterns.
        """
        batch: list[Frame] = []
        for frame in self._factory():
            batch.append(frame)
            if len(batch) >= n:
                yield batch
                batch = []
        if batch:
            yield batch


@dataclass
class AudioResult:
    """Result of audio extraction (kept for Whisper compatibility)."""

    path: Path
    duration_s: float
    speed: float
    sample_rate: int
    channels: int


def pyav_runnable() -> bool:
    """Check if PyAV is runnable"""
    try:
        import av  # noqa: F401

        return True
    except (ImportError, OSError):
        return False


@memoize_file(maxsize=64)
def probe(path: str | Path) -> VideoInfo:
    """Read video metadata via PyAV.

    Cached **in process memory** via :func:`mm.cache.memoize_file` —
    the same path with the same mtime returns instantly on subsequent
    calls. ~7 ms cold, ~0 ms warm vs ~58 ms for an ``ffprobe``
    subprocess.

    Disk caching is intentionally not used here: the in-memory hit is
    already a few microseconds, while a disk lookup (file open + pickle
    load) costs ~5 ms — almost the same as the cold compute.  Only the
    expensive helpers (``detect_scenes`` at ~3 s, ``transcript_messages``
    at ~76 s) graduate to the disk-backed cache.
    """
    import av

    p = Path(path)
    container = av.open(str(p))
    try:
        stream = container.streams.video[0]
        has_audio = len(container.streams.audio) > 0
        duration = container.duration / av.time_base if container.duration else 0.0
        return VideoInfo(
            path=p,
            duration=duration,
            fps=float(stream.average_rate) if stream.average_rate else 0.0,
            width=stream.width,
            height=stream.height,
            num_frames=stream.frames or 0,
            codec=stream.codec_context.name,
            has_audio=has_audio,
        )
    finally:
        container.close()


def _resize_to_pil(frame: Any, width: int | None) -> Image.Image:
    """Convert an AVFrame to a PIL Image, resizing in-decoder when possible.

    Uses ``frame.reformat(width, height)`` (libswscale) instead of decoding
    to PIL and then calling ``Image.resize`` — ~3× faster per frame.
    """
    if width and frame.width > width:
        new_h = int(frame.height * width / frame.width)
        # ``Frame.reformat`` rescales via libswscale and stays in YUV until
        # the final ``to_image`` step.  The default scaler (BILINEAR) is
        # good enough for thumbnail-sized VLM input; for higher fidelity
        # callers can post-process with PIL.
        frame = frame.reformat(width=width, height=new_h)
    return frame.to_image()


def _seek_and_decode_one(
    path: str,
    timestamp: float,
    width: int | None,
) -> Frame:
    """Open container, seek to timestamp, decode one frame, close.

    Each call opens its own container so this is safe for parallel
    execution in a ThreadPoolExecutor. PyAV releases the GIL during
    decoding so threads achieve real parallelism.
    """
    import av

    container = av.open(path)
    try:
        stream = container.streams.video[0]
        # ``stream.time_base`` is a Fraction at runtime; convert once so we can
        # do plain float arithmetic (and keep ty happy without per-line ignores).
        time_base = float(stream.time_base) if stream.time_base else 0.0
        target_pts = int(timestamp / time_base) if time_base else 0
        container.seek(target_pts, backward=True, stream=stream)
        for frame in container.decode(stream):
            if frame.pts is not None and frame.pts >= target_pts:
                img = _resize_to_pil(frame, width)
                actual_ts = frame.pts * time_base
                return Frame(timestamp=actual_ts, image=img)
        return Frame(timestamp=timestamp, image=Image.new("RGB", (1, 1)))
    finally:
        container.close()


def _decode_timestamps_batched(
    path: str,
    timestamps: list[float],
    width: int | None,
    max_workers: int,
    internal_batch: int,
) -> Iterator[Frame]:
    """Decode frames in parallel batches to bound memory.

    Processes ``internal_batch`` timestamps at a time via parallel seek,
    yielding decoded frames one by one. Peak memory is bounded to
    ``internal_batch`` frames regardless of total timestamp count.
    """
    for i in range(0, len(timestamps), internal_batch):
        batch_ts = timestamps[i : i + internal_batch]
        batch_indexed = list(enumerate(batch_ts))
        batch_indexed.sort(key=lambda x: x[1])

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                (orig_idx, pool.submit(_seek_and_decode_one, path, ts, width))
                for orig_idx, ts in batch_indexed
            ]

        results: list[tuple[int, Frame]] = []
        for orig_idx, future in futures:
            results.append((orig_idx, future.result()))

        results.sort(key=lambda x: x[0])
        for _, frame in results:
            yield frame


class VideoReader:
    """High-performance video reader backed by PyAV.

    Context manager that provides fast frame extraction via parallel
    seeking, keyframe iteration, and container metadata — all without
    subprocess overhead or temp file I/O.

    Example::

        with VideoReader("video.mp4") as reader:
            print(reader.info)  # VideoInfo

            # 12-frame summary
            frames = reader.frames([10, 30, 60, 90], width=1024).collect()

            # Stream 1fps frames in batches of 16
            for batch in reader.frames(ts_list, width=1024).batched(16):
                for f in batch:
                    b64, mime = f.encode_jpeg()
    """

    __slots__ = ("_path", "_info", "_max_workers")

    def __init__(
        self,
        path: str | Path,
        *,
        max_workers: int = 8,
    ) -> None:
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"Video not found: {self._path}")
        self._info = probe(self._path)
        self._max_workers = max_workers

    def __enter__(self) -> VideoReader:
        return self

    def __exit__(self, *exc: Any) -> None:
        pass

    def __repr__(self) -> str:
        i = self._info
        return (
            f"VideoReader({self._path.name!r}, "
            f"{i.duration:.1f}s, {i.width}x{i.height}, {i.fps:.1f}fps)"
        )

    @property
    def info(self) -> VideoInfo:
        """Container metadata (duration, fps, resolution, codec)."""
        return self._info

    @property
    def duration(self) -> float:
        return self._info.duration

    @property
    def fps(self) -> float:
        return self._info.fps

    @property
    def width(self) -> int:
        return self._info.width

    @property
    def height(self) -> int:
        return self._info.height

    def frames(
        self,
        timestamps: list[float],
        *,
        width: int | None = None,
    ) -> FrameStream:
        """Extract frames at specific timestamps via parallel seeking.

        Returns a ``FrameStream`` that decodes frames on demand using
        parallel container opens (one per worker thread). Frames are
        yielded in the same order as the input timestamps.

        Args:
            timestamps: Presentation times in seconds.
            width: Resize to this width (preserving aspect ratio).
                ``None`` keeps original resolution.

        Returns:
            A ``FrameStream`` supporting iteration, ``.collect()``,
            and ``.batched(n)``.
        """
        path_str = str(self._path)
        workers = self._max_workers
        internal_batch = workers * 4

        def factory() -> Iterator[Frame]:
            return _decode_timestamps_batched(
                path_str,
                timestamps,
                width,
                workers,
                internal_batch,
            )

        return FrameStream(factory, count=len(timestamps))

    def keyframes(
        self,
        *,
        width: int | None = None,
        max_frames: int | None = None,
    ) -> FrameStream:
        """Decode only I-frames from the video bitstream.

        Uses ``skip_frame='NONKEY'`` to skip all non-keyframes at the
        demuxer level — much faster than decoding every frame.

        Args:
            width: Resize width (``None`` keeps original).
            max_frames: Cap the number of keyframes returned.

        Returns:
            A ``FrameStream`` of I-frames in presentation order.
        """
        path_str = str(self._path)

        def factory() -> Iterator[Frame]:
            return _decode_keyframes(path_str, width, max_frames)

        count = self._count_keyframes() if max_frames is None else max_frames
        return FrameStream(factory, count=count)

    def _count_keyframes(self) -> int:
        """Quick I-frame count via demux-level skip."""
        import av

        container = av.open(str(self._path))
        try:
            stream = container.streams.video[0]
            stream.codec_context.skip_frame = "NONKEY"
            count = 0
            for packet in container.demux(stream):
                for _ in packet.decode():
                    count += 1
            return count
        finally:
            container.close()


def _decode_keyframes(
    path: str,
    width: int | None,
    max_frames: int | None,
) -> Iterator[Frame]:
    """Decode only I-frames using codec-level skip."""
    import av

    container = av.open(path)
    try:
        stream = container.streams.video[0]
        stream.codec_context.skip_frame = "NONKEY"
        time_base = float(stream.time_base) if stream.time_base else 0.0
        count = 0
        for packet in container.demux(stream):
            for frame in packet.decode():
                if max_frames is not None and count >= max_frames:
                    return
                img = _resize_to_pil(frame, width)
                ts = frame.pts * time_base if frame.pts is not None else 0.0
                yield Frame(timestamp=ts, image=img)
                count += 1
    finally:
        container.close()


def tile_to_mosaic(
    images: list[Image.Image],
    *,
    cols: int = 4,
    rows: int = 4,
    thumb_width: int = 160,
) -> Image.Image:
    """Tile PIL Images into a mosaic grid. Pure Pillow, no ffmpeg.

    Args:
        images: List of PIL Images to tile.
        cols: Grid columns.
        rows: Grid rows.
        thumb_width: Width of each thumbnail cell.

    Returns:
        A single mosaic ``Image.Image`` in RGB mode.
    """
    thumb_height = int(thumb_width * 9 / 16)

    mosaic = Image.new("RGB", (cols * thumb_width, rows * thumb_height), (0, 0, 0))
    for idx, img in enumerate(images[: cols * rows]):
        resized = img.copy()
        resized.thumbnail((thumb_width, thumb_height))
        col = idx % cols
        row = idx // cols
        x = col * thumb_width
        y = row * thumb_height
        mosaic.paste(resized, (x, y))

    return mosaic


def probe_subtitle_streams(path: str | Path) -> list[dict[str, Any]]:
    """Inspect subtitle streams via PyAV (no ffprobe subprocess)."""
    import av

    container = av.open(str(path))
    try:
        streams: list[dict[str, Any]] = []
        for s in container.streams:
            if s.type == "subtitle":
                meta: dict[str, Any] = {
                    "index": s.index,
                    "codec_name": s.codec_context.name if s.codec_context else None,
                    "codec_type": "subtitle",
                }
                if hasattr(s, "metadata"):
                    meta["tags"] = dict(s.metadata)
                streams.append(meta)
        return streams
    finally:
        container.close()

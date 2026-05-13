from pathlib import Path
from typing import Literal


def extract_meta(path: Path, kind: str, *, no_cache: bool = False) -> str:
    """Produce the metadata-tier content for a file (no LLM call) with caching."""
    from mm.store.utils import get_content_hash, shared_db

    content_hash = get_content_hash(path)
    if not no_cache and content_hash:
        cached = shared_db().get_file_content(content_hash)
        if cached is not None:
            return cached

    def _handler() -> str:
        if kind == "image":
            return _local_image(path)
        if kind == "video":
            return _local_video(path)
        if kind == "audio":
            return _local_audio(path)
        if kind == "document":
            return _local_document(path)
        return path.read_text(errors="replace")

    result = _handler()
    if content_hash and result and not result.startswith("["):
        from mm.store.schema import FileCol

        shared_db().put_file_content(
            str(path.resolve()),
            {
                FileCol.CONTENT_HASH: content_hash,
                FileCol.TEXT_PREVIEW: result,
            },
        )
    return result


def _local_image(path: Path) -> str:
    try:
        from mm._mm import Scanner
        from mm.display import format_size

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_metadata(path.name)
        parts: list[str] = []
        if r.dimensions:
            parts.append(f"Dimensions: {r.dimensions}")
        if r.magic_mime:
            parts.append(f"MIME:       {r.magic_mime}")
        if size_str := format_size(path.stat().st_size):
            parts.append(f"Size:       {size_str}")
        if r.content_hash:
            parts.append(f"Hash:       {r.content_hash}")
        if r.phash is not None:
            parts.append(f"pHash:      {r.phash:016x}")
        if r.exif_camera:
            parts.append(f"Camera:     {r.exif_camera}")
        if r.exif_date:
            parts.append(f"Date:       {r.exif_date}")
        if r.exif_gps:
            parts.append(f"GPS:        {r.exif_gps}")
        if r.exif_orientation:
            parts.append(f"Orientation: {r.exif_orientation}")
        return "\n".join(parts) if parts else f"[Image: {path.name}]"
    except Exception as e:
        return f"[Image extraction failed: {e}]"


def _local_video(path: Path) -> str:
    """Metadata only — no ffmpeg, <100ms."""
    try:
        from mm._mm import Scanner
        from mm.display import format_size

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_metadata(path.name)
        parts: list[str] = []
        if r.dimensions:
            parts.append(f"Resolution: {r.dimensions}")
        if r.duration_s is not None:
            mins, secs = divmod(r.duration_s, 60)
            parts.append(f"Duration:   {int(mins)}m {secs:.1f}s ({r.duration_s:.2f}s)")
        if size_str := format_size(path.stat().st_size):
            parts.append(f"Size:       {size_str}")
        if r.fps:
            parts.append(f"FPS:        {r.fps}")
        if r.video_codec:
            parts.append(f"Video:      {r.video_codec}")
        if r.audio_codec:
            parts.append(f"Audio:      {r.audio_codec}")
        elif r.has_audio is False:
            parts.append("Audio:      none")
        if r.content_hash:
            parts.append(f"Hash:       {r.content_hash}")
        return "\n".join(parts) if parts else f"[Video: {path.name}]"
    except Exception as e:
        return f"[Video extraction failed: {e}]"


def _local_audio(path: Path) -> str:
    """Metadata only — no ffmpeg, <100ms."""
    try:
        from mm._mm import Scanner
        from mm.display import format_size

        scanner = Scanner(str(path.parent))
        scanner.scan()
        r = scanner.extract_metadata(path.name)
        parts: list[str] = []
        if r.duration_s is not None:
            mins, secs = divmod(r.duration_s, 60)
            parts.append(f"Duration: {int(mins)}m {secs:.1f}s ({r.duration_s:.2f}s)")
        if size_str := format_size(path.stat().st_size):
            parts.append(f"Size:     {size_str}")
        if r.audio_codec:
            parts.append(f"Codec:    {r.audio_codec}")
        if r.content_hash:
            parts.append(f"Hash:     {r.content_hash}")
        return "\n".join(parts) if parts else f"[Audio: {path.name}]"
    except Exception as e:
        return f"[Audio extraction failed: {e}]"


def _local_document(path: Path) -> str:
    """Extract document content."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _local_pdf(path)

    try:
        from mm.constants import OFFICE_EXTS

        if ext in OFFICE_EXTS:
            from mm._mm import office_content

            return office_content(str(path))
        else:
            return path.read_text(errors="replace")
    except Exception as e:
        return f"[Document extraction failed for {path.name}: {e}]"


def _local_pdf(path: Path) -> str:
    """Fallback PDF text extraction via pypdfium2."""
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        pages_text: list[str] = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            pages_text.append(textpage.get_text_range())
            textpage.close()
            page.close()
        pdf.close()
        text = "\n\n".join(pages_text).strip()
        if not text:
            return "[No extractable text — this PDF may contain scanned images only]"
        return text
    except Exception as e:
        return f"[PDF extraction failed: {e}]"


def extract_text(path: Path, kind: Literal["document", "text"]) -> tuple[str, bool | None]:
    """``mm cat`` passthrough path — mode-agnostic."""
    from mm.store.utils import get_content_hash, shared_db

    content = extract_meta(path, kind)
    if not content or content.startswith("["):
        return content, None

    content_hash = get_content_hash(path)
    if not content_hash:
        return content, None

    db = shared_db()
    if db.has_text_chunks(content_hash):
        return content, True

    try:
        db.put_text_chunks(
            uri=str(path.resolve()),
            content_hash=content_hash,
            content=content,
        )
    except Exception as e:
        from mm.display import console

        console.print(f"Chunking failed for {content_hash}: {e}")

    return content, None

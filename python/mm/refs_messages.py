"""Driver for :meth:`mm.Context.to_messages` — converts role-aware items
into OpenAI-/Gemini-compatible message lists.

The hot-path encoder invocation still lives in Python because the
registered encoders own PIL / ffmpeg / pypdfium2 calls. The Rust side
owns item storage, ref generation, and (in the future) any Rust-native
encoders; this module is the narrow bridge.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Literal
from urllib.parse import urlparse

from mm.cache import memoize_file

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from mm.context import Context


OPENAI_DEFAULT_ENCODERS: dict[str, str] = {
    "image": "resize",
    "video": "mosaic",
    "document": "rasterize",
    "audio": "base64",
}


def build_messages(
    ctx: "Context",
    *,
    format: Literal["openai", "gemini"],
    encoders: dict[str, str],
    encoder_kwargs: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build a role-aware message list for ``ctx``.

    Args:
        ctx: Incremental context.
        format: ``"openai"`` (default) or ``"gemini"``.
        encoders: Per-kind encoder name overrides.
        encoder_kwargs: Per-kind kwargs forwarded to encoder ``encode()``.

    Returns:
        OpenAI returns one message per consecutive role run. Gemini
        returns a single user turn with non-user roles folded into
        labelled text because Gemini role semantics differ.
    """
    ekw = encoder_kwargs or {}
    if format == "openai":
        return _build_openai_messages(ctx, encoders=encoders, encoder_kwargs=ekw)

    parts: list[dict[str, Any]] = []
    for item in ctx.items():
        role = item.get("role", "user")
        if role != "user":
            parts.append({"text": f"[role={role}]"})
        for part in _parts_for_item(item, format="openai", encoders=encoders, encoder_kwargs=ekw):
            parts.append(_adapt_part(part, format=format))
    return [{"role": "user", "parts": parts}]


def _build_openai_messages(
    ctx: "Context",
    *,
    encoders: dict[str, str],
    encoder_kwargs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    current_role: str | None = None
    for item in ctx.items():
        role = item.get("role", "user")
        if current_role is not None and role != current_role:
            messages.append({"role": current_role, "content": parts})
            parts = []
        current_role = role
        for part in _parts_for_item(
            item, format="openai", encoders=encoders, encoder_kwargs=encoder_kwargs
        ):
            parts.append(_adapt_part(part, format="openai"))
    if current_role is not None:
        messages.append({"role": current_role, "content": parts})
    return messages


def _parts_for_item(
    item: dict[str, Any],
    *,
    format: str,
    encoders: dict[str, str],
    encoder_kwargs: dict[str, dict[str, Any]] | None = None,
) -> Iterable[dict[str, Any]]:
    meta = item.get("metadata") or {}
    ref_id = item["ref_id"]
    kind = item["kind"]
    ekw = (encoder_kwargs or {}).get(kind, {})

    note_line = _build_metadata_text(ref_id, meta)
    if note_line:
        yield {"type": "text", "text": note_line}

    src_kind = item["source_kind"]
    src_value = item["source_value"]

    if kind == "text" or (src_kind == "path" and kind in ("code", "config", "data")):
        if src_kind == "in_memory":
            text = item.get("desc") or ""
        else:
            text = _read_text_or_placeholder(src_kind, src_value)
        if text:
            yield {"type": "text", "text": text}
        return

    if src_kind == "url" and kind == "image" and format == "openai":
        _validate_image_url(src_value)
        yield {"type": "image_url", "image_url": {"url": src_value}}
        return

    if src_kind == "path":
        yield from _encode_path(Path(src_value), kind, encoders=encoders, extra_kwargs=ekw)
        return

    if src_kind == "in_memory":
        yield from _encode_in_memory(
            item, ref_id, kind, format=format, encoders=encoders, extra_kwargs=ekw
        )
        return

    # URL fallback (non-image / Gemini) — surface as text reference.
    yield {"type": "text", "text": f"[ref={ref_id}] remote {kind}: {src_value}"}


def _build_metadata_text(ref_id: str, meta: dict[str, Any]) -> str:
    """Render metadata as a compact ``[ref=...] note: ...`` text block."""
    if not meta:
        return f"[ref={ref_id}]"
    bits: list[str] = [f"[ref={ref_id}]"]
    if "note" in meta:
        bits.append(str(meta["note"]))
    elif "summary" in meta:
        bits.append(str(meta["summary"]))
    extras: list[str] = []
    for k, v in meta.items():
        if k in ("note", "summary"):
            continue
        extras.append(f"{k}={v}")
    if extras:
        bits.append("(" + ", ".join(extras) + ")")
    return " ".join(bits)


def _validate_image_url(url: str) -> None:
    """Validate that *url* is a well-formed HTTP(S) URL pointing to image content.

    Performs a lightweight HEAD request (2 s timeout) and checks the
    ``Content-Type`` header. Raises :class:`~mm.errors.ImageURLError` on
    any failure so the caller gets a 400-level error with a clear message
    instead of an opaque 500 from the downstream gateway.
    """
    from mm.errors import ImageURLError

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ImageURLError(url, f"unsupported scheme {parsed.scheme!r}; expected http or https")
    if not parsed.netloc:
        raise ImageURLError(url, "missing host")

    try:
        import httpx

        resp = httpx.head(url, timeout=2.0, follow_redirects=True)
    except Exception as exc:
        raise ImageURLError(url, f"fetch failed: {exc}") from exc

    if resp.status_code == 404:
        raise ImageURLError(url, "URL returned 404 Not Found")
    if resp.status_code == 403:
        raise ImageURLError(url, "URL returned 403 Forbidden")
    if resp.status_code == 401:
        raise ImageURLError(url, "URL returned 401 Unauthorized")
    if resp.status_code >= 400:
        raise ImageURLError(url, f"URL returned HTTP {resp.status_code}")

    content_type = resp.headers.get("content-type", "")
    if content_type and not content_type.startswith("image/"):
        raise ImageURLError(
            url,
            f"expected an image content type, got {content_type!r}",
        )
    logger.debug("image URL validated: %s [%s]", url, content_type)


def _read_text_or_placeholder(src_kind: str, src_value: str) -> str:
    if src_kind == "path":
        try:
            return Path(src_value).read_text(errors="replace")
        except OSError:
            return ""
    if src_kind == "url":
        return f"<remote text {src_value}>"
    return ""


@memoize_file(maxsize=128)
def _encode_path_cached(
    path: Path,
    kind: str,
    strategy_override: str | None,
    kwargs_items: tuple[tuple[str, Any], ...],
) -> list[dict[str, Any]]:
    """Resolve the encoder for *path* and flatten its output into parts."""
    from mm.encoders import get as get_encoder
    from mm.encoders.auto_strategy import auto_strategy

    strategy_name = strategy_override or auto_strategy(path)
    try:
        strategy = get_encoder(strategy_name, kind)
    except KeyError:
        return []
    return [
        part
        for msg in strategy.encode(path, **dict(kwargs_items))
        for part in msg.get("content", [])
    ]


def _encode_path(
    path: Path,
    kind: str,
    *,
    encoders: dict[str, str] | None = None,
    extra_kwargs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    override = (encoders or {}).get(kind)
    kwargs_items = tuple(sorted((extra_kwargs or {}).items()))
    return _encode_path_cached(path, kind, override, kwargs_items)


def _encode_in_memory(
    item: dict[str, Any],
    ref_id: str,
    kind: str,
    *,
    format: str,
    encoders: dict[str, str],
    extra_kwargs: dict[str, Any] | None = None,
) -> Iterable[dict[str, Any]]:
    desc = item.get("desc") or ""
    if kind != "image":
        yield {"type": "text", "text": f"[ref={ref_id}] in-memory {kind}: {desc}"}
        return

    from mm.context import Context as _CtxType  # noqa: F401 -- for hints only

    obj = _lookup_via_stored_obj(item)
    if obj is None:
        yield {"type": "text", "text": f"[ref={ref_id}] in-memory image: {desc}"}
        return

    try:
        path = _spool_image(obj)
    except Exception as exc:  # noqa: BLE001
        yield {
            "type": "text",
            "text": f"[ref={ref_id}] in-memory image (encode failed: {exc})",
        }
        return
    try:
        yield from _encode_path(path, "image", encoders=encoders, extra_kwargs=extra_kwargs)
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def _lookup_via_stored_obj(item: dict[str, Any]) -> Any:
    """We don't have a ctx handle here, so rely on the caller threading
    the object through ``item["_obj"]`` when needed.

    Current in-memory items route via :meth:`Context.get` upstream if
    needed; for now, the driver passes ``None`` and emits a descriptive
    text block. Hooking the PIL object through will land when we add a
    proper `ItemsIterator` API.
    """
    return item.get("_obj")


def _spool_image(obj: Any) -> Path:
    """Save a PIL.Image or raw bytes to a tempfile for encoder consumption."""
    from PIL import Image as PILImage  # lazy to keep import cheap

    if isinstance(obj, PILImage.Image):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        obj.save(tmp.name, format="PNG")
        tmp.close()
        return Path(tmp.name)
    if isinstance(obj, (bytes, bytearray, memoryview)):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(bytes(obj))
        tmp.close()
        return Path(tmp.name)
    raise TypeError(f"cannot spool {type(obj).__name__} to a temp file")


def _adapt_part(part: dict[str, Any], *, format: str) -> dict[str, Any]:
    """Convert an OpenAI content part to the target format.

    The registered encoders already emit OpenAI-shaped parts; this is a
    thin adapter for the Gemini ``inline_data`` case.
    """
    if format == "openai":
        return part
    if format == "gemini":
        # Already-adapted parts pass through unchanged.
        if "inline_data" in part or ("text" in part and "type" not in part):
            return part
        if part.get("type") == "image_url":
            url = part.get("image_url", {}).get("url", "")
            if url.startswith("data:"):
                meta, _, b64 = url.partition(",")
                mime = meta.removeprefix("data:").split(";")[0]
                return {"inline_data": {"mime_type": mime, "data": b64}}
            return {"inline_data": {"mime_type": "image/jpeg", "data": url}}
        if part.get("type") == "input_audio":
            audio_data = part.get("input_audio", {})
            fmt = audio_data.get("format", "mp3")
            mime_map = {
                "mp3": "audio/mpeg",
                "wav": "audio/wav",
                "flac": "audio/flac",
                "ogg": "audio/ogg",
                "m4a": "audio/mp4",
                "aac": "audio/aac",
                "opus": "audio/opus",
                "webm": "audio/webm",
            }
            mime = mime_map.get(fmt, f"audio/{fmt}")
            return {"inline_data": {"mime_type": mime, "data": audio_data.get("data", "")}}
        if part.get("type") == "text":
            return {"text": part.get("text", "")}
    return part

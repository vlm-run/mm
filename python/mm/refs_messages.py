"""Driver for :meth:`mm.Context.to_messages` — converts put-based items
into a single OpenAI-/Gemini-compatible user-turn message list.

The hot-path encoder invocation still lives in Python because the
registered encoders own PIL / ffmpeg / pypdfium2 calls. The Rust side
owns item storage, ref generation, and (in the future) any Rust-native
encoders; this module is the narrow bridge.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Literal

if TYPE_CHECKING:
    from mm.context import Context


_OPENAI_DEFAULT_ENCODERS: dict[str, str] = {
    "image": "image-resize",
    "video": "video-frame-sample",
    "document": "document-rasterize",
    "audio": "audio-transcribe",
}


def build_messages(
    ctx: "Context",
    *,
    format: Literal["openai", "gemini"],
    encoders: dict[str, str],
) -> list[dict[str, Any]]:
    """Build the single-user-turn message list for ``ctx``.

    Args:
        ctx: Incremental context.
        format: ``"openai"`` (default) or ``"gemini"``.
        encoders: Per-kind encoder name overrides.

    Returns:
        ``[{"role": "user", "content": [...]}]`` (always a single-turn
        list — use one ``Context`` per turn when composing multi-turn
        conversations).
    """
    parts: list[dict[str, Any]] = []
    for item in ctx.items():
        for part in _parts_for_item(item, format=format, encoders=encoders):
            parts.append(_adapt_part(part, format=format))
    if format == "gemini":
        return [{"role": "user", "parts": parts}]
    return [{"role": "user", "content": parts}]


def _parts_for_item(
    item: dict[str, Any],
    *,
    format: str,
    encoders: dict[str, str],
) -> Iterable[dict[str, Any]]:
    meta = item.get("metadata") or {}
    ref_id = item["ref_id"]
    kind = item["kind"]

    note_line = _build_metadata_text(ref_id, meta)
    if note_line:
        yield {"type": "text", "text": note_line}

    src_kind = item["source_kind"]
    src_value = item["source_value"]

    if kind == "text" or (src_kind == "path" and kind in ("code", "config", "data")):
        # Non-media kinds: inline the raw text content, chunked if huge.
        text = _read_text_or_placeholder(src_kind, src_value)
        if text:
            yield {"type": "text", "text": text}
        return

    if src_kind == "url" and kind == "image" and format == "openai":
        yield {"type": "image_url", "image_url": {"url": src_value}}
        return

    if src_kind == "path":
        yield from _encode_path(Path(src_value), kind, format=format, encoders=encoders)
        return

    if src_kind == "in_memory":
        yield from _encode_in_memory(item, ref_id, kind, format=format, encoders=encoders)
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


def _read_text_or_placeholder(src_kind: str, src_value: str) -> str:
    if src_kind == "path":
        try:
            return Path(src_value).read_text(errors="replace")
        except OSError:
            return ""
    if src_kind == "url":
        return f"<remote text {src_value}>"
    return ""


def _encode_path(
    path: Path,
    kind: str,
    *,
    format: str,
    encoders: dict[str, str],
) -> Iterable[dict[str, Any]]:
    strategy_name = _resolve_strategy(kind, encoders)
    if strategy_name is None:
        return
    from mm.encoders import get as get_encoder

    try:
        strategy = get_encoder(strategy_name)
    except KeyError:
        return
    for msg in strategy.encode(path):
        for part in msg.get("content", []):
            yield part


def _encode_in_memory(
    item: dict[str, Any],
    ref_id: str,
    kind: str,
    *,
    format: str,
    encoders: dict[str, str],
) -> Iterable[dict[str, Any]]:
    # Retrieve the concrete Python object via ctx.get — but we don't
    # have ctx here. Use source_value (MIME) + desc and let PIL / bytes
    # handling happen via a tempfile spool.
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
        yield from _encode_path(path, "image", format=format, encoders=encoders)
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


def _resolve_strategy(kind: str, encoders: dict[str, str]) -> str | None:
    override = encoders.get(kind)
    if override:
        # Accept both ``"tile"`` and ``"image-tile"``.
        if "-" in override:
            return override
        return f"{kind}-{override}"
    return _OPENAI_DEFAULT_ENCODERS.get(kind)


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
        if part.get("type") == "text":
            return {"text": part.get("text", "")}
    return part

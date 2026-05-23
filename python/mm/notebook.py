"""Jupyter notebook visualization for multimodal context.

Renders ``mm.Context`` items as styled, self-contained HTML that works
in Jupyter, Colab, and VS Code notebook renderers. Designed for
educating developers on how different encoders represent multimodal
content (video frames, image tiles, audio transcripts, etc.).

Two rendering paths:

1. **``render_context(ctx)``** — the rich path. Has access to source
   files, metadata dicts, and encoded VLM parts. Shows native media
   players, collapsible encoded-parts galleries, and per-context stats.

2. **``render_messages(messages)``** — the lightweight path. Renders
   an arbitrary OpenAI-format message list (useful for multi-turn
   conversations or assistant responses).

Example::

    import mm
    from pathlib import Path

    ctx = mm.Context()
    ctx.add("Describe the media below.", role="user")
    ctx.add(Path("photo.jpg"), role="user", metadata={"note": "hero shot"})
    ctx.add(Path("clip.mp4"), role="user")
    ctx.render_html()          # returns HTML string
    ctx                        # auto-renders in Jupyter via _repr_html_

    # Or for raw OpenAI-format message lists:
    from mm.notebook import render_messages
    msgs = [{"role": "assistant", "content": "I see a car."}]
    render_messages(msgs)
"""

from __future__ import annotations

import ast
import base64
import html
import json
import logging
import math
import re
import struct
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mm.context import Context

logger = logging.getLogger(__name__)

_REF_TAG_RE = re.compile(r"\[ref=([^\]]+)\]")
_GALLERY_COLLAPSE_THRESHOLD = 4
_ITEMS_VISIBLE = 3
_VIDEO_EMBED_MAX_BYTES = 50 * 1024 * 1024
_AUDIO_EMBED_MAX_BYTES = 20 * 1024 * 1024
_TOKENS_PER_CHAR = 0.25
_TOKENS_PER_IMAGE = 170


def render_context(
    ctx: "Context",
    *,
    max_image_width: int = 320,
    title: str | None = None,
    encoders: dict[str, str] | None = None,
    encoder_kwargs: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Render a Context as rich, self-contained HTML.

    Each item in the context is rendered with its native media view
    (image, video player, audio player, document pages), the user-supplied
    metadata dict, and a collapsible section showing the encoded VLM
    representation.

    Args:
        ctx: An incremental role-aware ``mm.Context``.
        max_image_width: Maximum rendered width for images in pixels.
        title: Optional title bar text.
        encoders: Per-kind encoder overrides, e.g.
            ``{"image": "tile", "video": "mosaic"}``.
        encoder_kwargs: Per-kind kwargs forwarded to the encoder's
            ``encode()`` method.

    Returns:
        Self-contained HTML string for ``IPython.display.HTML()``.
    """
    scope = f"mm-{uuid.uuid4().hex[:8]}"
    items = ctx.items()
    messages = ctx.to_messages(format="openai", encoders=encoders, encoder_kwargs=encoder_kwargs)
    encoded_parts_by_ref = _split_encoded_parts(messages)

    item_blocks: list[str] = []
    stats = _Stats()

    for item in items:
        block = _render_item(
            item,
            encoded_parts=encoded_parts_by_ref.get(item["ref_id"], []),
            scope=scope,
            max_image_width=max_image_width,
            stats=stats,
        )
        item_blocks.append(block)

    title_str = title or f"mm.Context · {len(items)} item(s)"
    title_html = f'<div class="{scope}-title">{html.escape(title_str)}</div>'
    stats_html = _render_stats(stats, scope)
    body = _collapse_extras(item_blocks, scope, label="items")

    return (
        f'<div class="{scope}-root">\n'
        f"<style>{_css(scope)}</style>\n"
        f"{title_html}\n{body}\n{stats_html}\n"
        f"</div>"
    )


def render_messages(
    messages: list[dict[str, Any]],
    *,
    max_image_width: int = 320,
    show_role: bool = True,
    title: str | None = None,
) -> str:
    """Render an OpenAI-format message list as self-contained HTML.

    Lighter-weight than ``render_context`` — works on any message list
    (including assistant responses or multi-turn conversations) but
    cannot show native media players or metadata dicts.

    Args:
        messages: List of message dicts with ``role`` and ``content``.
        max_image_width: Maximum rendered width for inline images.
        show_role: Whether to display role badges.
        title: Optional title bar text.

    Returns:
        Self-contained HTML string for ``IPython.display.HTML()``.
    """
    scope = f"mm-{uuid.uuid4().hex[:8]}"
    parts_html: list[str] = []
    stats = _Stats()

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        parts = content if isinstance(content, list) else []
        if not parts and "parts" in msg:
            parts = msg["parts"]

        msg_html = _render_message_block(
            role,
            parts,
            scope=scope,
            max_image_width=max_image_width,
            show_role=show_role,
            stats=stats,
        )
        parts_html.append(msg_html)

    body = _collapse_extras(parts_html, scope, label="messages")
    title_html = ""
    if title:
        title_html = f'<div class="{scope}-title">{html.escape(title)}</div>'
    stats_html = _render_stats(stats, scope)

    return (
        f'<div class="{scope}-root">\n'
        f"<style>{_css(scope)}</style>\n"
        f"{title_html}\n{body}\n{stats_html}\n"
        f"</div>"
    )


class _Stats:
    """Accumulates rendering statistics across all items/messages."""

    __slots__ = (
        "n_images",
        "n_videos",
        "n_audio",
        "n_documents",
        "n_text",
        "total_bytes",
        "total_text_chars",
        "total_encoded_images",
    )

    def __init__(self) -> None:
        self.n_images = 0
        self.n_videos = 0
        self.n_audio = 0
        self.n_documents = 0
        self.n_text = 0
        self.total_bytes = 0
        self.total_text_chars = 0
        self.total_encoded_images = 0

    @property
    def est_tokens(self) -> int:
        text_toks = int(self.total_text_chars * _TOKENS_PER_CHAR)
        image_toks = self.total_encoded_images * _TOKENS_PER_IMAGE
        return text_toks + image_toks


def _collapse_extras(blocks: list[str], scope: str, *, label: str) -> str:
    """Show first ``_ITEMS_VISIBLE`` blocks; tuck the rest behind a "Show more" pill.

    Threshold: when ``len(blocks) > _ITEMS_VISIBLE + 1`` we collapse — if we'd
    only be hiding a single item, the pill button has more chrome than the
    item itself, so we just show everything.
    """
    if len(blocks) <= _ITEMS_VISIBLE + 1:
        return "\n".join(blocks)
    visible = "\n".join(blocks[:_ITEMS_VISIBLE])
    hidden_count = len(blocks) - _ITEMS_VISIBLE
    hidden = "\n".join(blocks[_ITEMS_VISIBLE:])
    return (
        f"{visible}\n"
        f'<details class="{scope}-collapse {scope}-collapse-extras">'
        f'<summary class="{scope}-more">Show {hidden_count} more {label}</summary>'
        f'<div class="{scope}-extras-body">{hidden}</div>'
        f"</details>"
    )


def _split_encoded_parts(
    messages: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Map ref_id -> list of encoded content parts from to_messages() output.

    Parses ``[ref=xxx]`` markers in text parts to split the flat message
    content list back into per-item groups.
    """
    result: dict[str, list[dict[str, Any]]] = {}
    if not messages:
        return result

    all_parts: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content", [])
        if isinstance(content, list):
            all_parts.extend(content)
        elif isinstance(content, str):
            all_parts.append({"type": "text", "text": content})
        parts = msg.get("parts")
        if parts and isinstance(parts, list):
            all_parts.extend(parts)

    current_ref: str | None = None
    for part in all_parts:
        if part.get("type") == "text":
            text = part.get("text", "")
            m = _REF_TAG_RE.search(text)
            if m:
                current_ref = m.group(1)
        if current_ref is not None:
            result.setdefault(current_ref, []).append(part)

    return result


def _render_item(
    item: dict[str, Any],
    encoded_parts: list[dict[str, Any]],
    *,
    scope: str,
    max_image_width: int,
    stats: _Stats,
) -> str:
    """Render a single Context item as an HTML block."""
    ref_id = item["ref_id"]
    role = item.get("role", "user")
    kind = item["kind"]
    source_kind = item["source_kind"]
    source_value = item["source_value"]
    meta_raw = item.get("metadata")

    meta: dict[str, Any] = {}
    if meta_raw:
        if isinstance(meta_raw, str):
            try:
                meta = json.loads(meta_raw)
            except (json.JSONDecodeError, ValueError):
                try:
                    meta = ast.literal_eval(meta_raw)
                except (SyntaxError, ValueError):
                    meta = {"_raw": meta_raw}
        elif isinstance(meta_raw, dict):
            meta = meta_raw

    filename = Path(source_value).name if source_kind == "path" else source_value
    encoded_size = _encoded_bytes_from_parts(encoded_parts) or None
    display_size = encoded_size or (
        _get_file_size(source_value) if source_kind == "path" else item.get("byte_len")
    )

    _track_item_stats(kind, stats)

    header = _render_item_header(ref_id, role, kind, filename, display_size, scope)
    meta_html = _render_metadata_dict(meta, scope) if meta else ""
    native_html = _render_native_view(
        item, scope, max_image_width, stats, encoded_size=encoded_size
    )
    encoded_html = _render_encoded_section(
        encoded_parts, scope, max_image_width, stats, item_kind=kind
    )

    return f'<div class="{scope}-item">{header}{meta_html}{native_html}{encoded_html}</div>'


def _track_item_stats(kind: str, stats: _Stats) -> None:
    if kind == "image":
        stats.n_images += 1
    elif kind == "video":
        stats.n_videos += 1
    elif kind == "audio":
        stats.n_audio += 1
    elif kind == "document":
        stats.n_documents += 1
    else:
        stats.n_text += 1


def _render_item_header(
    ref_id: str,
    role: str,
    kind: str,
    filename: str,
    file_size: int | None,
    scope: str,
) -> str:
    kind_labels = {
        "image": "IMAGE",
        "video": "VIDEO",
        "audio": "AUDIO",
        "document": "DOCUMENT",
        "code": "CODE",
        "text": "TEXT",
        "config": "CONFIG",
        "data": "DATA",
    }
    kind_label = kind_labels.get(kind, kind.upper())
    size_str = f" · {_fmt_bytes(file_size)}" if file_size else ""

    return (
        f'<div class="{scope}-item-header">'
        f'<span class="{scope}-kind {scope}-kind-{html.escape(kind)}">{kind_label}</span>'
        f'<span class="{scope}-role {scope}-role-{html.escape(role)}">{html.escape(role)}</span>'
        f'<span class="{scope}-ref">{html.escape(ref_id)}</span>'
        f'<span class="{scope}-filename">{html.escape(filename)}{size_str}</span>'
        f"</div>"
    )


def _render_metadata_dict(meta: dict[str, Any], scope: str) -> str:
    if not meta:
        return ""
    rows: list[str] = []
    for k, v in meta.items():
        key_esc = html.escape(str(k))
        val_esc = html.escape(str(v))
        rows.append(
            f'<tr><td class="{scope}-meta-key">{key_esc}</td>'
            f'<td class="{scope}-meta-val">{val_esc}</td></tr>'
        )
    inner = "\n".join(rows)
    return f'<table class="{scope}-meta"><tbody>{inner}</tbody></table>'


def _render_native_view(
    item: dict[str, Any],
    scope: str,
    max_image_width: int,
    stats: _Stats,
    *,
    encoded_size: int | None = None,
) -> str:
    """Render the native media view for an item (image, video player, etc.)."""
    kind = item["kind"]
    source_kind = item["source_kind"]
    source_value = item["source_value"]

    if kind == "image" and source_kind == "path":
        return _render_native_image(
            Path(source_value), scope, max_image_width, encoded_size=encoded_size
        )

    if kind == "video" and source_kind == "path":
        return _render_native_video(Path(source_value), scope, max_image_width)

    if kind == "audio" and source_kind == "path":
        return _render_native_audio(Path(source_value), scope)

    if kind == "image" and source_kind == "url":
        return (
            f'<div class="{scope}-native">'
            f'<img src="{html.escape(source_value)}" class="{scope}-img" '
            f'style="max-width:{max_image_width}px">'
            f"</div>"
        )

    return ""


def _render_native_image(
    path: Path, scope: str, max_width: int, *, encoded_size: int | None = None
) -> str:
    if not path.exists():
        return ""
    try:
        data = path.read_bytes()
    except OSError:
        return ""

    mime = _mime_from_ext(path.suffix)
    b64 = base64.b64encode(data).decode()
    dims = _image_dims_from_bytes(data)
    src = f"data:{mime};base64,{b64}"
    byte_size = encoded_size if encoded_size is not None else len(data)
    info = _format_image_label(mime, byte_size, dims)

    return (
        f'<div class="{scope}-native">'
        f"{_zoomable_image(src, scope, max_width)}"
        f'<div class="{scope}-cap">{html.escape(info)}</div>'
        f"</div>"
    )


def _zoomable_image(src: str, scope: str, max_width: int) -> str:
    """Render an image as a zoomable thumbnail with a CSS-only lightbox modal.

    Click the thumbnail → checkbox toggles → modal shows. Click anywhere on
    the modal (backdrop or image) → checkbox un-toggles → modal hides.
    No JavaScript required, so it works reliably inside Jupyter, Colab, and
    VS Code notebook renderers.
    """
    img_id = f"{scope}-z{uuid.uuid4().hex[:6]}"
    return (
        f'<span class="{scope}-zoom">'
        f'<input type="checkbox" id="{img_id}" class="{scope}-zoom-toggle">'
        f'<label for="{img_id}" class="{scope}-img-link" title="Click to zoom">'
        f'<img src="{src}" class="{scope}-img" style="max-width:{max_width}px">'
        f"</label>"
        f'<label for="{img_id}" class="{scope}-modal">'
        f'<img src="{src}" class="{scope}-modal-img">'
        f"</label>"
        f"</span>"
    )


def _render_native_video(path: Path, scope: str, max_width: int) -> str:
    if not path.exists():
        return ""
    file_size = path.stat().st_size
    mime = _mime_from_ext(path.suffix)
    info_parts = [mime, _fmt_bytes(file_size)]

    try:
        from mm.video import VideoReader, pyav_runnable

        if pyav_runnable():
            with VideoReader(path) as reader:
                dur = reader.duration
                w, h = reader.width, reader.height
                if w and h:
                    info_parts.insert(1, f"{w}x{h}")
                if dur > 0:
                    info_parts.insert(1, _fmt_duration(dur))
    except Exception:
        pass

    info = " · ".join(info_parts)

    if file_size <= _VIDEO_EMBED_MAX_BYTES:
        try:
            b64 = base64.b64encode(path.read_bytes()).decode()
        except OSError as exc:
            logger.warning("notebook: cannot read video %s for embedding: %s", path, exc)
            return _render_native_placeholder(f"Video unreadable: {path.name}", info, scope)
        return (
            f'<div class="{scope}-native">'
            f'<video controls preload="metadata" class="{scope}-video" '
            f'style="max-width:{max_width}px">'
            f'<source src="data:{mime};base64,{b64}" type="{mime}">'
            f"</video>"
            f'<div class="{scope}-cap">{html.escape(info)}</div>'
            f"</div>"
        )

    return _render_native_placeholder(
        f"Video too large to embed ({_fmt_bytes(file_size)}): {path.name}",
        info,
        scope,
    )


def _render_native_audio(path: Path, scope: str) -> str:
    if not path.exists():
        return ""
    file_size = path.stat().st_size
    mime = _mime_from_ext(path.suffix)
    info = f"{mime} · {_fmt_bytes(file_size)}"

    if file_size <= _AUDIO_EMBED_MAX_BYTES:
        try:
            b64 = base64.b64encode(path.read_bytes()).decode()
        except OSError as exc:
            logger.warning("notebook: cannot read audio %s for embedding: %s", path, exc)
            return _render_native_placeholder(f"Audio unreadable: {path.name}", info, scope)
        return (
            f'<div class="{scope}-native">'
            f'<audio controls preload="metadata" class="{scope}-audio">'
            f'<source src="data:{mime};base64,{b64}" type="{mime}">'
            f"</audio>"
            f'<div class="{scope}-cap">{html.escape(info)}</div>'
            f"</div>"
        )

    return _render_native_placeholder(
        f"Audio too large to embed ({_fmt_bytes(file_size)}): {path.name}",
        info,
        scope,
    )


def _render_native_placeholder(message: str, caption: str, scope: str) -> str:
    """Render a fallback `<div>` for media that cannot be embedded."""
    return (
        f'<div class="{scope}-native">'
        f'<div class="{scope}-placeholder">{html.escape(message)}</div>'
        f'<div class="{scope}-cap">{html.escape(caption)}</div>'
        f"</div>"
    )


def _render_encoded_section(
    parts: list[dict[str, Any]],
    scope: str,
    max_image_width: int,
    stats: _Stats,
    *,
    item_kind: str,
) -> str:
    """Render encoded VLM parts inline, with a small descriptive caption.

    Skips rendering when the encoded view is redundant with the native view
    (a single image part for an image item — same picture, different size).
    Always renders for video / audio / document, where the encoded view
    contains fundamentally different content (frames / transcript / pages).
    """
    if not parts:
        return ""

    total_b64_bytes = 0
    for part in parts:
        url = _extract_image_url(part)
        if url and url.startswith("data:"):
            _, _, b64 = url.partition(",")
            total_b64_bytes += math.ceil(len(b64) * 3 / 4)
        if _classify_part(part) == "audio":
            _, _, ab = _extract_audio_info(part)
            total_b64_bytes += ab
        if part.get("type") == "text":
            stats.total_text_chars += len(part.get("text", ""))

    n_total_images = sum(1 for p in parts if _classify_part(p) == "image")
    stats.total_encoded_images += n_total_images
    stats.total_bytes += total_b64_bytes

    content_parts = [p for p in parts if not _is_metadata_text(p)]
    if not content_parts:
        return ""

    groups = _group_parts(content_parts)
    n_images = sum(len(g[1]) for g in groups if g[0] == "image")
    n_audio = sum(len(g[1]) for g in groups if g[0] == "audio")
    n_text = sum(len(g[1]) for g in groups if g[0] == "text")
    encoded_text_chars = sum(
        len(p.get("text", "")) for p in content_parts if p.get("type") == "text"
    )

    if item_kind == "image" and n_images == 1 and n_text == 0:
        return ""

    summary: list[str] = []
    if n_images:
        summary.append(f"{n_images} {_encoded_noun(item_kind, n_images)}")
    if n_audio:
        summary.append(f"{n_audio} audio clip{'s' if n_audio != 1 else ''}")
    if n_text and item_kind != "text":
        summary.append(f"{encoded_text_chars:,} chars")
    est_tokens = int(encoded_text_chars * _TOKENS_PER_CHAR) + n_images * _TOKENS_PER_IMAGE
    if est_tokens:
        summary.append(f"~{est_tokens:,} tokens")
    if total_b64_bytes:
        summary.append(_fmt_bytes(total_b64_bytes))

    label_html = ""
    if summary:
        label_html = (
            f'<div class="{scope}-encoded-label">→ {html.escape(" · ".join(summary))}</div>'
        )

    rendered: list[str] = []
    for group_type, group_items in groups:
        if group_type == "image":
            rendered.append(_render_image_gallery(group_items, scope, max_image_width))
        elif group_type == "audio":
            for item in group_items:
                rendered.append(_render_audio_part(item, scope))
        else:
            for item in group_items:
                rendered.append(_render_text_part(item, scope))
    inner = "\n".join(rendered)

    return f'<div class="{scope}-encoded">{label_html}{inner}</div>'


def _is_metadata_text(part: dict[str, Any]) -> bool:
    """True if ``part`` is the ``[ref=...]`` metadata text emitted by ``to_messages()``.

    Those texts are already visible in the item header / metadata dict, so we
    skip them when rendering the encoded view to avoid duplication.
    """
    if part.get("type") != "text":
        return False
    text = (part.get("text") or "").lstrip()
    return bool(_REF_TAG_RE.match(text))


def _encoded_noun(kind: str, n: int) -> str:
    """Per-kind label for the encoded image count."""
    plural = "s" if n != 1 else ""
    if kind == "video":
        return f"frame{plural}"
    if kind == "document":
        return f"page{plural}"
    return f"image{plural}"


def _render_message_block(
    role: str,
    parts: list[dict[str, Any]],
    *,
    scope: str,
    max_image_width: int,
    show_role: bool,
    stats: _Stats,
) -> str:
    """Render a single message (role + content parts) for render_messages."""
    badge = ""
    if show_role:
        badge = (
            f'<div class="{scope}-role {scope}-role-{html.escape(role)}">'
            f"{html.escape(role.capitalize())}</div>"
        )

    groups = _group_parts(parts)
    rendered: list[str] = []

    for group_type, group_items in groups:
        if group_type == "image":
            stats.total_encoded_images += len(group_items)
            for gi in group_items:
                url = _extract_image_url(gi)
                if url and url.startswith("data:"):
                    _, _, b64 = url.partition(",")
                    stats.total_bytes += math.ceil(len(b64) * 3 / 4)
            rendered.append(_render_image_gallery(group_items, scope, max_image_width))
        elif group_type == "audio":
            for item in group_items:
                _, _, byte_size = _extract_audio_info(item)
                stats.total_bytes += byte_size
            rendered.append("\n".join(_render_audio_part(item, scope) for item in group_items))
        else:
            for item in group_items:
                if item.get("type") == "text":
                    stats.total_text_chars += len(item.get("text", ""))
                rendered.append(_render_text_part(item, scope))

    content = "\n".join(rendered)
    return f'<div class="{scope}-msg">{badge}<div class="{scope}-content">{content}</div></div>'


def _group_parts(
    parts: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group consecutive image parts together for gallery rendering."""
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for part in parts:
        ptype = _classify_part(part)
        if groups and groups[-1][0] == ptype:
            groups[-1][1].append(part)
        else:
            groups.append((ptype, [part]))
    return groups


def _classify_part(part: dict[str, Any]) -> str:
    if part.get("type") == "image_url":
        return "image"
    if part.get("type") == "input_audio":
        return "audio"
    if "inline_data" in part:
        mime = part["inline_data"].get("mime_type", "")
        if mime.startswith("audio/"):
            return "audio"
        return "image"
    return "text"


def _render_image_gallery(
    parts: list[dict[str, Any]],
    scope: str,
    max_image_width: int,
) -> str:
    """Render consecutive image parts as a mosaic grid, collapsible if large."""
    items: list[str] = []
    for part in parts:
        url = _extract_image_url(part)
        if not url:
            continue

        dims = None
        if url.startswith("data:"):
            raw = _decode_b64_prefix(url, 32)
            if raw:
                dims = _image_dims_from_bytes(raw)

        caption = _image_size_label(url, dims)

        n = len(parts)
        if n == 1:
            thumb_width = min(240, max_image_width)
        elif n <= 4:
            thumb_width = min(200, max_image_width)
        elif n <= 8:
            thumb_width = min(160, max_image_width)
        else:
            thumb_width = min(100, max_image_width)
        items.append(
            f'<figure class="{scope}-fig">'
            f"{_zoomable_image(url, scope, thumb_width)}"
            f'<figcaption class="{scope}-cap">{html.escape(caption)}</figcaption>'
            f"</figure>"
        )

    if not items:
        return ""

    inner = "\n".join(items)
    grid_class = f"{scope}-grid" if len(parts) > 1 else f"{scope}-gallery"

    if len(items) > _GALLERY_COLLAPSE_THRESHOLD:
        return (
            f'<details class="{scope}-collapse">'
            f'<summary class="{scope}-more">Show {len(items)} frames</summary>'
            f'<div class="{grid_class}">{inner}</div>'
            f"</details>"
        )

    return f'<div class="{grid_class}">{inner}</div>'


def _extract_image_url(part: dict[str, Any]) -> str | None:
    if part.get("type") == "image_url":
        url_obj = part.get("image_url", {})
        if isinstance(url_obj, dict):
            return url_obj.get("url")
        return None
    if "inline_data" in part:
        data = part["inline_data"]
        mime = data.get("mime_type", "image/jpeg")
        b64 = data.get("data", "")
        return f"data:{mime};base64,{b64}"
    return None


def _image_size_label(url: str, dims: tuple[int, int] | None = None) -> str:
    if not url.startswith("data:"):
        return "image (remote)"
    meta, _, b64 = url.partition(",")
    mime = meta.removeprefix("data:").split(";")[0]
    byte_size = math.ceil(len(b64) * 3 / 4)
    return _format_image_label(mime, byte_size, dims)


def _format_image_label(mime: str, byte_size: int, dims: tuple[int, int] | None) -> str:
    """Format a compact image info string: ``mime · KB · WxH · ~tokens``."""
    parts = [mime, _fmt_bytes(byte_size)]
    if dims:
        parts.append(f"{dims[0]}x{dims[1]}")
    parts.append(f"~{_TOKENS_PER_IMAGE} tokens")
    return " · ".join(parts)


def _render_text_part(part: dict[str, Any], scope: str) -> str:
    text = ""
    if part.get("type") == "text":
        text = part.get("text", "")
    elif "text" in part and "type" not in part:
        text = part["text"]
    else:
        text = str(part)
    if not text:
        return ""

    escaped = html.escape(text)
    escaped = _REF_TAG_RE.sub(
        rf'<span class="{scope}-ref">\g<0></span>',
        escaped,
    )
    char_count = len(text)
    annotation = f"text · {char_count:,} chars"

    return (
        f'<div class="{scope}-text">'
        f'<pre class="{scope}-pre">{escaped}</pre>'
        f'<div class="{scope}-cap">{html.escape(annotation)}</div>'
        f"</div>"
    )


_AUDIO_MIME_MAP: dict[str, str] = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "opus": "audio/opus",
    "webm": "audio/webm",
}


def _extract_audio_info(part: dict[str, Any]) -> tuple[str, str, int]:
    """Extract (mime, format_label, byte_size) from an audio part.

    Lightweight — does NOT build a data URI, just computes the decoded size
    from the base64 string length.
    """
    if part.get("type") == "input_audio":
        audio = part.get("input_audio", {})
        fmt = audio.get("format", "mp3")
        mime = _AUDIO_MIME_MAP.get(fmt, f"audio/{fmt}")
        byte_size = math.ceil(len(audio.get("data", "")) * 3 / 4)
        return mime, fmt, byte_size
    if "inline_data" in part:
        data = part["inline_data"]
        mime = data.get("mime_type", "audio/mpeg")
        fmt = mime.split("/")[-1]
        byte_size = math.ceil(len(data.get("data", "")) * 3 / 4)
        return mime, fmt, byte_size
    return "", "unknown", 0


_AUDIO_EMBED_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _render_audio_part(part: dict[str, Any], scope: str) -> str:
    """Render an encoded audio part with an inline player when feasible.

    Embeds a ``<audio>`` player for files up to ``_AUDIO_EMBED_MAX_BYTES``.
    Larger files get a compact badge to avoid bloating the HTML output.
    """
    mime, fmt, byte_size = _extract_audio_info(part)
    if not mime:
        return ""
    annotation = f"{mime} · {_fmt_bytes(byte_size)}"

    if byte_size > _AUDIO_EMBED_MAX_BYTES:
        return (
            f'<div class="{scope}-audio-part">'
            f'<div class="{scope}-audio-badge">&#9835; {html.escape(fmt.upper())}</div>'
            f'<div class="{scope}-cap">{html.escape(annotation)} (too large to embed)</div>'
            f"</div>"
        )

    b64 = ""
    if part.get("type") == "input_audio":
        b64 = part.get("input_audio", {}).get("data", "")
    elif "inline_data" in part:
        b64 = part["inline_data"].get("data", "")
    data_uri = f"data:{mime};base64,{b64}"

    return (
        f'<div class="{scope}-audio-part">'
        f'<audio controls preload="metadata" class="{scope}-audio">'
        f'<source src="{data_uri}" type="{mime}">'
        f"</audio>"
        f'<div class="{scope}-cap">{html.escape(annotation)}</div>'
        f"</div>"
    )


def _render_stats(stats: _Stats, scope: str) -> str:
    """Render the stats footer bar."""
    parts: list[str] = []
    items: list[str] = []
    if stats.n_images:
        items.append(f"{stats.n_images} image(s)")
    if stats.n_videos:
        items.append(f"{stats.n_videos} video(s)")
    if stats.n_audio:
        items.append(f"{stats.n_audio} audio")
    if stats.n_documents:
        items.append(f"{stats.n_documents} document(s)")
    if stats.n_text:
        items.append(f"{stats.n_text} text/code")
    if items:
        parts.append(", ".join(items))

    if stats.total_bytes:
        parts.append(f"encoded: ~{_fmt_bytes(stats.total_bytes)}")
    if stats.est_tokens:
        parts.append(f"~{stats.est_tokens:,} est. tokens")

    if not parts:
        return ""

    text = " · ".join(parts)
    return f'<div class="{scope}-stats">{html.escape(text)}</div>'


def _image_dims_from_bytes(data: bytes) -> tuple[int, int] | None:
    """Extract width x height from JPEG or PNG header bytes.

    Works on partial data (only the first ~32 bytes are needed for PNG;
    JPEG SOF markers may be further in so we scan up to 64 KB).
    """
    if len(data) < 8:
        return None

    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        try:
            w, h = struct.unpack(">II", data[16:24])
            return (w, h)
        except struct.error:
            return None

    if data[:2] == b"\xff\xd8":
        return _jpeg_dims(data)

    return None


def _jpeg_dims(data: bytes) -> tuple[int, int] | None:
    """Scan a JPEG bitstream for the first SOF marker to read dimensions.

    Handles real-world quirks of JPEG framing:
      - Multiple ``0xFF`` fill bytes preceding a marker (``0xFF 0xFF 0xC0``).
      - Stuffed ``0xFF 0x00`` byte pairs (zero is not a marker, just padding).
      - Standalone markers (RSTn / TEM / SOI) that have no segment payload.
      - Stops at SOS (``0xDA``) or EOI (``0xD9``); after SOS the data is
        entropy-coded and any ``0xFF`` byte may be a literal, not a marker.

    Returns ``None`` for malformed streams or streams without an SOF marker
    in the inspected window.
    """
    n = len(data)
    if n < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return None

    standalone = {0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8}
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }

    i = 2
    while i < n:
        if data[i] != 0xFF:
            return None
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            return None
        marker = data[i]
        i += 1
        if marker == 0x00:
            continue
        if marker == 0xD9 or marker == 0xDA:
            return None
        if marker in standalone:
            continue
        if marker in sof_markers:
            if i + 7 > n:
                return None
            try:
                h, w = struct.unpack(">HH", data[i + 3 : i + 7])
            except struct.error:
                return None
            return (w, h)
        if i + 2 > n:
            return None
        try:
            seg_len = struct.unpack(">H", data[i : i + 2])[0]
        except struct.error:
            return None
        if seg_len < 2:
            return None
        i += seg_len
    return None


def _decode_b64_prefix(data_url: str, n_bytes: int) -> bytes | None:
    """Decode the first *n_bytes* from a data-URL without decoding all of it.

    Pads the truncated base64 chunk with the correct number of ``=`` so the
    total length is a multiple of 4. A fixed two-byte pad would yield invalid
    base64 for chunks whose length mod 4 is 2 or 3, raising
    ``binascii.Error`` on decode.
    """
    _, _, b64 = data_url.partition(",")
    chars_needed = math.ceil(n_bytes * 4 / 3) + 4
    chunk = b64[:chars_needed]
    pad = (-len(chunk)) % 4
    try:
        return base64.b64decode(chunk + "=" * pad)
    except ValueError:
        return None


def _encoded_bytes_from_parts(parts: list[dict[str, Any]]) -> int:
    """Total decoded byte size of base64 image payloads in a part list."""
    total = 0
    for part in parts:
        url = _extract_image_url(part)
        if url and url.startswith("data:"):
            _, _, b64 = url.partition(",")
            total += math.ceil(len(b64) * 3 / 4)
    return total


def _get_file_size(path_str: str) -> int | None:
    try:
        return Path(path_str).stat().st_size
    except OSError:
        return None


def _mime_from_ext(ext: str) -> str:
    ext = ext.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".opus": "audio/opus",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def _css(scope: str) -> str:
    s = scope
    return f"""
    .{s}-root {{
        --mm-bg: #ffffff;
        --mm-bg-pre: #f6f8fa;
        --mm-bg-soft: #fafbfc;
        --mm-text: #1a1a2e;
        --mm-text-dim: #656d76;
        --mm-border: #d1d9e0;
        --mm-border-soft: #e6e9ec;
        --mm-accent: #4361ee;
        --mm-ref-bg: #ddf4ff;
        --mm-ref-text: #0969da;
        --mm-role-user: #4361ee;
        --mm-role-assistant: #1a7f37;
        --mm-role-system: #656d76;
        --mm-shadow: rgba(0, 0, 0, 0.04);
        --mm-kind-image: #8250df;
        --mm-kind-video: #bf3989;
        --mm-kind-audio: #cf222e;
        --mm-kind-document: #0969da;
        --mm-kind-default: #656d76;

        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        font-size: 12px;
        color: var(--mm-text);
        background: var(--mm-bg-soft);
        border: 1px solid var(--mm-border);
        border-radius: 8px;
        overflow: hidden;
        max-width: 720px;
        line-height: 1.4;
    }}
    .{s}-title {{
        padding: 6px 10px;
        font-weight: 600;
        font-size: 12px;
        background: var(--mm-bg-soft);
        border-bottom: 1px solid var(--mm-border-soft);
        letter-spacing: -0.01em;
    }}

    /* ── item / message cards ── */
    .{s}-item, .{s}-msg {{
        padding: 8px 10px;
        margin: 6px 8px;
        background: var(--mm-bg);
        border: 1px solid var(--mm-border-soft);
        border-radius: 6px;
    }}
    .{s}-item-header {{
        display: flex;
        align-items: center;
        gap: 5px;
        margin-bottom: 5px;
        flex-wrap: wrap;
    }}
    .{s}-kind {{
        display: inline-block;
        font-size: 8px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        padding: 1px 5px;
        border-radius: 2px;
        color: white;
        background: var(--mm-kind-default);
    }}
    .{s}-kind-image {{ background: var(--mm-kind-image); }}
    .{s}-kind-video {{ background: var(--mm-kind-video); }}
    .{s}-kind-audio {{ background: var(--mm-kind-audio); }}
    .{s}-kind-document {{ background: var(--mm-kind-document); }}
    .{s}-ref {{
        display: inline-block;
        background: var(--mm-ref-bg);
        color: var(--mm-ref-text);
        padding: 0 4px;
        border-radius: 2px;
        font-weight: 600;
        font-size: 10px;
        font-family: "SF Mono", Menlo, Consolas, monospace;
    }}
    .{s}-filename {{
        font-size: 11px;
        color: var(--mm-text-dim);
    }}

    /* ── metadata dict ── */
    .{s}-meta {{
        margin: 0 0 5px 0;
        border-collapse: collapse;
        font-size: 10px;
    }}
    .{s}-meta td {{
        padding: 1px 8px 1px 0;
        vertical-align: top;
    }}
    .{s}-meta-key {{
        color: var(--mm-text-dim);
        font-weight: 600;
        white-space: nowrap;
    }}
    .{s}-meta-val {{
        color: var(--mm-text);
    }}

    /* ── native media views ── */
    .{s}-native {{ margin-bottom: 5px; }}
    .{s}-zoom {{
        display: inline-block;
        line-height: 0;
    }}
    .{s}-zoom-toggle {{
        position: absolute;
        opacity: 0;
        pointer-events: none;
    }}
    .{s}-img-link {{
        display: inline-block;
        line-height: 0;
        cursor: zoom-in;
    }}
    .{s}-img {{
        border: 1px solid var(--mm-border-soft);
        border-radius: 3px;
        box-shadow: 0 1px 2px var(--mm-shadow);
        display: block;
        height: auto;
        transition: border-color 0.15s;
    }}
    .{s}-img-link:hover .{s}-img {{
        border-color: var(--mm-accent);
    }}

    /* ── lightbox modal (CSS-only, checkbox-toggle pattern) ── */
    .{s}-modal {{
        display: none;
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.92);
        z-index: 99999;
        cursor: zoom-out;
        align-items: center;
        justify-content: center;
        padding: 24px;
        box-sizing: border-box;
        animation: {s}-fade 0.12s ease-out;
    }}
    .{s}-zoom-toggle:checked ~ .{s}-modal {{
        display: flex;
    }}
    .{s}-modal-img {{
        max-width: 95vw;
        max-height: 95vh;
        width: auto;
        height: auto;
        border-radius: 4px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
    }}
    @keyframes {s}-fade {{
        from {{ opacity: 0; }}
        to {{ opacity: 1; }}
    }}
    .{s}-video {{
        border: 1px solid var(--mm-border-soft);
        border-radius: 3px;
        display: block;
        background: #000;
    }}
    .{s}-audio {{
        display: block;
        width: 100%;
        max-width: 320px;
        height: 28px;
    }}
    .{s}-audio-part {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 8px;
        background: var(--mm-bg-alt);
        border-radius: 4px;
        margin: 2px 0;
    }}
    .{s}-audio-badge {{
        font-weight: 600;
        font-size: 12px;
        color: var(--mm-kind-audio);
    }}
    .{s}-placeholder {{
        padding: 6px 10px;
        background: var(--mm-bg-soft);
        border: 1px dashed var(--mm-border);
        border-radius: 3px;
        color: var(--mm-text-dim);
        font-size: 11px;
    }}
    .{s}-cap {{
        font-size: 9px;
        color: var(--mm-text-dim);
        margin-top: 2px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}

    /* ── collapsible "Show more" pattern ── */
    .{s}-collapse {{
        margin-top: 4px;
    }}
    .{s}-collapse > summary {{
        list-style: none;
        cursor: pointer;
        user-select: none;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }}
    .{s}-collapse > summary::-webkit-details-marker {{ display: none; }}
    .{s}-more {{
        font-size: 10px;
        color: var(--mm-text-dim);
        padding: 2px 7px;
        border-radius: 999px;
        background: var(--mm-bg-soft);
        border: 1px solid var(--mm-border-soft);
        transition: all 0.15s;
    }}
    .{s}-more:hover {{
        color: var(--mm-accent);
        border-color: var(--mm-accent);
        background: white;
    }}
    .{s}-collapse[open] > summary > .{s}-more::before {{
        content: "− ";
    }}
    .{s}-collapse:not([open]) > summary > .{s}-more::before {{
        content: "+ ";
    }}
    .{s}-collapse-extras {{
        margin: 0 8px 6px 8px;
        text-align: center;
    }}
    .{s}-extras-body {{
        margin-top: 0;
        text-align: left;
    }}
    .{s}-extras-body > .{s}-item,
    .{s}-extras-body > .{s}-msg {{
        margin-left: 0;
        margin-right: 0;
    }}

    /* ── encoded VLM view (inline, kind-aware) ── */
    .{s}-encoded {{
        margin-top: 6px;
        padding-top: 6px;
        border-top: 1px dashed var(--mm-border-soft);
        display: flex;
        flex-direction: column;
        gap: 5px;
    }}
    .{s}-encoded-label {{
        font-size: 9px;
        color: var(--mm-text-dim);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        letter-spacing: 0.02em;
    }}

    /* ── mosaic grid ── */
    .{s}-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 4px;
    }}
    .{s}-grid .{s}-fig {{ margin: 0; }}
    .{s}-grid .{s}-img {{
        width: 100%;
        max-width: none;
        border-radius: 2px;
    }}
    .{s}-grid .{s}-cap {{ font-size: 9px; }}
    .{s}-gallery {{
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
        align-items: flex-start;
    }}
    .{s}-fig {{
        margin: 0;
        padding: 0;
        display: inline-flex;
        flex-direction: column;
        align-items: flex-start;
    }}

    /* ── text parts ── */
    .{s}-pre {{
        margin: 0;
        padding: 5px 8px;
        background: var(--mm-bg);
        border: 1px solid var(--mm-border-soft);
        border-radius: 3px;
        font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
        font-size: 11px;
        line-height: 1.45;
        white-space: pre-wrap;
        word-break: break-word;
        overflow-x: auto;
        max-height: 140px;
        overflow-y: auto;
        color: var(--mm-text);
    }}

    /* ── role badges (render_messages) ── */
    .{s}-role {{
        display: inline-block;
        font-size: 9px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        padding: 1px 5px;
        border-radius: 2px;
        margin-bottom: 5px;
    }}
    .{s}-role-user {{
        color: var(--mm-role-user);
        background: color-mix(in srgb, var(--mm-role-user) 12%, transparent);
    }}
    .{s}-role-assistant {{
        color: var(--mm-role-assistant);
        background: color-mix(in srgb, var(--mm-role-assistant) 12%, transparent);
    }}
    .{s}-role-system {{
        color: var(--mm-role-system);
        background: color-mix(in srgb, var(--mm-role-system) 12%, transparent);
    }}
    .{s}-content {{
        display: flex;
        flex-direction: column;
        gap: 5px;
    }}

    /* ── stats footer ── */
    .{s}-stats {{
        padding: 5px 10px;
        font-size: 10px;
        color: var(--mm-text-dim);
        background: var(--mm-bg-soft);
        border-top: 1px solid var(--mm-border-soft);
    }}
    """

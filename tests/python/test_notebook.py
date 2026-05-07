"""Tests for mm.notebook — Jupyter message thread visualization."""

from __future__ import annotations

import base64
import struct
from typing import Any

from mm.notebook import (
    _Stats,
    _classify_part,
    _collapse_extras,
    _css,
    _decode_b64_prefix,
    _encoded_noun,
    _extract_image_url,
    _fmt_bytes,
    _fmt_duration,
    _format_image_label,
    _group_parts,
    _image_dims_from_bytes,
    _image_size_label,
    _is_metadata_text,
    _mime_from_ext,
    _render_native_audio,
    _render_native_video,
    _render_stats,
    _render_text_part,
    _split_encoded_parts,
    render_context,
    render_messages,
)

TINY_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20).decode()


def _make_valid_png(w: int = 100, h: int = 80) -> bytes:
    """Create a valid PNG file with actual pixel data using PIL."""
    from PIL import Image as PILImage
    import io

    img = PILImage.new("RGB", (w, h), color=(128, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_valid_jpeg(w: int = 160, h: int = 120) -> bytes:
    """Create a minimal JPEG-like header with SOF0 dimensions."""
    sof = struct.pack(">HH", h, w)
    return (
        b"\xff\xd8"
        b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xc0\x00\x11\x08" + sof + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
        b"\xff\xd9"
    )


def _text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _image_part(b64: str = TINY_B64, mime: str = "image/png") -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def _gemini_image_part(b64: str = TINY_B64, mime: str = "image/png") -> dict[str, Any]:
    return {"inline_data": {"mime_type": mime, "data": b64}}


def _message(role: str = "user", parts: list | None = None) -> dict[str, Any]:
    return {"role": role, "content": parts or []}


class TestClassifyPart:
    def test_text(self):
        assert _classify_part({"type": "text", "text": "hello"}) == "text"

    def test_image_url(self):
        assert _classify_part(_image_part()) == "image"

    def test_gemini_inline_data(self):
        assert _classify_part(_gemini_image_part()) == "image"

    def test_unknown_falls_to_text(self):
        assert _classify_part({"type": "unknown"}) == "text"


class TestGroupParts:
    def test_empty(self):
        assert _group_parts([]) == []

    def test_consecutive_images_grouped(self):
        groups = _group_parts([_image_part(), _image_part(), _image_part()])
        assert len(groups) == 1
        assert groups[0][0] == "image"
        assert len(groups[0][1]) == 3

    def test_text_breaks_image_groups(self):
        parts = [_image_part(), _text_part("caption"), _image_part()]
        groups = _group_parts(parts)
        assert [g[0] for g in groups] == ["image", "text", "image"]

    def test_mixed_sequence(self):
        parts = [
            _text_part("intro"),
            _image_part(),
            _image_part(),
            _text_part("between"),
            _text_part("more"),
            _image_part(),
        ]
        groups = _group_parts(parts)
        assert [g[0] for g in groups] == ["text", "image", "text", "image"]
        assert len(groups[1][1]) == 2


class TestExtractImageUrl:
    def test_openai_format(self):
        url = _extract_image_url(_image_part())
        assert url is not None
        assert url.startswith("data:image/png;base64,")

    def test_gemini_format(self):
        url = _extract_image_url(_gemini_image_part())
        assert url is not None
        assert url.startswith("data:image/png;base64,")

    def test_text_returns_none(self):
        assert _extract_image_url(_text_part("hi")) is None


class TestImageSizeLabel:
    def test_data_url(self):
        url = f"data:image/jpeg;base64,{TINY_B64}"
        label = _image_size_label(url)
        assert "image/jpeg" in label
        assert "B" in label or "KB" in label
        assert "tokens" in label

    def test_remote_url(self):
        label = _image_size_label("https://example.com/img.png")
        assert "remote" in label

    def test_with_dims(self):
        url = f"data:image/jpeg;base64,{TINY_B64}"
        label = _image_size_label(url, dims=(640, 480))
        assert "640x480" in label


class TestFormatImageLabel:
    def test_full_format(self):
        label = _format_image_label("image/jpeg", 99_201, (640, 480))
        assert label.startswith("image/jpeg · ")
        assert " · 96.9 KB" in label or " · 97.0 KB" in label
        assert " · 640x480" in label
        assert " · ~170 tokens" in label

    def test_no_dims(self):
        label = _format_image_label("image/png", 1024, None)
        assert "x" not in label.split("·")[2] if len(label.split("·")) > 2 else True
        assert "tokens" in label


class TestFmtBytes:
    def test_bytes(self):
        assert _fmt_bytes(100) == "100 B"

    def test_kilobytes(self):
        assert _fmt_bytes(2048) == "2.0 KB"

    def test_megabytes(self):
        assert _fmt_bytes(5 * 1024 * 1024) == "5.0 MB"


class TestFmtDuration:
    def test_seconds(self):
        assert _fmt_duration(45) == "0m45s"

    def test_minutes(self):
        assert _fmt_duration(125) == "2m05s"

    def test_hours(self):
        assert _fmt_duration(3661) == "1h01m01s"


class TestImageDims:
    def test_png_dims(self):
        data = _make_valid_png(320, 240)
        dims = _image_dims_from_bytes(data)
        assert dims == (320, 240)

    def test_jpeg_dims(self):
        data = _make_valid_jpeg(640, 480)
        dims = _image_dims_from_bytes(data)
        assert dims == (640, 480)

    def test_too_short(self):
        assert _image_dims_from_bytes(b"\x89PNG") is None

    def test_unknown_format(self):
        assert _image_dims_from_bytes(b"RIFF" + b"\x00" * 20) is None


class TestDecodeB64Prefix:
    def test_decodes_prefix(self):
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        b64 = base64.b64encode(data).decode()
        url = f"data:image/png;base64,{b64}"
        result = _decode_b64_prefix(url, 24)
        assert result is not None
        assert result[:8] == b"\x89PNG\r\n\x1a\n"


class TestSplitEncodedParts:
    def test_splits_by_ref(self):
        messages = [
            _message(
                "user",
                [
                    _text_part("[ref=img_abc] note"),
                    _image_part(),
                    _text_part("[ref=doc_def] other note"),
                    _text_part("Document pages 1-1 of f.pdf:"),
                ],
            )
        ]
        result = _split_encoded_parts(messages)
        assert "img_abc" in result
        assert "doc_def" in result
        assert len(result["img_abc"]) == 2
        assert len(result["doc_def"]) == 2

    def test_empty_messages(self):
        assert _split_encoded_parts([]) == {}


class TestRenderTextPart:
    def test_ref_tag_highlighted(self):
        h = _render_text_part(_text_part("[ref=img_abc123] some note"), "mm-t")
        assert "mm-t-ref" in h
        assert "[ref=img_abc123]" in h

    def test_html_escaped(self):
        h = _render_text_part(_text_part("<script>alert('xss')</script>"), "mm-t")
        assert "<script>" not in h
        assert "&lt;script&gt;" in h

    def test_empty_returns_empty(self):
        assert _render_text_part({"type": "text", "text": ""}, "mm-t") == ""

    def test_char_count_annotation(self):
        h = _render_text_part(_text_part("twelve chars"), "mm-t")
        assert "12 chars" in h


class TestStats:
    def test_initial(self):
        s = _Stats()
        assert s.n_images == 0
        assert s.est_tokens == 0

    def test_token_estimate(self):
        s = _Stats()
        s.total_text_chars = 400
        s.total_encoded_images = 2
        assert s.est_tokens == 100 + 340

    def test_render_stats(self):
        s = _Stats()
        s.n_images = 2
        s.n_videos = 1
        s.total_bytes = 100_000
        s.total_text_chars = 400
        s.total_encoded_images = 3
        h = _render_stats(s, "mm-t")
        assert "2 image(s)" in h
        assert "1 video(s)" in h
        assert "est. tokens" in h


class TestRenderMessages:
    def test_empty_messages(self):
        result = render_messages([])
        assert "<style>" in result

    def test_single_text_message(self):
        msgs = [_message("user", [_text_part("Hello")])]
        result = render_messages(msgs)
        assert "Hello" in result
        assert "User" in result

    def test_string_content(self):
        msgs = [{"role": "assistant", "content": "Sure thing."}]
        result = render_messages(msgs)
        assert "Sure thing." in result

    def test_image_rendered(self):
        msgs = [_message("user", [_image_part()])]
        result = render_messages(msgs)
        assert "<img " in result

    def test_collapsible_gallery(self):
        parts = [_image_part() for _ in range(8)]
        msgs = [_message("user", parts)]
        result = render_messages(msgs)
        assert "<details" in result
        assert "Show 8 frames" in result

    def test_small_gallery_not_collapsed(self):
        parts = [_image_part() for _ in range(3)]
        msgs = [_message("user", parts)]
        result = render_messages(msgs)
        assert "<details" not in result or "Show " not in result

    def test_role_hidden(self):
        msgs = [_message("user", [_text_part("test")])]
        result = render_messages(msgs, show_role=False)
        assert "User" not in result

    def test_title(self):
        result = render_messages([], title="My Thread")
        assert "My Thread" in result

    def test_stats_footer(self):
        msgs = [_message("user", [_text_part("hello"), _image_part()])]
        result = render_messages(msgs)
        assert "est. tokens" in result

    def test_multi_role(self):
        msgs = [
            _message("system", [_text_part("You are helpful.")]),
            _message("user", [_text_part("Hi")]),
            _message("assistant", [_text_part("Hello!")]),
        ]
        result = render_messages(msgs)
        assert "System" in result
        assert "User" in result
        assert "Assistant" in result

    def test_scoped_css(self):
        r1 = render_messages([])
        r2 = render_messages([])
        id1 = r1.split("-root")[0].split('"')[-1]
        id2 = r2.split("-root")[0].split('"')[-1]
        assert id1 != id2


class TestRenderContext:
    def test_basic(self, tmp_path):
        img_path = tmp_path / "test.png"
        img_path.write_bytes(_make_valid_png(200, 150))

        import mm

        ctx = mm.Context()
        ctx.add(img_path, metadata={"note": "test image", "tags": "demo"})
        result = render_context(ctx)
        assert "<style>" in result
        assert "IMAGE" in result
        assert "test.png" in result

    def test_metadata_dict_rendered(self, tmp_path):
        img_path = tmp_path / "photo.png"
        img_path.write_bytes(_make_valid_png())

        import mm

        ctx = mm.Context()
        ctx.add(img_path, metadata={"note": "hero shot", "camera": "iPhone"})
        result = render_context(ctx)
        assert "hero shot" in result
        assert "camera" in result
        assert "iPhone" in result
        assert "meta-key" in result

    def test_image_resolution(self, tmp_path):
        img_path = tmp_path / "big.png"
        img_path.write_bytes(_make_valid_png(1920, 1080))

        import mm

        ctx = mm.Context()
        ctx.add(img_path)
        result = render_context(ctx)
        assert "1920x1080" in result

    def test_encoded_skipped_for_single_image(self, tmp_path):
        """Image kind + 1 encoded image is redundant — skip the encoded view."""
        img_path = tmp_path / "img.png"
        img_path.write_bytes(_make_valid_png())

        import mm

        ctx = mm.Context()
        ctx.add(img_path)
        result = render_context(ctx)
        assert "Show VLM encoding" not in result
        assert "→ 1 image" not in result

    def test_encoded_inline_for_video(self, tmp_path):
        """Video frames are fundamentally different from native — render inline."""
        from mm.notebook import _render_encoded_section, _Stats

        parts = [
            {"type": "text", "text": "frames 0-3"},
            _image_part(),
            _image_part(),
            _image_part(),
        ]
        result = _render_encoded_section(parts, "mm-t", 320, _Stats(), item_kind="video")
        assert "encoded-label" in result
        assert "3 frames" in result
        assert "<details" not in result

    def test_encoded_inline_for_document(self, tmp_path):
        """Document pages render inline — no native PDF view exists."""
        from mm.notebook import _render_encoded_section, _Stats

        parts = [_image_part(), _image_part()]
        result = _render_encoded_section(parts, "mm-t", 320, _Stats(), item_kind="document")
        assert "2 pages" in result
        assert "<details" not in result

    def test_encoded_renders_for_image_with_tiles(self, tmp_path):
        """Image with multiple encoded parts (e.g. image-tile) is informative."""
        from mm.notebook import _render_encoded_section, _Stats

        parts = [_image_part(), _image_part(), _image_part()]
        result = _render_encoded_section(parts, "mm-t", 320, _Stats(), item_kind="image")
        assert "3 images" in result

    def test_stats_footer(self, tmp_path):
        img_path = tmp_path / "a.png"
        img_path.write_bytes(_make_valid_png())

        import mm

        ctx = mm.Context()
        ctx.add(img_path, metadata={"note": "first"})
        result = render_context(ctx)
        assert "1 image(s)" in result
        assert "est. tokens" in result

    def test_text_item(self, tmp_path):
        txt_path = tmp_path / "hello.txt"
        txt_path.write_text("Hello, world!")

        import mm

        ctx = mm.Context()
        ctx.add(txt_path)
        result = render_context(ctx)
        assert "hello.txt" in result

    def test_title_override(self, tmp_path):
        txt_path = tmp_path / "f.txt"
        txt_path.write_text("x")

        import mm

        ctx = mm.Context()
        ctx.add(txt_path)
        result = render_context(ctx, title="Custom Title")
        assert "Custom Title" in result

    def test_render_html_method(self, tmp_path):
        img_path = tmp_path / "m.png"
        img_path.write_bytes(_make_valid_png())

        import mm

        ctx = mm.Context()
        ctx.add(img_path)
        result = ctx.render_html()
        assert "<style>" in result
        assert "IMAGE" in result


class TestCollapseExtras:
    def test_no_collapse_when_few(self):
        blocks = ["<a/>", "<b/>", "<c/>", "<d/>"]
        result = _collapse_extras(blocks, "mm-t", label="items")
        assert "Show " not in result
        assert "<details" not in result

    def test_collapses_when_many(self):
        blocks = [f"<x{i}/>" for i in range(8)]
        result = _collapse_extras(blocks, "mm-t", label="items")
        assert "Show 5 more items" in result
        assert "<details" in result
        assert "<x0/>" in result
        assert "<x2/>" in result
        assert "<x7/>" in result


class TestRenderContextTruncation:
    def test_truncates_when_many_items(self, tmp_path):
        import mm

        ctx = mm.Context()
        for i in range(8):
            p = tmp_path / f"f{i}.txt"
            p.write_text(f"file {i}")
            ctx.add(p)
        result = ctx.render_html()
        assert "Show 5 more items" in result
        assert "<details" in result

    def test_no_truncation_when_few(self, tmp_path):
        import mm

        ctx = mm.Context()
        for i in range(3):
            p = tmp_path / f"f{i}.txt"
            p.write_text(f"file {i}")
            ctx.add(p)
        result = ctx.render_html()
        assert "Show " not in result or "more items" not in result


class TestClickToZoom:
    def test_native_image_has_modal(self, tmp_path):
        img_path = tmp_path / "z.png"
        img_path.write_bytes(_make_valid_png())

        import mm

        ctx = mm.Context()
        ctx.add(img_path)
        result = render_context(ctx)
        assert "img-link" in result
        assert "zoom-toggle" in result
        assert "-modal" in result
        assert 'target="_blank"' not in result

    def test_gallery_image_has_modal(self):
        msgs = [_message("user", [_image_part()])]
        result = render_messages(msgs)
        assert "img-link" in result
        assert "zoom-toggle" in result
        assert "-modal" in result
        assert 'target="_blank"' not in result

    def test_each_image_has_unique_modal_id(self):
        msgs = [_message("user", [_image_part(), _image_part(), _image_part()])]
        result = render_messages(msgs)
        import re

        ids = re.findall(r'id="(mm-\w+-z\w+)"', result)
        assert len(ids) == 3
        assert len(set(ids)) == 3


class TestXssSafety:
    def test_script_injection(self):
        msgs = [_message("user", [_text_part('<img src=x onerror="alert(1)">')])]
        result = render_messages(msgs)
        assert "<img src=x" not in result

    def test_ref_tag_injection(self):
        msgs = [_message("user", [_text_part('[ref="><script>alert(1)</script>]')])]
        result = render_messages(msgs)
        assert "<script>" not in result


class TestIsMetadataText:
    def test_ref_tag_is_metadata(self):
        assert _is_metadata_text({"type": "text", "text": "[ref=abc123] photo.jpg"})

    def test_ref_tag_with_leading_whitespace(self):
        assert _is_metadata_text({"type": "text", "text": "  [ref=xyz]"})

    def test_plain_text_is_not_metadata(self):
        assert not _is_metadata_text({"type": "text", "text": "hello world"})

    def test_non_text_part_is_not_metadata(self):
        assert not _is_metadata_text(_image_part())

    def test_empty_text(self):
        assert not _is_metadata_text({"type": "text", "text": ""})

    def test_ref_in_middle_is_not_metadata(self):
        assert not _is_metadata_text({"type": "text", "text": "see [ref=x]"})


class TestEncodedNoun:
    def test_video_singular(self):
        assert _encoded_noun("video", 1) == "frame"

    def test_video_plural(self):
        assert _encoded_noun("video", 5) == "frames"

    def test_document_singular(self):
        assert _encoded_noun("document", 1) == "page"

    def test_document_plural(self):
        assert _encoded_noun("document", 3) == "pages"

    def test_image_singular(self):
        assert _encoded_noun("image", 1) == "image"

    def test_image_plural(self):
        assert _encoded_noun("image", 4) == "images"

    def test_unknown_kind_falls_to_image(self):
        assert _encoded_noun("audio", 2) == "images"


class TestMimeFromExt:
    def test_jpeg(self):
        assert _mime_from_ext(".jpg") == "image/jpeg"
        assert _mime_from_ext(".jpeg") == "image/jpeg"

    def test_case_insensitive(self):
        assert _mime_from_ext(".PNG") == "image/png"
        assert _mime_from_ext(".Mp4") == "video/mp4"

    def test_video(self):
        assert _mime_from_ext(".mp4") == "video/mp4"
        assert _mime_from_ext(".mkv") == "video/x-matroska"
        assert _mime_from_ext(".webm") == "video/webm"

    def test_audio(self):
        assert _mime_from_ext(".mp3") == "audio/mpeg"
        assert _mime_from_ext(".wav") == "audio/wav"
        assert _mime_from_ext(".m4a") == "audio/mp4"

    def test_pdf(self):
        assert _mime_from_ext(".pdf") == "application/pdf"

    def test_unknown_falls_to_octet_stream(self):
        assert _mime_from_ext(".xyz") == "application/octet-stream"


class TestRenderNativeVideo:
    def _write_fake_mp4(self, path, size: int = 1024) -> None:
        # Minimal bytes — enough to be embedded; PyAV will fail and that's fine,
        # we still exercise the embed path.
        path.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * (size - 16))

    def test_returns_empty_for_missing_file(self, tmp_path):
        result = _render_native_video(tmp_path / "nope.mp4", "scope", 320)
        assert result == ""

    def test_embeds_small_video(self, tmp_path):
        path = tmp_path / "small.mp4"
        self._write_fake_mp4(path, size=2048)
        result = _render_native_video(path, "scope", 320)
        assert "<video controls" in result
        assert 'preload="metadata"' in result
        assert "<source" in result
        assert "video/mp4" in result
        assert "data:video/mp4;base64," in result
        assert "max-width:320px" in result
        assert "scope-cap" in result

    def test_too_large_shows_placeholder(self, tmp_path, monkeypatch):
        from mm import notebook

        monkeypatch.setattr(notebook, "_VIDEO_EMBED_MAX_BYTES", 100)
        path = tmp_path / "big.mp4"
        self._write_fake_mp4(path, size=2000)
        result = _render_native_video(path, "scope", 320)
        assert "Video too large to embed" in result
        assert "<video controls" not in result
        assert "scope-placeholder" in result


class TestRenderNativeAudio:
    def _write_fake_mp3(self, path, size: int = 1024) -> None:
        path.write_bytes(b"ID3\x04\x00\x00" + b"\x00" * (size - 6))

    def test_returns_empty_for_missing_file(self, tmp_path):
        result = _render_native_audio(tmp_path / "nope.mp3", "scope")
        assert result == ""

    def test_embeds_small_audio(self, tmp_path):
        path = tmp_path / "small.mp3"
        self._write_fake_mp3(path, size=2048)
        result = _render_native_audio(path, "scope")
        assert "<audio controls" in result
        assert 'preload="metadata"' in result
        assert "<source" in result
        assert "audio/mpeg" in result
        assert "data:audio/mpeg;base64," in result
        assert "scope-cap" in result

    def test_too_large_shows_placeholder(self, tmp_path, monkeypatch):
        from mm import notebook

        monkeypatch.setattr(notebook, "_AUDIO_EMBED_MAX_BYTES", 100)
        path = tmp_path / "big.mp3"
        self._write_fake_mp3(path, size=2000)
        result = _render_native_audio(path, "scope")
        assert "Audio too large to embed" in result
        assert "<audio controls" not in result
        assert "scope-placeholder" in result


class TestModalLightboxCss:
    def test_css_includes_modal_selectors(self):
        css = _css("mm-test")
        assert "mm-test-modal" in css
        assert "mm-test-zoom-toggle" in css
        assert ":checked ~ .mm-test-modal" in css
        assert "position: fixed" in css

    def test_modal_present_in_rendered_output(self):
        msgs = [_message("user", [_image_part()])]
        result = render_messages(msgs)
        assert ":checked ~" in result
        assert "position: fixed" in result

    def test_modal_scoped_to_render(self):
        # Two independent renders must each have their own scoped modal CSS
        # so opening a modal in one doesn't accidentally style the other.
        a = render_messages([_message("user", [_image_part()])])
        b = render_messages([_message("user", [_image_part()])])
        # Extract the scope id from each
        import re

        scope_a = re.search(r'class="(mm-\w+)-zoom"', a)
        scope_b = re.search(r'class="(mm-\w+)-zoom"', b)
        assert scope_a and scope_b
        assert scope_a.group(1) != scope_b.group(1)


class TestContextManager:
    def test_with_block_yields_context(self):
        import mm

        with mm.Context() as ctx:
            assert isinstance(ctx, mm.Context)

    def test_add_inside_with_persists(self, tmp_path):
        import mm

        img = tmp_path / "a.png"
        img.write_bytes(_make_valid_png())

        with mm.Context() as ctx:
            ctx.add(img)
            assert len(list(ctx.items())) == 1

    def test_context_usable_after_exit(self, tmp_path):
        # __exit__ is intentionally a no-op, so the context remains usable.
        import mm

        img = tmp_path / "a.png"
        img.write_bytes(_make_valid_png())

        with mm.Context() as ctx:
            ctx.add(img)

        assert len(list(ctx.items())) == 1
        html_out = ctx.render_html()
        assert "<style" in html_out


class TestContextRenderHtml:
    def test_render_html_returns_self_contained_html(self, tmp_path):
        import mm

        img = tmp_path / "a.png"
        img.write_bytes(_make_valid_png())

        with mm.Context() as ctx:
            ctx.add(img)

            result = ctx.render_html()

        assert "<style" in result
        assert "</style>" in result
        assert "mm-" in result

    def test_render_html_respects_max_width(self, tmp_path):
        import mm

        img = tmp_path / "a.png"
        img.write_bytes(_make_valid_png())

        with mm.Context() as ctx:
            ctx.add(img)
            result = ctx.render_html(max_image_width=128)

        assert "max-width:128px" in result

    def test_render_html_custom_title(self, tmp_path):
        import mm

        img = tmp_path / "a.png"
        img.write_bytes(_make_valid_png())

        with mm.Context() as ctx:
            ctx.add(img)
            result = ctx.render_html(title="My Custom Context")

        assert "My Custom Context" in result

    def test_render_html_encoder_kwargs(self, tmp_path):
        import mm

        img = tmp_path / "a.png"
        img.write_bytes(_make_valid_png())

        with mm.Context() as ctx:
            ctx.add(img)
            result = ctx.render_html(
                encoder_kwargs={"image": {"max_width": 16}},
            )

        assert "<style" in result
        assert "mm-" in result

    def test_render_context_encoder_kwargs(self, tmp_path):
        import mm
        from mm.notebook import render_context

        img = tmp_path / "a.png"
        img.write_bytes(_make_valid_png())

        with mm.Context() as ctx:
            ctx.add(img)
            result = render_context(
                ctx,
                encoder_kwargs={"image": {"max_width": 16}},
            )

        assert "<style" in result


class TestJpegDimsRobustness:
    """Regression tests for the JPEG SOF scanner — see PR #113 review."""

    def test_handles_ff_fill_padding(self):
        # FF FF FF C0 ... — multiple FF fill bytes before the SOF marker.
        sof = struct.pack(">HH", 240, 320)
        data = (
            b"\xff\xd8"
            b"\xff\xff\xff\xc0\x00\x11\x08" + sof + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
            b"\xff\xd9"
        )
        assert _image_dims_from_bytes(data) == (320, 240)

    def test_skips_stuffed_zero_bytes(self):
        # FF 00 is byte-stuffing (literal 0xFF in entropy data); should be
        # treated as not-a-marker and not consume a segment length.
        sof = struct.pack(">HH", 64, 96)
        data = (
            b"\xff\xd8"
            b"\xff\x00"
            b"\xff\xc0\x00\x11\x08" + sof + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
            b"\xff\xd9"
        )
        assert _image_dims_from_bytes(data) == (96, 64)

    def test_stops_at_sos_without_sof(self):
        # SOS (0xDA) means entropy-coded data follows; if we haven't seen
        # SOF by then, return None instead of recursing into garbage.
        data = b"\xff\xd8" + b"\xff\xda" + b"\x00" * 100
        assert _image_dims_from_bytes(data) is None

    def test_stops_at_eoi(self):
        data = b"\xff\xd8" + b"\xff\xd9"
        assert _image_dims_from_bytes(data) is None

    def test_skips_app_segment_to_find_sof(self):
        # APP0 (0xE0) segment of length 16, then a real SOF0.
        sof = struct.pack(">HH", 480, 640)
        data = (
            b"\xff\xd8"
            b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xc0\x00\x11\x08" + sof + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
            b"\xff\xd9"
        )
        assert _image_dims_from_bytes(data) == (640, 480)

    def test_recognises_progressive_sof2(self):
        # SOF2 (0xC2) is progressive JPEG and must be detected the same as SOF0.
        sof = struct.pack(">HH", 200, 100)
        data = (
            b"\xff\xd8"
            b"\xff\xc2\x00\x11\x08" + sof + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
            b"\xff\xd9"
        )
        assert _image_dims_from_bytes(data) == (100, 200)

    def test_does_not_loop_on_zero_length_segment(self):
        # Malformed: APP0 with declared length < 2 must not loop forever
        # nor confuse the scanner.
        data = b"\xff\xd8" + b"\xff\xe0\x00\x00" + b"\x00" * 200
        # Should terminate cleanly, returning None.
        assert _image_dims_from_bytes(data) is None

    def test_does_not_loop_on_truncated_segment(self):
        # Segment length claims more bytes than exist.
        data = b"\xff\xd8" + b"\xff\xe0\xff\xff" + b"\x00" * 8
        assert _image_dims_from_bytes(data) is None

    def test_truncated_before_dimensions(self):
        # SOF marker present but bytes are cut off before the height/width.
        data = b"\xff\xd8" + b"\xff\xc0\x00\x11\x08\x00"
        assert _image_dims_from_bytes(data) is None

    def test_non_jpeg_returns_none(self):
        assert _image_dims_from_bytes(b"GIF89a\x00\x00") is None


class TestDecodeB64PrefixPadding:
    """Regression tests for `=` padding handling — see PR #113 review."""

    def test_handles_chunk_len_mod_4_eq_2(self):
        # Construct a payload where the truncated chunk length % 4 == 2,
        # which would have failed under the old fixed-`==` padding only by
        # coincidence; the modulo strategy must always succeed for valid b64.
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        b64 = base64.b64encode(data).decode().rstrip("=")
        url = f"data:image/png;base64,{b64}"
        for n in range(8, 32):
            result = _decode_b64_prefix(url, n)
            assert result is not None, f"failed for n={n}"
            assert result[:8] == b"\x89PNG\r\n\x1a\n", f"wrong prefix for n={n}"

    def test_short_payload_does_not_raise(self):
        # Payloads where every truncated chunk-mod-4 ∈ {0,1,2,3} is exercised.
        data = b"X" * 6
        b64 = base64.b64encode(data).decode().rstrip("=")
        url = f"data:application/octet-stream;base64,{b64}"
        for n in range(1, 6):
            result = _decode_b64_prefix(url, n)
            assert result is not None
            assert result.startswith(b"X")

    def test_invalid_chars_returns_none(self):
        url = "data:application/octet-stream;base64,!!!not-base64!!!"
        assert _decode_b64_prefix(url, 8) is None


class TestNativeMediaErrorHandling:
    """Regression tests for OSError handling in video/audio embedding."""

    def test_video_unreadable_returns_placeholder(self, tmp_path, monkeypatch, caplog):
        import logging

        path = tmp_path / "broken.mp4"
        path.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 1024)

        from pathlib import Path as _Path

        def boom(self):
            raise OSError("simulated read failure")

        monkeypatch.setattr(_Path, "read_bytes", boom)

        with caplog.at_level(logging.WARNING, logger="mm.notebook"):
            result = _render_native_video(path, "scope", 320)

        assert "<video controls" not in result
        assert "Video unreadable" in result
        assert "scope-placeholder" in result
        assert any("simulated read failure" in rec.message for rec in caplog.records)

    def test_audio_unreadable_returns_placeholder(self, tmp_path, monkeypatch, caplog):
        import logging

        path = tmp_path / "broken.mp3"
        path.write_bytes(b"ID3\x04\x00\x00" + b"\x00" * 1024)

        from pathlib import Path as _Path

        def boom(self):
            raise OSError("simulated read failure")

        monkeypatch.setattr(_Path, "read_bytes", boom)

        with caplog.at_level(logging.WARNING, logger="mm.notebook"):
            result = _render_native_audio(path, "scope")

        assert "<audio controls" not in result
        assert "Audio unreadable" in result
        assert "scope-placeholder" in result
        assert any("simulated read failure" in rec.message for rec in caplog.records)

    def test_video_placeholder_escapes_filename(self, tmp_path, monkeypatch):
        # The placeholder rendered when a video is too large to embed must
        # html-escape the filename — otherwise a maliciously named file could
        # inject HTML when the Context is rendered in Jupyter.
        from mm import notebook as nb

        monkeypatch.setattr(nb, "_VIDEO_EMBED_MAX_BYTES", 100)
        # `&` and `<` are valid on POSIX filesystems and trigger the escape path.
        path = tmp_path / "evil&<bad>.mp4"
        path.write_bytes(b"\x00" * 2000)
        result = _render_native_video(path, "scope", 320)
        assert "<bad>" not in result
        assert "&lt;bad&gt;" in result
        assert "&amp;" in result

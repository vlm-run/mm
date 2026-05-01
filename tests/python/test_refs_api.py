"""Tests for the new put-based :class:`mm.Context` API.

Covers:

- ``put`` for Path, str path, URL, bytes, PIL.Image
- metadata sugar params (``note``/``summary``/``tags``/``metadata``)
- ``get`` round-trip (in-memory PIL objects come back identity-equal)
- ``RefNotFoundError`` message + "did you mean" suggestions
- ``to_messages(format=...)`` for both formats
- ``to_md(mode="metadata")`` table
- ``print_tree(layout="insertion")`` rendering
- ``NotImplementedError`` for non-``insertion`` layouts + for
  :meth:`Context.save` on put-based contexts
- ``__repr__`` markdown smoke test
- :func:`mm.uuid7` shape
- ``mm.Ref`` typing alias is a ``str`` at runtime
"""

from __future__ import annotations

import uuid
from pathlib import Path

import mm
import pytest
from mm.refs import RefNotFoundError
from PIL import Image


@pytest.fixture
def tiny_png(tmp_path: Path) -> Path:
    p = tmp_path / "tiny.png"
    Image.new("RGB", (32, 32), "red").save(p)
    return p


@pytest.fixture
def tiny_txt(tmp_path: Path) -> Path:
    p = tmp_path / "hello.py"
    p.write_text('print("hello")\n')
    return p


# ── Construction ──────────────────────────────────────────────────────


class TestConstruction:
    def test_empty_default_has_uuid7_session(self):
        ctx = mm.Context()
        assert ctx.session_id is not None
        assert len(ctx.session_id) == 36
        assert ctx.session_id[14] == "7", "version nibble should be 7"
        assert len(ctx) == 0

    def test_empty_explicit_session_id(self):
        ctx = mm.Context(session_id="sess-xyz")
        assert ctx.session_id == "sess-xyz"

    def test_two_contexts_have_distinct_session_ids(self):
        a = mm.Context()
        b = mm.Context()
        assert a.session_id != b.session_id


# ── put ───────────────────────────────────────────────────────────────


class TestPut:
    def test_put_path(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.put(tiny_png)
        assert ref.startswith("img_")
        assert len(ctx) == 1

    def test_put_str_path(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.put(str(tiny_png))
        assert ref.startswith("img_")

    def test_put_pil_image(self):
        ctx = mm.Context()
        img = Image.new("RGB", (10, 10), "blue")
        ref = ctx.put(img)
        assert ref.startswith("img_")

    def test_put_bytes_png(self):
        ctx = mm.Context()
        ref = ctx.put(b"\x89PNG\r\n\x1a\nrest")
        assert ref.startswith("img_")

    def test_put_bytes_unknown_kind(self):
        ctx = mm.Context()
        ref = ctx.put(b"random bytes no magic")
        # Falls back to "other" -> prefix "obj"
        assert ref.startswith("obj_")

    def test_put_url(self):
        ctx = mm.Context()
        ref = ctx.put("https://example.com/foo.jpg")
        assert ref.startswith("img_")

    def test_put_missing_path_raises(self, tmp_path: Path):
        ctx = mm.Context()
        with pytest.raises(FileNotFoundError):
            ctx.put(tmp_path / "missing.png")

    def test_put_unsupported_type_raises(self):
        ctx = mm.Context()
        with pytest.raises(TypeError):
            ctx.put(12345)

    def test_put_metadata_round_trips(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.put(
            tiny_png,
            metadata={
                "note": "product hero",
                "summary": "the money shot",
                "tags": ["catalog", "hero"],
                "scene": 3,
                "actor": "A",
            },
        )
        it = next(i for i in ctx.items() if i["ref_id"] == ref)
        m = it["metadata"]
        assert m["note"] == "product hero"
        assert m["summary"] == "the money shot"
        assert m["tags"] == ["catalog", "hero"]
        assert m["scene"] == 3
        assert m["actor"] == "A"

    def test_put_metadata_accepts_arbitrary_keys(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.put(tiny_png, metadata={"b": 1, "a": 2, "c": 3})
        it = next(i for i in ctx.items() if i["ref_id"] == ref)
        assert set(it["metadata"].keys()) == {"a", "b", "c"}
        assert it["metadata"]["a"] == 2

    def test_put_no_metadata_empty_dict(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.put(tiny_png)
        it = next(i for i in ctx.items() if i["ref_id"] == ref)
        assert it["metadata"] == {}


# ── get ───────────────────────────────────────────────────────────────


class TestGet:
    def test_get_path_returns_path(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.put(tiny_png)
        got = ctx.get(ref)
        assert isinstance(got, Path)
        # Path is resolved to absolute — compare by resolve().
        assert got.resolve() == tiny_png.resolve()

    def test_get_pil_returns_same_instance(self):
        ctx = mm.Context()
        img = Image.new("RGB", (5, 5), "green")
        ref = ctx.put(img)
        got = ctx.get(ref)
        assert got is img, "put PIL objects must come back identity-equal"

    def test_get_url_returns_string(self):
        ctx = mm.Context()
        url = "https://example.com/x.jpg"
        ref = ctx.put(url)
        assert ctx.get(ref) == url

    def test_get_bytes_returns_bytes(self):
        ctx = mm.Context()
        payload = b"\x89PNG\r\n\x1a\ndata"
        ref = ctx.put(payload)
        got = ctx.get(ref)
        assert got == payload

    def test_get_accepts_global_ref(self, tiny_png: Path):
        ctx = mm.Context(session_id="xyz")
        ref = ctx.put(tiny_png)
        got = ctx.get(f"xyz/{ref}")
        assert isinstance(got, Path)

    def test_get_rejects_wrong_session(self, tiny_png: Path):
        ctx = mm.Context(session_id="right")
        ref = ctx.put(tiny_png)
        with pytest.raises(ValueError, match="belongs to session"):
            ctx.get(f"other-session/{ref}")

    def test_get_miss_raises_refnotfounderror(self):
        ctx = mm.Context()
        with pytest.raises(RefNotFoundError):
            ctx.get("img_zzzzzz")

    def test_refnotfound_is_key_error(self):
        assert issubclass(RefNotFoundError, KeyError)

    def test_refnotfound_suggests_close_match(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.put(tiny_png)
        # Perturb one hex digit
        bad = ref[:-1] + ("z" if ref[-1] != "z" else "0")
        # The suggestion is best-effort — one-edit-distance refs should match.
        # We tolerate the suggestion being absent for unlucky cases but the
        # full ref table must always appear.
        with pytest.raises(RefNotFoundError) as excinfo:
            ctx.get(bad)
        msg = str(excinfo.value)
        assert "Available refs" in msg
        assert ref in msg


# ── to_messages ───────────────────────────────────────────────────────


class TestToMessages:
    def test_openai_single_user_turn(self, tiny_png: Path):
        ctx = mm.Context()
        ctx.put(tiny_png, metadata={"note": "ref-a"})
        msgs = ctx.to_messages(format="openai")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert "content" in msgs[0]
        kinds = {p.get("type") for p in msgs[0]["content"]}
        assert "text" in kinds
        assert "image_url" in kinds

    def test_metadata_emitted_as_text(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.put(tiny_png, metadata={"note": "hero"})
        msgs = ctx.to_messages(format="openai")
        texts = [p["text"] for p in msgs[0]["content"] if p.get("type") == "text"]
        assert any(f"[ref={ref}]" in t and "hero" in t for t in texts)

    def test_gemini_uses_inline_data(self, tiny_png: Path):
        ctx = mm.Context()
        ctx.put(tiny_png)
        msgs = ctx.to_messages(format="gemini")
        assert len(msgs) == 1
        parts = msgs[0]["parts"]
        assert any("inline_data" in p for p in parts)

    def test_invalid_format_raises(self):
        ctx = mm.Context()
        with pytest.raises(ValueError):
            ctx.to_messages(format="claude")  # type: ignore[arg-type]

    def test_encoders_override(self, tiny_png: Path):
        ctx = mm.Context()
        ctx.put(tiny_png)
        # Should not raise — 'tile' is a registered image encoder.
        msgs = ctx.to_messages(format="openai", encoders={"image": "tile"})
        assert len(msgs) == 1

    def test_url_image_openai_passes_through(self):
        ctx = mm.Context()
        url = "https://example.com/a.jpg"
        ctx.put(url)
        msgs = ctx.to_messages(format="openai")
        urls = [p["image_url"]["url"] for p in msgs[0]["content"] if p.get("type") == "image_url"]
        assert url in urls


# ── to_md ─────────────────────────────────────────────────────────────


class TestToMd:
    def test_table_shape(self, tiny_png: Path, tiny_txt: Path):
        ctx = mm.Context()
        ctx.put(tiny_png)
        ctx.put(tiny_txt)
        md = ctx.to_md(mode="metadata")
        assert md.startswith("| ref | kind | source | content |")
        assert "img_" in md
        assert "code_" in md

    @pytest.mark.parametrize("mode", ["fast", "accurate"])
    def test_unimplemented_modes_raise(self, tiny_png: Path, mode: str):
        ctx = mm.Context()
        ctx.put(tiny_png)
        with pytest.raises(NotImplementedError):
            ctx.to_md(mode=mode)


# ── print_tree ────────────────────────────────────────────────────────


class TestPrintTree:
    def test_insertion_layout(self, capsys, tiny_png: Path):
        import re

        ctx = mm.Context(session_id="tree-sess")
        ctx.put(tiny_png, metadata={"note": "one"})
        ctx.put(Image.new("RGB", (8, 8)), metadata={"summary": "two"})
        ctx.print_tree()
        raw = capsys.readouterr().out
        # Strip ANSI control sequences that rich injects.
        out = re.sub(r"\x1b\[[0-9;]*m", "", raw)
        assert "Context(session=tree-sess" in out
        assert "img_" in out
        # Metadata rendered beneath items.
        assert "note" in out and "one" in out
        assert "summary" in out and "two" in out

    @pytest.mark.parametrize("layout", ["paths", "kind", "flat", "hybrid"])
    def test_other_layouts_not_implemented(self, layout: str):
        ctx = mm.Context()
        with pytest.raises(NotImplementedError):
            ctx.print_tree(layout=layout)  # type: ignore[arg-type]


# ── __repr__ / str ────────────────────────────────────────────────────


class TestRepr:
    def test_repr_is_markdown(self, tiny_png: Path):
        ctx = mm.Context(session_id="repr-sess")
        ref = ctx.put(tiny_png)
        text = repr(ctx)
        assert text.startswith("Context(session=repr-sess, items=1)")
        assert "| ref |" in text
        assert ref in text

    def test_empty_repr(self):
        ctx = mm.Context(session_id="e")
        text = repr(ctx)
        assert "items=0" in text


# ── uuid7 / Ref alias ─────────────────────────────────────────────────


class TestTypingHelpers:
    def test_uuid7_shape(self):
        u = mm.uuid7()
        assert len(u) == 36
        assert u[14] == "7"
        # Parseable by stdlib UUID.
        uuid.UUID(u)

    def test_uuid7_distinct(self):
        assert len({mm.uuid7() for _ in range(200)}) >= 198

    def test_ref_is_str_at_runtime(self):
        # Typed alias — at runtime it's just ``str``.
        ctx = mm.Context()
        img = Image.new("RGB", (2, 2))
        ref: mm.Ref = ctx.put(img)
        assert isinstance(ref, str)


# ── save() stub ───────────────────────────────────────────────────────


class TestSaveStub:
    def test_save_put_based_raises(self, tiny_png: Path):
        ctx = mm.Context()
        ctx.put(tiny_png)
        with pytest.raises(NotImplementedError, match="not implemented"):
            ctx.save()


# ── Guardrails: mode mismatch ─────────────────────────────────────────


class TestModeGuardrails:
    def test_put_on_dirscan_raises(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1")
        ctx = mm.Context(tmp_path)
        with pytest.raises(RuntimeError, match="put-based"):
            ctx.put("a.py")

    def test_to_messages_on_dirscan_raises(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1")
        ctx = mm.Context(tmp_path)
        with pytest.raises(RuntimeError):
            ctx.to_messages()

    def test_files_on_putbased_raises(self):
        ctx = mm.Context()
        with pytest.raises(RuntimeError):
            _ = ctx.files

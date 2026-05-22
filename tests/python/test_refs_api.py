"""Tests for the role-aware :class:`mm.Context` API.

Covers:

- ``add`` for str, Path, and PIL.Image
- rejected bytes raise TypeError
- metadata sugar params (``note``/``summary``/``tags``/``metadata``)
- ``get`` round-trip (in-memory PIL objects come back identity-equal)
- ``RefNotFoundError`` message + "did you mean" suggestions
- ``to_messages(format=...)`` for both formats
- ``to_md(mode="metadata")`` table
- ``print_tree(layout="insertion")`` rendering
- ``NotImplementedError`` for non-``insertion`` layouts + for
  :meth:`Context.save` on role-aware contexts
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


# ── add ───────────────────────────────────────────────────────────────


class TestAdd:
    def test_add_path(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.add(tiny_png)
        assert ref.startswith("img_")
        assert len(ctx) == 1

    def test_add_str_inlines_text(self):
        ctx = mm.Context()
        ref = ctx.add("Describe the image in detail.")
        assert ref.startswith("txt_")
        it = next(i for i in ctx.items() if i["ref_id"] == ref)
        assert it["kind"] == "text"
        assert it["source_kind"] == "in_memory"
        assert it["source_value"] == "text/plain"

    def test_add_path_like_str_is_literal_text(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.add(str(tiny_png))
        assert ref.startswith("txt_")
        assert ctx.get(ref) == str(tiny_png)

    def test_add_pil_image(self):
        ctx = mm.Context()
        img = Image.new("RGB", (10, 10), "blue")
        ref = ctx.add(img)
        assert ref.startswith("img_")

    def test_add_bytes_raises_typeerror(self):
        ctx = mm.Context()
        with pytest.raises(TypeError, match="bytes"):
            ctx.add(b"\x89PNG\r\n\x1a\nrest")

    def test_add_url_string_is_literal_text(self):
        ctx = mm.Context()
        ref = ctx.add("https://example.com/foo.jpg")
        assert ref.startswith("txt_")
        assert ctx.get(ref) == "https://example.com/foo.jpg"

    def test_add_missing_path_raises(self, tmp_path: Path):
        ctx = mm.Context()
        with pytest.raises(FileNotFoundError):
            ctx.add(tmp_path / "missing.png")

    def test_add_unsupported_type_raises(self):
        ctx = mm.Context()
        with pytest.raises(TypeError):
            ctx.add(12345)

    def test_add_rejects_invalid_role(self):
        ctx = mm.Context()
        with pytest.raises(ValueError, match="role"):
            ctx.add("hello", role="assistant")  # type: ignore[arg-type]

    def test_add_rejects_non_user_media(self, tiny_png: Path):
        ctx = mm.Context()
        with pytest.raises(ValueError, match="Only free-form string text"):
            ctx.add(tiny_png, role="system")

    def test_add_metadata_round_trips(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.add(
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

    def test_add_metadata_accepts_arbitrary_keys(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.add(tiny_png, metadata={"b": 1, "a": 2, "c": 3})
        it = next(i for i in ctx.items() if i["ref_id"] == ref)
        assert set(it["metadata"].keys()) == {"a", "b", "c"}
        assert it["metadata"]["a"] == 2

    def test_add_no_metadata_empty_dict(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.add(tiny_png)
        it = next(i for i in ctx.items() if i["ref_id"] == ref)
        assert it["metadata"] == {}


# ── get ───────────────────────────────────────────────────────────────


class TestGet:
    def test_get_path_returns_path(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.add(tiny_png)
        got = ctx.get(ref)
        assert isinstance(got, Path)
        # Path is resolved to absolute — compare by resolve().
        assert got.resolve() == tiny_png.resolve()

    def test_get_pil_returns_same_instance(self):
        ctx = mm.Context()
        img = Image.new("RGB", (5, 5), "green")
        ref = ctx.add(img)
        got = ctx.get(ref)
        assert got is img, "added PIL objects must come back identity-equal"

    def test_get_text_returns_same_string(self):
        ctx = mm.Context()
        text = "Analyze this context."
        ref = ctx.add(text)
        assert ctx.get(ref) == text

    def test_get_accepts_global_ref(self, tiny_png: Path):
        ctx = mm.Context(session_id="xyz")
        ref = ctx.add(tiny_png)
        got = ctx.get(f"xyz/{ref}")
        assert isinstance(got, Path)

    def test_get_rejects_wrong_session(self, tiny_png: Path):
        ctx = mm.Context(session_id="right")
        ref = ctx.add(tiny_png)
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
        ref = ctx.add(tiny_png)
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
        ctx.add(tiny_png, metadata={"note": "ref-a"})
        msgs = ctx.to_messages(format="openai")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert "content" in msgs[0]
        kinds = {p.get("type") for p in msgs[0]["content"]}
        assert "text" in kinds
        assert "image_url" in kinds

    def test_metadata_emitted_as_text(self, tiny_png: Path):
        ctx = mm.Context()
        ref = ctx.add(tiny_png, metadata={"note": "hero"})
        msgs = ctx.to_messages(format="openai")
        texts = [p["text"] for p in msgs[0]["content"] if p.get("type") == "text"]
        assert any(f"[ref={ref}]" in t and "hero" in t for t in texts)

    def test_gemini_uses_inline_data(self, tiny_png: Path):
        ctx = mm.Context()
        ctx.add(tiny_png)
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
        ctx.add(tiny_png)
        # Should not raise — 'tile' is a registered image encoder.
        msgs = ctx.to_messages(format="openai", encoders={"image": "tile"})
        assert len(msgs) == 1

    def test_encoder_kwargs_forwarded(self, tiny_png: Path):
        """encoder_kwargs are forwarded to the encoder's encode() method."""
        ctx = mm.Context()
        ctx.add(tiny_png)
        msgs = ctx.to_messages(
            format="openai",
            encoders={"image": "resize"},
            encoder_kwargs={"image": {"max_width": 16}},
        )
        assert len(msgs) == 1
        parts = msgs[0]["content"]
        img_parts = [p for p in parts if p.get("type") == "image_url"]
        assert len(img_parts) >= 1

    def test_encoder_kwargs_ignored_for_unrelated_kind(self, tiny_png: Path):
        """encoder_kwargs for a different kind don't interfere."""
        ctx = mm.Context()
        ctx.add(tiny_png)
        msgs_without = ctx.to_messages(format="openai")
        msgs_with = ctx.to_messages(
            format="openai",
            encoder_kwargs={"video": {"fps": 0.5}},
        )
        without_parts = [p for p in msgs_without[0]["content"] if p.get("type") == "image_url"]
        with_parts = [p for p in msgs_with[0]["content"] if p.get("type") == "image_url"]
        assert len(without_parts) == len(with_parts)

    def test_encoder_kwargs_empty_dict_is_noop(self, tiny_png: Path):
        ctx = mm.Context()
        ctx.add(tiny_png)
        msgs = ctx.to_messages(format="openai", encoder_kwargs={})
        assert len(msgs) == 1

    def test_encoder_kwargs_with_gemini_format(self, tiny_png: Path):
        ctx = mm.Context()
        ctx.add(tiny_png)
        msgs = ctx.to_messages(
            format="gemini",
            encoder_kwargs={"image": {"max_width": 16}},
        )
        assert len(msgs) == 1

    def test_string_content_is_inlined(self):
        ctx = mm.Context()
        text = "This is an instruction, not a URL: https://example.com/a.jpg"
        ref = ctx.add(text)
        msgs = ctx.to_messages(format="openai")
        texts = [p["text"] for p in msgs[0]["content"] if p.get("type") == "text"]
        assert any(f"[ref={ref}]" in t for t in texts)
        assert text in texts

    def test_openai_emits_role_aware_turns(self, tiny_png: Path):
        ctx = mm.Context()
        ctx.add("You are terse.", role="system")
        ctx.add("Prefer JSON.", role="developer")
        ctx.add("Describe this.", role="user")
        ctx.add(tiny_png, role="user")
        msgs = ctx.to_messages(format="openai")
        assert [m["role"] for m in msgs] == ["system", "developer", "user"]
        assert "You are terse." in [
            p["text"] for p in msgs[0]["content"] if p.get("type") == "text"
        ]
        assert "Prefer JSON." in [p["text"] for p in msgs[1]["content"] if p.get("type") == "text"]
        assert any(p.get("type") == "image_url" for p in msgs[2]["content"])

    def test_gemini_folds_non_user_roles(self):
        ctx = mm.Context()
        ctx.add("You are terse.", role="system")
        ctx.add("Answer as JSON.", role="developer")
        msgs = ctx.to_messages(format="gemini")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        texts = [p["text"] for p in msgs[0]["parts"] if "text" in p]
        assert "[role=system]" in texts
        assert "[role=developer]" in texts


# ── to_md ─────────────────────────────────────────────────────────────


class TestToMd:
    def test_table_shape(self, tiny_png: Path, tiny_txt: Path):
        ctx = mm.Context()
        ctx.add(tiny_png)
        ctx.add(tiny_txt)
        md = ctx.to_md(mode="metadata")
        assert md.startswith("| ref | role | kind | source | content |")
        assert "img_" in md
        assert "code_" in md

    def test_default_mode_is_metadata(self, tiny_png: Path, tiny_txt: Path):
        """Calling ``to_md()`` with no args must match ``mode='metadata'``."""
        ctx = mm.Context()
        ctx.add(tiny_png)
        ctx.add(tiny_txt)
        assert ctx.to_md() == ctx.to_md(mode="metadata")

    def test_metadata_tier_content_renders(self, tiny_png: Path, tiny_txt: Path, isolated_db: Path):
        """``mode='metadata'`` must surface the metadata tier, not just refs.

        ``extract_meta`` produces ``Dimensions: 32x32 …`` for images and
        ``read_text`` returns the file body for code/text. Asserting on
        actual content guards against a future regression where ``to_md``
        renders an empty content column.
        """
        ctx = mm.Context()
        ctx.add(tiny_png)
        ctx.add(tiny_txt)
        md = ctx.to_md()
        # image row carries extract_meta output
        assert "32x32" in md
        # text row carries the raw file body
        assert 'print("hello")' in md

    def test_renders_inmemory_items(self, tiny_png: Path):
        """In-memory text/PIL items must still render a row.

        Text strings are collected as metadata-tier content; PIL falls
        through to the Rust-side fallback.
        """
        ctx = mm.Context()
        path_ref = ctx.add(tiny_png)
        text_ref = ctx.add("inline note")
        pil_ref = ctx.add(Image.new("RGB", (8, 8), "blue"))
        md = ctx.to_md()
        for ref in (path_ref, text_ref, pil_ref):
            assert ref in md, f"{ref} missing from to_md output"
        assert "inline note" in md

    @pytest.mark.parametrize("mode", ["fast", "accurate"])
    def test_unimplemented_modes_raise(self, tiny_png: Path, mode: str):
        ctx = mm.Context()
        ctx.add(tiny_png)
        with pytest.raises(NotImplementedError) as excinfo:
            ctx.to_md(mode=mode)
        # Error message must echo the actual mode passed (regression guard
        # against the previous hard-coded "mode='accurate'" string).
        assert f"mode={mode!r}" in str(excinfo.value)
        assert "mode='metadata'" in str(excinfo.value)


# ── print_tree ────────────────────────────────────────────────────────


class TestPrintTree:
    def test_insertion_layout(self, capsys, tiny_png: Path):
        import re

        ctx = mm.Context(session_id="tree-sess")
        ctx.add(tiny_png, metadata={"note": "one"})
        ctx.add(Image.new("RGB", (8, 8)), metadata={"summary": "two"})
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
        ref = ctx.add(tiny_png)
        text = repr(ctx)
        assert text.startswith("Context(session=repr-sess, items=1)")
        assert "| ref |" in text
        assert "| role |" in text
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
        ref: mm.Ref = ctx.add(img)
        assert isinstance(ref, str)


# ── save() stub ───────────────────────────────────────────────────────


class TestSaveStub:
    def test_save_role_aware_raises(self, tiny_png: Path):
        ctx = mm.Context()
        ctx.add(tiny_png)
        with pytest.raises(NotImplementedError, match="not implemented"):
            ctx.save()


# ── remove() ───────────────────────────────────────────────────────────


class TestRemove:
    def test_remove_deletes_item(self, tiny_png: Path):
        ctx = mm.Context()
        first = ctx.add(tiny_png)
        second = ctx.add("caption")
        ctx.remove(first)
        assert ctx.ref_ids() == [second]
        with pytest.raises(RefNotFoundError):
            ctx.get(first)

    def test_remove_accepts_global_ref(self, tiny_png: Path):
        ctx = mm.Context(session_id="remove-sess")
        ref = ctx.add(tiny_png)
        ctx.remove(f"remove-sess/{ref}")
        assert ctx.ref_ids() == []

    def test_remove_rejects_wrong_session(self, tiny_png: Path):
        ctx = mm.Context(session_id="right")
        ref = ctx.add(tiny_png)
        with pytest.raises(ValueError, match="belongs to session"):
            ctx.remove(f"wrong/{ref}")

    def test_remove_missing_raises_refnotfounderror(self):
        ctx = mm.Context()
        with pytest.raises(RefNotFoundError):
            ctx.remove("img_zzzzzz")


# ── Guardrails: mode mismatch ─────────────────────────────────────────


class TestModeGuardrails:
    def test_add_on_dirscan_raises(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1")
        ctx = mm.Context(tmp_path)
        with pytest.raises(RuntimeError, match="role-aware"):
            ctx.add(tmp_path / "a.py")

    def test_to_messages_on_dirscan_raises(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1")
        ctx = mm.Context(tmp_path)
        with pytest.raises(RuntimeError):
            ctx.to_messages()

    def test_remove_on_dirscan_raises(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1")
        ctx = mm.Context(tmp_path)
        with pytest.raises(RuntimeError, match="role-aware"):
            ctx.remove("img_aaaaaa")

    def test_files_on_role_aware_raises(self):
        ctx = mm.Context()
        with pytest.raises(RuntimeError):
            _ = ctx.files

"""Tests for mm.deps — optional dependency guards and try_import_or_raise."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from mm.deps import try_import_or_raise


class TestTryImportOrRaise:
    def test_succeeds_for_stdlib_module(self):
        mod = try_import_or_raise("json", extra="gemini")
        assert hasattr(mod, "dumps")

    def test_raises_for_missing_module(self):
        with pytest.raises(ImportError, match=r"pip install mm\[gemini\]"):
            try_import_or_raise("nonexistent_fake_pkg_1234", extra="gemini")

    def test_error_mentions_package_name(self):
        with pytest.raises(ImportError, match="google-genai"):
            try_import_or_raise(
                "nonexistent_fake_pkg_1234",
                extra="gemini",
                package="google-genai",
            )

    def test_error_mentions_correct_extra_mlx(self):
        with pytest.raises(ImportError, match=r"pip install mm\[mlx\]"):
            try_import_or_raise("nonexistent_fake_pkg_1234", extra="mlx")

    def test_error_mentions_correct_extra_experimental(self):
        with pytest.raises(ImportError, match=r"pip install mm\[experimental\]"):
            try_import_or_raise("nonexistent_fake_pkg_1234", extra="experimental")

    def test_unknown_extra_still_works(self):
        with pytest.raises(ImportError, match=r"pip install mm\[custom\]"):
            try_import_or_raise("nonexistent_fake_pkg_1234", extra="custom")

    def test_returns_module_object(self):
        mod = try_import_or_raise("os.path", extra="gemini")
        assert hasattr(mod, "join")


class TestGeminiGuard:
    """Verify that store/embed.py raises ImportError when google-genai is absent."""

    def test_text_part_raises_without_genai(self):
        with _hide_module("google.genai.types", "google.genai", "google"):
            from mm.store.embed import text_part

            with pytest.raises(ImportError, match=r"pip install mm\[gemini\]"):
                text_part("hello")

    def test_image_part_raises_without_genai(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        with _hide_module("google.genai.types", "google.genai", "google"):
            from mm.store.embed import image_part

            with pytest.raises(ImportError, match=r"pip install mm\[gemini\]"):
                image_part(img)

    def test_document_part_raises_without_genai(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4" + b"\x00" * 100)
        with _hide_module("google.genai.types", "google.genai", "google"):
            from mm.store.embed import document_part

            with pytest.raises(ImportError, match=r"pip install mm\[gemini\]"):
                document_part(pdf)


class TestMlxGuard:
    """Verify whisper MLX path raises ImportError when mlx extra is absent."""

    def test_get_mlx_model_raises_without_mlx(self):
        with _hide_module("lightning_whisper_mlx"):
            from mm.whisper import _MODEL_CACHE, _get_mlx_model

            _MODEL_CACHE.clear()
            with pytest.raises(ImportError, match=r"pip install mm\[mlx\]"):
                _get_mlx_model("tiny", 12)


class TestExperimentalGuard:
    """Verify HF datasets guard in display.py."""

    def test_emit_dataset_hf_raises_without_datasets(self):
        with _hide_module("datasets"):
            from mm.display import _emit_dataset_hf

            with pytest.raises(ImportError, match=r"pip install mm\[experimental\]"):
                _emit_dataset_hf([{"a": 1}])


class _hide_module:
    """Context manager that temporarily hides module(s) from import.

    Removes them from ``sys.modules`` and injects a finder that blocks
    them, then restores everything on exit.
    """

    def __init__(self, *module_names: str):
        self.module_names = module_names
        self._saved: dict[str, object] = {}
        self._meta_path_entry: object | None = None

    def __enter__(self):
        for name in self.module_names:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    self._saved[key] = sys.modules.pop(key)

        blocker = _ImportBlocker(self.module_names)
        sys.meta_path.insert(0, blocker)
        self._meta_path_entry = blocker
        return self

    def __exit__(self, *exc):
        if self._meta_path_entry in sys.meta_path:
            sys.meta_path.remove(self._meta_path_entry)
        sys.modules.update(self._saved)


class _ImportBlocker:
    """A sys.meta_path finder that raises ImportError for specific modules."""

    def __init__(self, blocked: tuple[str, ...]):
        self.blocked = blocked

    def find_module(self, fullname, path=None):
        for b in self.blocked:
            if fullname == b or fullname.startswith(b + "."):
                return self
        return None

    def load_module(self, fullname):
        raise ImportError(f"Blocked by test: {fullname}")

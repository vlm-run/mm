"""Tests for mm.deps — optional dependency guards and try_import_or_raise."""

from __future__ import annotations

import sys

import pytest

from mm.deps import try_import_or_raise


class TestTryImportOrRaise:
    def test_succeeds_for_stdlib_module(self):
        mod = try_import_or_raise("json", extra="mlx")
        assert hasattr(mod, "dumps")

    def test_raises_for_missing_module(self):
        with pytest.raises(ImportError, match=r"pip install mm-ctx\[mlx\]"):
            try_import_or_raise("nonexistent_fake_pkg_1234", extra="mlx")

    def test_error_mentions_package_name(self):
        with pytest.raises(ImportError, match="lightning-whisper-mlx"):
            try_import_or_raise(
                "nonexistent_fake_pkg_1234",
                extra="mlx",
                package="lightning-whisper-mlx",
            )

    def test_error_mentions_correct_extra_mlx(self):
        with pytest.raises(ImportError, match=r"pip install mm-ctx\[mlx\]"):
            try_import_or_raise("nonexistent_fake_pkg_1234", extra="mlx")

    def test_error_mentions_correct_extra_experimental(self):
        with pytest.raises(ImportError, match=r"pip install mm-ctx\[experimental\]"):
            try_import_or_raise("nonexistent_fake_pkg_1234", extra="experimental")

    def test_unknown_extra_still_works(self):
        with pytest.raises(ImportError, match=r"pip install mm-ctx\[custom\]"):
            try_import_or_raise("nonexistent_fake_pkg_1234", extra="custom")

    def test_returns_module_object(self):
        mod = try_import_or_raise("os.path", extra="mlx")
        assert hasattr(mod, "join")


class TestMlxGuard:
    """Verify whisper MLX path raises ImportError when mlx extra is absent."""

    def test_get_mlx_model_raises_without_mlx(self):
        with _hide_module("lightning_whisper_mlx"):
            from mm.common.audio._mlx import _MODEL_CACHE, _get_model

            _MODEL_CACHE.clear()
            with pytest.raises(ImportError, match=r"pip install mm.*\[mlx\]"):
                _get_model("tiny", 12)


class TestExperimentalGuard:
    """Verify HF datasets guard in display.py."""

    def test_emit_dataset_hf_raises_without_datasets(self):
        with _hide_module("datasets"):
            from mm.display import _emit_dataset_hf

            with pytest.raises(ImportError, match=r"pip install mm-ctx\[experimental\]"):
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

    def find_spec(self, fullname, path=None, target=None):
        for b in self.blocked:
            if fullname == b or fullname.startswith(b + "."):
                raise ImportError(f"Blocked by test: {fullname}")
        return None

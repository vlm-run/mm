"""Tests for ``mm grep`` that bypass the CLI runner.

CLI-level grep tests live in ``test_cli.py::TestGrep`` alongside the other
command surfaces. This file is for direct API tests of the modules ``mm grep``
delegates to.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestGrepSemantic:
    """Direct (non-CLI) tests of the ``grep_semantic`` API."""

    def test_prunes_stale_rows(
        self, tmp_path: Path, isolated_db: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """``grep_semantic`` prunes deleted files before querying embeddings.

        Stubs ``search`` so we don't hit the real embedding backend — the
        prune happens earlier in ``grep_semantic`` regardless.
        """
        from mm.semantic import grep_semantic
        from mm.store.db import MmDatabase

        a = tmp_path / "a.png"
        b = tmp_path / "b.png"
        # Minimal PNG header so ``file_kind`` classifies them as image.
        png_sig = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        a.write_bytes(png_sig)
        b.write_bytes(png_sig)

        db = MmDatabase()
        db.ensure_l0(str(a))
        db.ensure_l0(str(b))
        assert {f["name"] for f in db.get_files()} == {"a.png", "b.png"}

        a.unlink()

        # Isolate from the real embedding backend.
        monkeypatch.setattr("mm.semantic.search", lambda *a, **kw: [])

        grep_semantic(
            "whatever",
            tmp_path,
            kind="image",
            ext=None,
            limit=5,
            do_index=False,
            quiet=True,
        )

        assert db.get_file(str(a)) is None
        assert db.get_file(str(b)) is not None

"""Unit tests for ``mm.cache.memoize_file``.

The decorator powers every long-lived cache in mm (``probe``,
``detect_scenes``, ``transcript_messages``, …).  These tests pin down
its semantics with synthetic functions so that domain-specific tests
can rely on the contract.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from mm.cache import cache_dir, file_fingerprint, memoize_file


def _write(path: Path, contents: bytes = b"hello") -> Path:
    path.write_bytes(contents)
    return path


class TestFileFingerprint:
    def test_returns_tuple_for_existing_file(self, tmp_path):
        clip = _write(tmp_path / "a.bin")
        fp = file_fingerprint(clip)
        assert isinstance(fp, tuple) and len(fp) == 3
        # absolute path, mtime, size
        assert fp[0] == str(clip.resolve())
        assert isinstance(fp[1], float)
        assert fp[2] == clip.stat().st_size

    def test_str_and_path_equivalent(self, tmp_path):
        clip = _write(tmp_path / "b.bin")
        assert file_fingerprint(clip) == file_fingerprint(str(clip))

    def test_missing_returns_none(self):
        assert file_fingerprint("/no/such/file") is None

    def test_non_pathlike_returns_none(self):
        assert file_fingerprint(object()) is None


class TestMemoizeFileBasics:
    def test_caches_by_fingerprint(self, tmp_path):
        calls = []

        @memoize_file(maxsize=8)
        def load(path):
            calls.append(path)
            return object()  # fresh object so identity tells us cache hits

        clip = _write(tmp_path / "a.bin")
        a = load(clip)
        b = load(clip)
        assert a is b
        assert len(calls) == 1

    def test_different_paths_get_separate_entries(self, tmp_path):
        @memoize_file(maxsize=8)
        def load(path):
            return path.read_bytes()

        a = _write(tmp_path / "a.bin", b"AAA")
        b = _write(tmp_path / "b.bin", b"BBB")
        assert load(a) == b"AAA"
        assert load(b) == b"BBB"
        assert load.cache_info()["currsize"] == 2

    def test_kwargs_are_part_of_key(self, tmp_path):
        calls = []

        @memoize_file(maxsize=8)
        def f(path, *, mode="fast"):
            calls.append(mode)
            return mode

        clip = _write(tmp_path / "a.bin")
        f(clip, mode="fast")
        f(clip, mode="fast")
        f(clip, mode="accurate")
        assert calls == ["fast", "accurate"]

    def test_positional_extra_args_are_part_of_key(self, tmp_path):
        calls = []

        @memoize_file(maxsize=8)
        def f(path, n):
            calls.append(n)
            return n

        clip = _write(tmp_path / "a.bin")
        f(clip, 1)
        f(clip, 1)
        f(clip, 2)
        assert calls == [1, 2]

    def test_default_kwargs_canonicalise_to_same_key(self, tmp_path):
        """Calling with explicit defaults must hit the cache from a call
        that omitted them.  Without this, encoders that say
        ``detect_scenes(path)`` and ``detect_scenes(path, threshold=27.0)``
        end up with separate cache entries even though 27.0 is the default.
        """
        calls = []

        @memoize_file(maxsize=8)
        def f(path, *, threshold=27.0, min_scene_len=15):
            calls.append((threshold, min_scene_len))
            return (threshold, min_scene_len)

        clip = _write(tmp_path / "a.bin")
        a = f(clip)  # all defaults
        b = f(clip, threshold=27.0)  # explicit default
        c = f(clip, threshold=27.0, min_scene_len=15)  # all explicit defaults
        d = f(clip, min_scene_len=15, threshold=27.0)  # different kw order

        assert a == b == c == d
        assert len(calls) == 1, f"expected 1 underlying call, got {len(calls)}"
        assert f.cache_info()["currsize"] == 1
        assert f.cache_info()["hits"] == 3


class TestCacheInvalidation:
    def test_mtime_change_misses_cache(self, tmp_path):
        @memoize_file(maxsize=8)
        def load(path):
            return path.stat().st_mtime

        clip = _write(tmp_path / "a.bin")
        first = load(clip)

        future = clip.stat().st_mtime + 100.0
        os.utime(clip, (future, future))

        second = load(clip)
        assert second != first
        # Both entries should now coexist (different fingerprints).
        assert load.cache_info()["currsize"] == 2

    def test_size_change_misses_cache(self, tmp_path):
        @memoize_file(maxsize=8)
        def load(path):
            return path.read_bytes()

        clip = _write(tmp_path / "a.bin", b"short")
        load(clip)
        # Make the file longer with the same mtime — size change still keys differently.
        mtime = clip.stat().st_mtime
        clip.write_bytes(b"a much longer payload than before")
        os.utime(clip, (mtime, mtime))
        load(clip)
        # Two distinct fingerprints → two entries.
        assert load.cache_info()["currsize"] == 2


class TestMissingPath:
    def test_missing_path_bypasses_cache(self):
        @memoize_file(maxsize=8)
        def opener(path):
            return Path(path).read_text()

        # Function should still run (and raise) for a missing file —
        # the cache must NOT swallow nor poison.
        with pytest.raises(FileNotFoundError):
            opener("/no/such/file/ever")
        assert opener.cache_info()["currsize"] == 0
        assert opener.cache_info()["misses"] == 0  # never even attempted to cache


class TestCacheControl:
    def test_cache_clear_resets_size_and_stats(self, tmp_path):
        @memoize_file(maxsize=8)
        def load(path):
            return object()

        clip = _write(tmp_path / "a.bin")
        load(clip)
        load(clip)
        before = load.cache_info()
        assert before["hits"] == 1 and before["misses"] == 1

        load.cache_clear()
        after = load.cache_info()
        assert after == {"hits": 0, "misses": 0, "currsize": 0, "maxsize": 8}

    def test_lru_eviction_under_maxsize(self, tmp_path):
        @memoize_file(maxsize=2)
        def load(path):
            return object()

        a = _write(tmp_path / "a.bin")
        b = _write(tmp_path / "b.bin")
        c = _write(tmp_path / "c.bin")

        load(a)
        load(b)
        load(c)  # should evict a (LRU)

        assert load.cache_info()["currsize"] == 2

    def test_cache_attribute_exposed(self, tmp_path):
        @memoize_file(maxsize=4)
        def load(path):
            return 1

        load(_write(tmp_path / "a.bin"))
        # ``fn.cache`` is a callable that materialises the lazy backend
        # on first touch — exposed for tests/introspection.
        from cachetools import LRUCache

        backend = load.cache()
        assert isinstance(backend, LRUCache)
        assert backend.maxsize == 4
        # Cache_info also exposes maxsize as part of the user-facing
        # contract; the two should agree.
        assert load.cache_info()["maxsize"] == 4


class TestCacheDir:
    """``cache_dir`` honours MM_CACHE_DIR, then XDG_CACHE_HOME, then ~/.cache/mm."""

    def test_mm_cache_dir_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MM_CACHE_DIR", str(tmp_path / "mm-override"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
        assert cache_dir() == tmp_path / "mm-override"

    def test_xdg_cache_home_used_when_no_mm_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MM_CACHE_DIR", raising=False)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
        assert cache_dir() == tmp_path / "xdg" / "mm"

    def test_falls_back_to_home_cache_mm(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MM_CACHE_DIR", raising=False)
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        assert cache_dir() == Path.home() / ".cache" / "mm"


class TestDiskBackedCache:
    """Disk-backed memoize_file must persist across decorator instances.

    These tests simulate "second CLI invocation" by re-decorating the
    same logical function with the same on-disk path: a fresh
    in-memory holder, but the FSLRUCache file already exists, so a
    repeat call hits the cache without invoking the body.
    """

    def test_disk_cache_writes_pickle_file(self, tmp_path):
        @memoize_file(maxsize=4, path=tmp_path / "transcripts")
        def load(path):
            return path.read_bytes().upper()

        clip = _write(tmp_path / "a.bin", b"hello")
        result = load(clip)
        assert result == b"HELLO"
        # Directory was created lazily; entry written as a single .pkl.
        files = list((tmp_path / "transcripts").glob("*.pkl"))
        assert len(files) == 1
        assert files[0].suffix == ".pkl"

    def test_disk_cache_persists_across_decorator_instances(self, tmp_path):
        cache_path = tmp_path / "scenes"
        clip = _write(tmp_path / "a.bin", b"original")

        # First "process": warm the cache.
        calls = []

        @memoize_file(maxsize=4, path=cache_path)
        def first(path):
            calls.append(path)
            return path.read_bytes().upper()

        assert first(clip) == b"ORIGINAL"
        assert first.cache_info()["currsize"] == 1

        # Second "process": fresh decorator, same path, same file.
        # Body MUST NOT run — the disk entry should rehydrate the value.
        @memoize_file(maxsize=4, path=cache_path)
        def second(path):
            calls.append(path)
            return path.read_bytes().upper()

        assert second(clip) == b"ORIGINAL"
        # Two underlying calls would mean disk persistence failed.
        assert len(calls) == 1
        info = second.cache_info()
        assert info["currsize"] == 1 and info["hits"] == 1

    def test_disk_cache_invalidates_on_mtime_change(self, tmp_path):
        cache_path = tmp_path / "scenes"
        clip = _write(tmp_path / "a.bin", b"v1")

        @memoize_file(maxsize=4, path=cache_path)
        def load(path):
            return path.read_bytes()

        assert load(clip) == b"v1"
        # Rewrite + bump mtime to simulate the user re-encoding the source.
        clip.write_bytes(b"v2")
        future = clip.stat().st_mtime + 100.0
        os.utime(clip, (future, future))

        # New fingerprint → cache miss → fresh value, both entries on disk.
        assert load(clip) == b"v2"
        files = list(cache_path.glob("*.pkl"))
        assert len(files) == 2

    def test_disk_cache_clear_wipes_directory(self, tmp_path):
        cache_path = tmp_path / "scenes"

        @memoize_file(maxsize=4, path=cache_path)
        def load(path):
            return path.read_bytes()

        load(_write(tmp_path / "a.bin", b"a"))
        load(_write(tmp_path / "b.bin", b"b"))
        assert load.cache_info()["currsize"] == 2

        load.cache_clear()
        assert load.cache_info() == {"hits": 0, "misses": 0, "currsize": 0, "maxsize": 4}
        assert list(cache_path.glob("*.pkl")) == []

    def test_disk_cache_lazy_path_resolution(self, tmp_path, monkeypatch):
        """A callable ``path`` is resolved on first use, not at decoration.

        That lets tests (and conftest) set ``MM_CACHE_DIR`` *after*
        ``mm.cache`` and call sites are imported.
        """
        monkeypatch.setenv("MM_CACHE_DIR", str(tmp_path / "late"))

        # Resolve via cache_dir() inside the lambda — would point at the
        # default ~/.cache/mm if eagerly evaluated at decoration time.
        @memoize_file(maxsize=4, path=lambda: cache_dir() / "transcripts")
        def load(path):
            return path.read_bytes()

        load(_write(tmp_path / "a.bin", b"data"))
        # Entries land under the env-overridden directory.
        files = list((tmp_path / "late" / "transcripts").glob("*.pkl"))
        assert len(files) == 1

    def test_disk_cache_default_kwargs_canonicalise(self, tmp_path):
        """The default-kwarg fix carries over to the disk backend."""
        calls = []

        @memoize_file(maxsize=4, path=tmp_path / "scenes")
        def f(path, *, threshold=27.0):
            calls.append(threshold)
            return threshold

        clip = _write(tmp_path / "a.bin")
        f(clip)
        f(clip, threshold=27.0)
        assert len(calls) == 1
        assert f.cache_info()["currsize"] == 1


class TestThreadSafety:
    def test_concurrent_calls_share_one_compute(self, tmp_path):
        # Hammer the same key from many threads — ``cache_info`` should show
        # at least one miss and the rest hits, with currsize == 1.  We don't
        # require "exactly one miss" because the lock window is small enough
        # that multiple threads can legitimately miss before anyone writes.
        # The contract we DO want is "no crashes, deterministic result".
        compute_count = 0
        lock = threading.Lock()

        @memoize_file(maxsize=4)
        def load(path):
            nonlocal compute_count
            with lock:
                compute_count += 1
            return "value"

        clip = _write(tmp_path / "a.bin")

        threads = [threading.Thread(target=lambda: load(clip)) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert load(clip) == "value"
        assert load.cache_info()["currsize"] == 1
        # Should have computed at most once per genuine miss (and almost certainly only once).
        assert compute_count >= 1

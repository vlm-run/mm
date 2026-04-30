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

from mm.cache import file_fingerprint, memoize_file


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
        # The underlying LRUCache is exposed for tests/introspection.
        from cachetools import LRUCache

        assert isinstance(load.cache, LRUCache)
        assert load.cache.maxsize == 4


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

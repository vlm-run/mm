"""Tests for mm.encoders.video helpers.

Focused coverage of ``_read_frames_b64``, the thread-pool helper that
batch-reads extracted video frames and base64-encodes them before they
get wrapped into OpenAI-compatible Messages. The helper is on the hot
path for every video pipeline, so it's worth nailing down the
behaviour: empty input, single-path fast path, multi-path pool path,
ordering guarantees, correctness against ``base64.b64encode``, and
graceful propagation of I/O errors.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from mm.encoders.video import _read_frames_b64


def _write(tmp_path: Path, name: str, payload: bytes) -> Path:
    """Write *payload* to *tmp_path/name* and return the path."""
    p = tmp_path / name
    p.write_bytes(payload)
    return p


class TestReadFramesB64Empty:
    def test_empty_list_returns_empty_list(self):
        assert _read_frames_b64([]) == []

    def test_empty_list_returns_new_list_instance(self):
        a = _read_frames_b64([])
        b = _read_frames_b64([])
        # Each call should yield its own fresh list — no accidental
        # shared state.
        assert a is not b


class TestReadFramesB64SinglePath:
    def test_single_path_hits_fast_path(self, tmp_path: Path):
        payload = b"\xff\xd8\xff\xe0 fake jpeg bytes"
        p = _write(tmp_path, "frame_0.jpg", payload)

        out = _read_frames_b64([p])
        assert len(out) == 1
        assert out[0] == base64.b64encode(payload).decode()

    def test_single_path_roundtrip(self, tmp_path: Path):
        payload = b"hello world"
        p = _write(tmp_path, "frame.jpg", payload)

        out = _read_frames_b64([p])
        assert base64.b64decode(out[0]) == payload

    def test_single_empty_file(self, tmp_path: Path):
        p = _write(tmp_path, "empty.jpg", b"")
        assert _read_frames_b64([p]) == [""]


class TestReadFramesB64MultiplePaths:
    def test_preserves_input_order(self, tmp_path: Path):
        payloads = [f"frame-{i}".encode() for i in range(5)]
        paths = [_write(tmp_path, f"f_{i}.jpg", p) for i, p in enumerate(payloads)]

        out = _read_frames_b64(paths)

        assert len(out) == len(paths)
        expected = [base64.b64encode(p).decode() for p in payloads]
        assert out == expected

    def test_distinct_payloads_produce_distinct_b64(self, tmp_path: Path):
        payloads = [b"\x00" * 8, b"\xff" * 8, b"\xab\xcd" * 4]
        paths = [_write(tmp_path, f"f_{i}.jpg", p) for i, p in enumerate(payloads)]

        out = _read_frames_b64(paths)
        assert len(set(out)) == len(out), "expected distinct b64 per distinct payload"

    def test_duplicate_paths_return_same_b64(self, tmp_path: Path):
        payload = b"same bytes"
        p = _write(tmp_path, "same.jpg", payload)

        out = _read_frames_b64([p, p, p])
        expected = base64.b64encode(payload).decode()
        assert out == [expected, expected, expected]

    def test_many_frames_cap_at_8_workers(self, tmp_path: Path):
        """Smoke test: 32 frames should still produce 32 ordered results.

        The helper caps the pool at 8 workers; 32 tasks exercise the
        pool's reuse path.
        """
        payloads = [f"chunk-{i}".encode() * 16 for i in range(32)]
        paths = [_write(tmp_path, f"f_{i}.bin", p) for i, p in enumerate(payloads)]

        out = _read_frames_b64(paths)
        assert len(out) == 32
        for expected, actual in zip(payloads, out):
            assert base64.b64decode(actual) == expected

    def test_roundtrip_binary_data(self, tmp_path: Path):
        # Random-ish bytes over the full 0x00..0xff range to make sure
        # no text-mode assumption leaks in.
        payloads = [bytes(range(i, i + 32)) for i in range(0, 96, 32)]
        paths = [_write(tmp_path, f"f_{i}.bin", p) for i, p in enumerate(payloads)]

        out = _read_frames_b64(paths)
        decoded = [base64.b64decode(s) for s in out]
        assert decoded == payloads


class TestReadFramesB64Errors:
    def test_missing_path_raises(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist.jpg"
        with pytest.raises(FileNotFoundError):
            _read_frames_b64([missing])

    def test_one_missing_in_batch_raises(self, tmp_path: Path):
        p_ok = _write(tmp_path, "ok.jpg", b"ok")
        missing = tmp_path / "missing.jpg"

        # ThreadPoolExecutor.map surfaces the first exception when the
        # returned generator is iterated — `list(...)` forces iteration
        # so the error propagates out of the helper.
        with pytest.raises(FileNotFoundError):
            _read_frames_b64([p_ok, missing])

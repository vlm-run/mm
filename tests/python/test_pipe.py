"""Tests for pipe detection and composability."""

from __future__ import annotations

import io
import json
import sys

from mm.pipe import is_piped_input, is_piped_output, read_paths_from_stdin


def test_is_piped_input_in_tests():
    result = is_piped_input()
    assert isinstance(result, bool)


def test_is_piped_output_in_tests():
    result = is_piped_output()
    assert isinstance(result, bool)


def test_read_paths_empty_when_tty(monkeypatch):
    """When stdin is a TTY, read_paths_from_stdin should return empty."""

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", FakeTTY())
    paths = read_paths_from_stdin()
    assert paths == []


# ---------------------------------------------------------------------------
# Bare paths
# ---------------------------------------------------------------------------


def test_read_bare_paths(monkeypatch):
    """Bare paths, one per line."""

    class FakePipe(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", FakePipe("src/main.py\nsrc/lib.rs\n\n"))

    paths = read_paths_from_stdin()
    assert paths == ["src/main.py", "src/lib.rs"]


# ---------------------------------------------------------------------------
# TSV with header
# ---------------------------------------------------------------------------


def test_read_tsv_with_header(monkeypatch):
    """TSV output from 'mm find' — header row should be skipped."""

    class FakePipe(io.StringIO):
        def isatty(self):
            return False

    tsv = "kind\tsize\tpath\nimage\t4301\tsrc/photo.png\ncode\t1200\tsrc/main.py\n"
    monkeypatch.setattr(sys, "stdin", FakePipe(tsv))

    paths = read_paths_from_stdin()
    assert paths == ["src/photo.png", "src/main.py"]


def test_read_tsv_no_header(monkeypatch):
    """TSV without a recognizable header — all rows treated as data."""

    class FakePipe(io.StringIO):
        def isatty(self):
            return False

    tsv = "image\t4301\tsrc/photo.png\ncode\t1200\tsrc/main.py\n"
    monkeypatch.setattr(sys, "stdin", FakePipe(tsv))

    paths = read_paths_from_stdin()
    assert paths == ["src/photo.png", "src/main.py"]


# ---------------------------------------------------------------------------
# JSON input
# ---------------------------------------------------------------------------


def test_read_json_array_of_objects(monkeypatch):
    """JSON array of objects with 'path' key."""

    class FakePipe(io.StringIO):
        def isatty(self):
            return False

    data = [{"path": "src/main.py", "kind": "code"}, {"path": "img.png", "kind": "image"}]
    monkeypatch.setattr(sys, "stdin", FakePipe(json.dumps(data)))

    paths = read_paths_from_stdin()
    assert paths == ["src/main.py", "img.png"]


def test_read_json_array_of_strings(monkeypatch):
    """JSON array of plain strings."""

    class FakePipe(io.StringIO):
        def isatty(self):
            return False

    data = ["src/main.py", "img.png"]
    monkeypatch.setattr(sys, "stdin", FakePipe(json.dumps(data)))

    paths = read_paths_from_stdin()
    assert paths == ["src/main.py", "img.png"]


# ---------------------------------------------------------------------------
# CSV with header
# ---------------------------------------------------------------------------


def test_read_csv_with_header(monkeypatch):
    """CSV output — header row should be skipped, last field extracted."""

    class FakePipe(io.StringIO):
        def isatty(self):
            return False

    csv_data = "kind,size,path\nimage,4301,src/photo.png\ncode,1200,src/main.py\n"
    monkeypatch.setattr(sys, "stdin", FakePipe(csv_data))

    paths = read_paths_from_stdin()
    assert paths == ["src/photo.png", "src/main.py"]


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_read_empty_pipe(monkeypatch):
    """Empty piped input returns empty list."""

    class FakePipe(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", FakePipe(""))

    paths = read_paths_from_stdin()
    assert paths == []

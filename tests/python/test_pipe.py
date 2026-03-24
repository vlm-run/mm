"""Tests for pipe detection and composability."""

from __future__ import annotations

import io
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


def test_read_paths_from_pipe(monkeypatch):
    """When stdin is piped with data, read_paths_from_stdin returns paths.

    select.select() doesn't work with StringIO, so we monkeypatch
    is_piped_input to return True and replace stdin with a FakePipe.
    """

    class FakePipe(io.StringIO):
        def isatty(self):
            return False

    fake_stdin = FakePipe("src/main.py\nsrc/lib.rs\n\n")
    monkeypatch.setattr(sys, "stdin", fake_stdin)
    monkeypatch.setattr("mm.pipe.is_piped_input", lambda: True)
    paths = read_paths_from_stdin()
    assert paths == ["src/main.py", "src/lib.rs"]

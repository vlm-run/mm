"""Tests for pipe detection and composability."""

from __future__ import annotations

from vlmctx.pipe import is_piped_input, is_piped_output, read_paths_from_stdin


def test_is_piped_input_in_tests():
    """In test runner, stdin is typically not a TTY."""
    # This just validates the function doesn't error
    result = is_piped_input()
    assert isinstance(result, bool)


def test_is_piped_output_in_tests():
    result = is_piped_output()
    assert isinstance(result, bool)


def test_read_paths_empty_when_tty(monkeypatch):
    """When stdin is a TTY, read_paths_from_stdin should return empty."""
    import sys
    import io

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", FakeTTY())
    paths = read_paths_from_stdin()
    assert paths == []


def test_read_paths_from_pipe(monkeypatch):
    """When stdin is piped, read_paths_from_stdin should return paths."""
    import sys
    import io

    class FakePipe(io.StringIO):
        def isatty(self):
            return False

    fake_stdin = FakePipe("src/main.py\nsrc/lib.rs\n\n")
    monkeypatch.setattr(sys, "stdin", fake_stdin)
    paths = read_paths_from_stdin()
    assert paths == ["src/main.py", "src/lib.rs"]

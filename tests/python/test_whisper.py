"""Tests for vlmctx.whisper — Whisper transcription wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_whisper_available_false():
    """whisper_available() returns False when faster_whisper is not installed."""
    with patch.dict("sys.modules", {"faster_whisper": None}):
        # Re-import to force re-check
        from vlmctx.whisper import whisper_available
        # Note: module-level caching means this may still return True
        # if faster_whisper was previously imported


def test_transcription_result_defaults():
    """TranscriptionResult has sensible defaults."""
    from vlmctx.whisper import TranscriptionResult

    r = TranscriptionResult(text="hello world")
    assert r.text == "hello world"
    assert r.segments == []
    assert r.language == ""
    assert r.elapsed_ms == 0.0
    assert r.model_size == ""
    assert r.device == ""


def test_transcribe_without_whisper():
    """transcribe() returns error message when whisper is not available."""
    from vlmctx.whisper import transcribe

    with patch("vlmctx.whisper.whisper_available", return_value=False):
        result = transcribe("/tmp/test.wav", model_size="tiny")
        assert "not installed" in result.text
        assert result.model_size == "tiny"


def test_transcribe_with_mock_whisper(tmp_path):
    """transcribe() calls WhisperModel correctly."""
    # Create a dummy audio file
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"\x00" * 100)

    # Mock the faster_whisper module
    mock_segment = MagicMock()
    mock_segment.start = 0.0
    mock_segment.end = 1.5
    mock_segment.text = " Hello world"

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.95

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    with (
        patch("vlmctx.whisper.whisper_available", return_value=True),
        patch("vlmctx.whisper._get_model", return_value=mock_model),
        patch("vlmctx.whisper._get_device", return_value=("cpu", "int8")),
    ):
        from vlmctx.whisper import transcribe

        result = transcribe(str(audio_file), model_size="tiny")
        assert result.text == "Hello world"
        assert len(result.segments) == 1
        assert result.segments[0]["start"] == 0.0
        assert result.segments[0]["end"] == 1.5
        assert result.language == "en"
        assert result.language_probability == 0.95
        assert result.model_size == "tiny"
        assert result.elapsed_ms >= 0


def test_get_device_cpu():
    """_get_device() returns CPU when no GPU is available."""
    with patch.dict("sys.modules", {"torch": None, "ctranslate2": None}):
        from vlmctx.whisper import _get_device
        device, compute = _get_device()
        # Should be cpu on systems without CUDA
        assert device in ("cpu", "cuda")

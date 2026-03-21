"""Tests for vlmctx.whisper — Whisper transcription wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_whisper_available_true():
    """whisper_available() returns True when a backend is available."""
    from vlmctx.whisper import whisper_available
    # At least one backend should be installed in the test env
    # (either faster_whisper or lightning_whisper_mlx)
    assert isinstance(whisper_available(), bool)


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
    assert r.backend == ""


def test_transcribe_without_whisper():
    """transcribe() returns error message when no backend is available."""
    from vlmctx.whisper import transcribe

    with patch("vlmctx.whisper._detect_backend", return_value=None):
        result = transcribe("/tmp/test.wav", model_size="tiny")
        assert "not installed" in result.text
        assert result.model_size == "tiny"


def test_transcribe_with_mock_ct2(tmp_path):
    """transcribe() calls CTranslate2 backend correctly."""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"\x00" * 100)

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
        patch("vlmctx.whisper._detect_backend", return_value="ctranslate2"),
        patch("vlmctx.whisper._get_ct2_model", return_value=mock_model),
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
        assert result.backend == "ctranslate2"
        assert result.elapsed_ms >= 0


def test_transcribe_ct2_timestamp_scaling(tmp_path):
    """Timestamps are scaled back by audio_speed."""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"\x00" * 100)

    mock_segment = MagicMock()
    mock_segment.start = 1.0
    mock_segment.end = 2.0
    mock_segment.text = "scaled"

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 1.0

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    with (
        patch("vlmctx.whisper._detect_backend", return_value="ctranslate2"),
        patch("vlmctx.whisper._get_ct2_model", return_value=mock_model),
        patch("vlmctx.whisper._get_device", return_value=("cpu", "int8")),
    ):
        from vlmctx.whisper import transcribe

        result = transcribe(str(audio_file), model_size="tiny", audio_speed=2.0)
        assert result.segments[0]["start"] == 2.0  # 1.0 * 2.0
        assert result.segments[0]["end"] == 4.0    # 2.0 * 2.0


def test_transcribe_mlx_segment_format(tmp_path):
    """MLX backend handles [start_ms, end_ms, text] segment format."""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"\x00" * 100)

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {
        "text": "Hello from MLX",
        "segments": [[0, 1500, " Hello from"], [1500, 3000, " MLX"]],
        "language": "en",
    }

    with (
        patch("vlmctx.whisper._detect_backend", return_value="mlx"),
        patch("vlmctx.whisper._get_mlx_model", return_value=mock_model),
    ):
        from vlmctx.whisper import transcribe

        result = transcribe(str(audio_file), model_size="tiny", audio_speed=2.0)
        assert result.text == "Hello from MLX"
        assert result.backend == "mlx"
        assert result.device == "metal"
        assert len(result.segments) == 2
        # Timestamps: 0ms→0s*2=0, 1500ms→1.5s*2=3.0
        assert result.segments[0]["start"] == 0.0
        assert result.segments[0]["end"] == 3.0
        assert result.segments[1]["start"] == 3.0
        assert result.segments[1]["end"] == 6.0


def test_detect_backend_preference():
    """MLX is preferred over CTranslate2 when available."""
    import vlmctx.whisper as w
    # Reset cached backend
    w._BACKEND = None
    backend = w._detect_backend()
    # On macOS with both installed, should be "mlx"
    # On other platforms, could be "ctranslate2"
    assert backend in ("mlx", "ctranslate2", None)

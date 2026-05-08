"""Tests for mm.common.audio — modular transcription backends."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestTranscriptionResult:
    def test_defaults(self):
        from mm.common.audio import TranscriptionResult

        r = TranscriptionResult(text="hello world")
        assert r.text == "hello world"
        assert r.segments == []
        assert r.language == ""
        assert r.elapsed_ms == 0.0
        assert r.model_size == ""
        assert r.device == ""
        assert r.backend == ""


class TestRegistry:
    def test_list_backends_returns_tuples(self):
        from mm.common.audio import list_backends

        backends = list_backends()
        assert len(backends) >= 3
        names = [name for name, _ in backends]
        assert "mlx" in names
        assert "ctranslate2" in names
        assert "openai" in names

    def test_list_backends_sorted_by_priority(self):
        from mm.common.audio import list_backends

        backends = list_backends()
        names = [name for name, _ in backends]
        assert names.index("mlx") < names.index("ctranslate2")
        assert names.index("ctranslate2") < names.index("openai")

    def test_detect_backend_by_name(self):
        from mm.common.audio import detect_backend
        from mm.common.audio._base import _reset

        _reset()
        be = detect_backend(name="openai")
        assert be is not None
        assert be.name == "openai"

    def test_detect_backend_unknown_returns_none(self):
        from mm.common.audio import detect_backend

        assert detect_backend(name="nonexistent") is None

    def test_detect_backend_auto(self):
        from mm.common.audio import detect_backend
        from mm.common.audio._base import _reset

        _reset()
        be = detect_backend()
        # At least one backend should be available in the test env
        assert be is None or be.name in ("mlx", "ctranslate2", "openai")

    def test_transcribe_available(self):
        from mm.common.audio import transcribe_available

        assert isinstance(transcribe_available(), bool)


class TestDetectWithOverrides:
    def test_openai_with_custom_url(self):
        from mm.common.audio import detect_backend

        be = detect_backend(name="openai", base_url="http://localhost:9999/v1")
        assert be is not None
        assert be.name == "openai"
        assert be._base_url == "http://localhost:9999/v1"

    def test_non_openai_ignores_url(self):
        from mm.common.audio import detect_backend

        be = detect_backend(name="ctranslate2", base_url="http://example.com")
        assert be is not None
        assert be.name == "ctranslate2"


class TestTranscribeNoBackend:
    def test_returns_error_message(self):
        from mm.common.audio import transcribe
        from mm.common.audio._base import _reset

        _reset()
        with patch("mm.common.audio.detect_backend", return_value=None):
            result = transcribe("/tmp/test.wav", model="tiny")
            assert "no transcription backend" in result.text


class TestCTranslate2Backend:
    def test_transcribe_mock(self, tmp_path):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_seg = MagicMock()
        mock_seg.start = 0.0
        mock_seg.end = 1.5
        mock_seg.text = " Hello world"

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.95

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_seg], mock_info)

        with (
            patch("mm.common.audio._ctranslate2._get_model", return_value=mock_model),
            patch("mm.common.audio._ctranslate2._get_device", return_value=("cpu", "int8")),
        ):
            from mm.common.audio._ctranslate2 import CTranslate2Backend

            be = CTranslate2Backend()
            result = be.transcribe(audio, model="tiny")
            assert result.text == "Hello world"
            assert len(result.segments) == 1
            assert result.segments[0].start == 0.0
            assert result.segments[0].end == 1.5
            assert result.language == "en"
            assert result.backend == "ctranslate2"

    def test_timestamp_scaling(self, tmp_path):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_seg = MagicMock()
        mock_seg.start = 1.0
        mock_seg.end = 2.0
        mock_seg.text = "scaled"

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_seg], mock_info)

        with (
            patch("mm.common.audio._ctranslate2._get_model", return_value=mock_model),
            patch("mm.common.audio._ctranslate2._get_device", return_value=("cpu", "int8")),
        ):
            from mm.common.audio._ctranslate2 import CTranslate2Backend

            be = CTranslate2Backend()
            result = be.transcribe(audio, model="tiny", audio_speed=2.0)
            assert result.segments[0].start == 2.0
            assert result.segments[0].end == 4.0


class TestMLXBackend:
    def test_segment_format(self, tmp_path):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Hello from MLX",
            "segments": [[0, 1500, " Hello from"], [1500, 3000, " MLX"]],
            "language": "en",
        }

        with patch("mm.common.audio._mlx._get_model", return_value=mock_model):
            from mm.common.audio._mlx import MLXBackend

            be = MLXBackend()
            result = be.transcribe(audio, model="tiny", audio_speed=2.0)
            assert result.text == "Hello from MLX"
            assert result.backend == "mlx"
            assert result.device == "metal"
            assert len(result.segments) == 2
            assert result.segments[0].start == 0.0
            assert result.segments[0].end == 3.0
            assert result.segments[1].start == 3.0
            assert result.segments[1].end == 6.0


class TestOpenAIBackend:
    def test_transcribe_mock(self, tmp_path):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_seg = MagicMock()
        mock_seg.start = 0.0
        mock_seg.end = 2.5
        mock_seg.text = " Hello from API"

        mock_resp = MagicMock()
        mock_resp.text = "Hello from API"
        mock_resp.language = "en"
        mock_resp.segments = [mock_seg]

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with patch("openai.OpenAI", return_value=mock_client) as MockOpenAI:
            from mm.common.audio._openai import OpenAIBackend

            be = OpenAIBackend(base_url="http://localhost:11434/v1", api_key="test-key")
            result = be.transcribe(audio, model="whisper-1")

            assert result.text == "Hello from API"
            assert result.language == "en"
            assert result.backend == "openai"
            assert result.device == "remote"
            assert len(result.segments) == 1
            assert result.segments[0].end == 2.5

            MockOpenAI.assert_called_once_with(
                base_url="http://localhost:11434/v1",
                api_key="test-key",
                timeout=120.0,
            )
            mock_client.audio.transcriptions.create.assert_called_once()

    def test_default_base_url_is_gateway(self, tmp_path):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.text = ""
        mock_resp.language = ""
        mock_resp.segments = []

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with patch("openai.OpenAI", return_value=mock_client) as MockOpenAI:
            from mm.common.audio._openai import OpenAIBackend
            from mm.profile import GATEWAY_BASE_URL

            be = OpenAIBackend()
            be.transcribe(audio)

            MockOpenAI.assert_called_once_with(
                base_url=GATEWAY_BASE_URL,
                api_key="noop",
                timeout=120.0,
            )

    def test_timestamp_scaling(self, tmp_path):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_seg = MagicMock()
        mock_seg.start = 1.0
        mock_seg.end = 2.0
        mock_seg.text = "scaled"

        mock_resp = MagicMock()
        mock_resp.text = "scaled"
        mock_resp.language = "en"
        mock_resp.segments = [mock_seg]

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with patch("openai.OpenAI", return_value=mock_client):
            from mm.common.audio._openai import OpenAIBackend

            be = OpenAIBackend(base_url="http://localhost/v1")
            result = be.transcribe(audio, model="whisper-1", audio_speed=2.0)
            assert result.segments[0].start == 2.0
            assert result.segments[0].end == 4.0


class TestTranscriptionConfig:
    def test_defaults_all_none(self):
        from mm.config import TranscriptionConfig

        cfg = TranscriptionConfig()
        assert cfg.backend is None
        assert cfg.base_url is None
        assert cfg.api_key is None

    def test_get_transcription_config_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mm.config._find_config_path", lambda: tmp_path / "mm.toml")
        from mm.config import get_transcription_config

        cfg = get_transcription_config()
        assert cfg.backend is None
        assert cfg.base_url is None

    def test_get_transcription_config_from_file(self, tmp_path, monkeypatch):
        toml = tmp_path / "mm.toml"
        toml.write_text(
            '[transcription]\nbackend = "openai"\nbase_url = "http://localhost:11434/v1"\n'
        )
        monkeypatch.setattr("mm.config._find_config_path", lambda: toml)
        from mm.config import get_transcription_config

        cfg = get_transcription_config()
        assert cfg.backend == "openai"
        assert cfg.base_url == "http://localhost:11434/v1"
        assert cfg.api_key is None

    def test_update_config_key_transcription(self, tmp_path, monkeypatch):
        from mm.config import ConfigData, write_full_config

        toml_path = tmp_path / "mm.toml"
        monkeypatch.setattr("mm.config._find_config_path", lambda: toml_path)

        from typing import cast

        from mm.config import ProfileData

        write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": "ollama",
                    "profile": {
                        "ollama": cast(
                            ProfileData, {"base_url": "http://a", "api_key": "", "model": "m"}
                        )
                    },
                },
            )
        )

        from mm.config import update_config_key

        update_config_key("transcription.backend", "openai")
        update_config_key("transcription.base_url", "http://localhost:11434/v1")

        from mm.config import get_transcription_config

        cfg = get_transcription_config()
        assert cfg.backend == "openai"
        assert cfg.base_url == "http://localhost:11434/v1"

    def test_update_config_key_invalid_transcription_field(self, tmp_path, monkeypatch):
        toml_path = tmp_path / "mm.toml"
        monkeypatch.setattr("mm.config._find_config_path", lambda: toml_path)

        from typing import cast

        from mm.config import ConfigData, ProfileData, write_full_config

        write_full_config(
            cast(
                ConfigData,
                {
                    "active_profile": "ollama",
                    "profile": {
                        "ollama": cast(
                            ProfileData, {"base_url": "http://a", "api_key": "", "model": "m"}
                        )
                    },
                },
            )
        )

        from mm.config import update_config_key

        with pytest.raises(ValueError, match="Invalid transcription key"):
            update_config_key("transcription.model", "whisper-1")


class TestTopLevelTranscribe:
    def test_routes_to_named_backend(self, tmp_path):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_seg = MagicMock()
        mock_seg.start = 0.0
        mock_seg.end = 1.0
        mock_seg.text = "ok"

        mock_resp = MagicMock()
        mock_resp.text = "ok"
        mock_resp.language = "en"
        mock_resp.segments = [mock_seg]

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with patch("openai.OpenAI", return_value=mock_client):
            from mm.common.audio import transcribe

            result = transcribe(
                audio,
                model="whisper-1",
                backend="openai",
                base_url="http://localhost:11434/v1",
            )
            assert result.backend == "openai"
            assert result.text == "ok"

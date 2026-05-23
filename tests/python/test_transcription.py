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
    def test_openai_always_registered(self):
        from mm.common.audio import ACTIVE_VARIANT, list_backends

        backends = list_backends()
        names = [name for name, _ in backends]
        assert len(backends) >= 1
        assert "openai" in names
        assert ACTIVE_VARIANT in names

    def test_active_variant_is_valid(self):
        from mm.common.audio import ACTIVE_VARIANT

        assert ACTIVE_VARIANT in ("openai", "mlx", "ctranslate2")

    def test_detect_backend_by_name(self):
        from mm.common.audio import ACTIVE_VARIANT, detect_backend
        from mm.common.audio._base import _reset

        _reset()
        be = detect_backend(name=ACTIVE_VARIANT)
        assert be is not None
        assert be.name == ACTIVE_VARIANT

    def test_detect_backend_unknown_returns_none(self):
        from mm.common.audio import detect_backend

        assert detect_backend(name="nonexistent") is None

    def test_detect_backend_auto_selects_openai(self):
        """Auto-detection always returns openai, even if local backends are installed."""
        from mm.common.audio import detect_backend
        from mm.common.audio._base import _reset

        _reset()
        be = detect_backend()
        assert be is not None
        assert be.name == "openai"

    def test_transcribe_available(self):
        from mm.common.audio import transcribe_available

        assert transcribe_available() is True


class TestCustomBackend:
    """Verify that third-party backends can be registered and used."""

    def test_register_and_detect_custom_backend(self):
        from mm.common.audio import (
            TranscriptionBackend,
            TranscriptionResult,
            detect_backend,
            register_backend,
            unregister_backend,
        )
        from mm.common.audio._base import _reset

        class FakeGeminiBackend(TranscriptionBackend):
            name = "gemini"

            def available(self) -> bool:
                return True

            def transcribe(self, audio_path, *, model=None, **kw):
                return TranscriptionResult(text="gemini result", backend="gemini")

        _reset()
        register_backend(FakeGeminiBackend())
        try:
            be = detect_backend(name="gemini")
            assert be is not None
            assert be.name == "gemini"

            from pathlib import Path

            result = be.transcribe(Path("/tmp/test.wav"))
            assert result.text == "gemini result"
            assert result.backend == "gemini"
        finally:
            unregister_backend("gemini")
            _reset()

    def test_register_replaces_existing(self):
        from mm.common.audio import (
            TranscriptionBackend,
            TranscriptionResult,
            detect_backend,
            list_backends,
            register_backend,
            unregister_backend,
        )
        from mm.common.audio._base import _reset

        class V1(TranscriptionBackend):
            name = "custom"

            def available(self):
                return True

            def transcribe(self, audio_path, **kw):
                return TranscriptionResult(text="v1")

        class V2(TranscriptionBackend):
            name = "custom"

            def available(self):
                return True

            def transcribe(self, audio_path, **kw):
                return TranscriptionResult(text="v2")

        _reset()
        register_backend(V1())
        register_backend(V2())
        try:
            names = [n for n, _ in list_backends()]
            assert names.count("custom") == 1
            be = detect_backend(name="custom")
            assert isinstance(be, V2)
        finally:
            unregister_backend("custom")
            _reset()

    def test_unregister_backend(self):
        from mm.common.audio import (
            TranscriptionBackend,
            TranscriptionResult,
            detect_backend,
            register_backend,
            unregister_backend,
        )
        from mm.common.audio._base import _reset

        class Temp(TranscriptionBackend):
            name = "temp"

            def available(self):
                return True

            def transcribe(self, audio_path, **kw):
                return TranscriptionResult(text="temp")

        _reset()
        register_backend(Temp())
        assert detect_backend(name="temp") is not None
        assert unregister_backend("temp") is True
        assert detect_backend(name="temp") is None
        assert unregister_backend("temp") is False
        _reset()

    def test_auto_detect_still_returns_openai(self):
        """Custom backends don't affect auto-detection — openai is always the default."""
        from mm.common.audio import (
            TranscriptionBackend,
            TranscriptionResult,
            detect_backend,
            register_backend,
            unregister_backend,
        )
        from mm.common.audio._base import _reset

        class Custom(TranscriptionBackend):
            name = "custom"

            def available(self):
                return True

            def transcribe(self, audio_path, **kw):
                return TranscriptionResult(text="custom")

        _reset()
        register_backend(Custom())
        try:
            be = detect_backend()
            assert be is not None
            assert be.name == "openai"
        finally:
            unregister_backend("custom")
            _reset()


class TestDetectWithOverrides:
    def test_openai_always_selectable(self):
        """backend='openai' works even when local backends are installed."""
        from mm.common.audio import detect_backend
        from mm.common.audio._base import _reset

        _reset()
        be = detect_backend(name="openai")
        assert be is not None
        assert be.name == "openai"

    def test_openai_with_custom_url(self):
        from mm.common.audio import detect_backend

        be = detect_backend(name="openai", base_url="http://localhost:9999/v1")
        assert be is not None
        assert be.name == "openai"
        assert be._base_url == "http://localhost:9999/v1"


class TestTranscribeNoBackend:
    def test_returns_error_message(self):
        from mm.common.audio import transcribe
        from mm.common.audio._base import _reset

        _reset()
        with patch("mm.common.audio.detect_backend", return_value=None):
            result = transcribe("/tmp/test.wav", model="whisper-1")
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
            result = be.transcribe(audio, model="tiny", audio_speed=1.0)
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
            result = be.transcribe(audio, model="whisper-1", audio_speed=1.0)

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

    def test_falls_back_to_gateway_url(self, tmp_path):
        """When no base_url is set and no profile/config overrides exist, uses the gateway."""
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.text = "gateway transcription"
        mock_resp.language = "en"
        mock_resp.segments = []

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with (
            patch("openai.OpenAI", return_value=mock_client) as MockOpenAI,
            patch("mm.common.audio._openai._resolve_transcription_config", return_value=("", "")),
            patch("mm.common.audio._openai._resolve_profile_url", return_value=("", "")),
        ):
            from mm.common.audio._openai import GATEWAY_AUDIO_URL, OpenAIBackend

            be = OpenAIBackend(api_key="vlmrun")
            result = be.transcribe(audio)

            assert result.text == "gateway transcription"
            MockOpenAI.assert_called_once_with(
                base_url=GATEWAY_AUDIO_URL,
                api_key="vlmrun",
                timeout=120.0,
            )

    def test_prefers_transcription_config_over_profile(self, tmp_path):
        """[transcription] config takes precedence over the active profile."""
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.text = "from config"
        mock_resp.language = "en"
        mock_resp.segments = []

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with (
            patch("openai.OpenAI", return_value=mock_client) as MockOpenAI,
            patch(
                "mm.common.audio._openai._resolve_transcription_config",
                return_value=("http://localhost:9000/v1", "cfg-key"),
            ),
            patch(
                "mm.common.audio._openai._resolve_profile_url",
                return_value=("http://profile.example.com/v1", "profile-key"),
            ),
        ):
            from mm.common.audio._openai import OpenAIBackend

            be = OpenAIBackend()
            result = be.transcribe(audio)

            assert result.text == "from config"
            MockOpenAI.assert_called_once_with(
                base_url="http://localhost:9000/v1",
                api_key="cfg-key",
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

            be = OpenAIBackend(base_url="http://localhost/v1", api_key="test-key")
            result = be.transcribe(audio, model="whisper-1", audio_speed=2.0)
            assert result.segments[0].start == 2.0
            assert result.segments[0].end == 4.0

    def test_default_model_whisper_for_openai_url(self, tmp_path):
        """When base_url contains api.openai.com, model defaults to whisper-1."""
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.text = "hello"
        mock_resp.language = "en"
        mock_resp.segments = []

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with patch("openai.OpenAI", return_value=mock_client):
            from mm.common.audio._openai import OpenAIBackend

            be = OpenAIBackend(base_url="https://api.openai.com/v1", api_key="sk-test")
            be.transcribe(audio)
            call_kwargs = mock_client.audio.transcriptions.create.call_args
            assert call_kwargs[1]["model"] == "whisper-1"

    def test_default_model_parakeet_for_gateway(self, tmp_path):
        """When base_url is the gateway, model defaults to parakeet."""
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.text = "hello"
        mock_resp.language = "en"
        mock_resp.segments = []

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with (
            patch("openai.OpenAI", return_value=mock_client),
            patch("mm.common.audio._openai._resolve_transcription_config", return_value=("", "")),
            patch("mm.common.audio._openai._resolve_profile_url", return_value=("", "")),
        ):
            from mm.common.audio._openai import OpenAIBackend

            be = OpenAIBackend(api_key="vlmrun")
            be.transcribe(audio)
            call_kwargs = mock_client.audio.transcriptions.create.call_args
            assert call_kwargs[1]["model"] == "nvidia/parakeet-tdt-0.6b-v3"

    def test_no_env_var_reading(self, tmp_path):
        """OpenAI backend does not read OPENAI_API_KEY from environment."""
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.text = "hello"
        mock_resp.language = "en"
        mock_resp.segments = []

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with (
            patch("openai.OpenAI", return_value=mock_client) as MockOpenAI,
            patch("mm.common.audio._openai._resolve_transcription_config", return_value=("", "")),
            patch("mm.common.audio._openai._resolve_profile_url", return_value=("", "")),
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-from-env"}, clear=False),
        ):
            from mm.common.audio._openai import OpenAIBackend

            be = OpenAIBackend(api_key="vlmrun")
            be.transcribe(audio)
            MockOpenAI.assert_called_once_with(
                base_url="https://gateway.vlm.run/v1/openai",
                api_key="vlmrun",
                timeout=120.0,
            )


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
                api_key="test-key",
            )
            assert result.backend == "openai"
            assert result.text == "ok"

    def test_default_model_is_parakeet_for_openai(self, tmp_path):
        """When using the openai backend, model defaults to nvidia/parakeet-tdt-0.6b-v3."""
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.text = "hello"
        mock_resp.language = "en"
        mock_resp.segments = []

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp

        with (
            patch("openai.OpenAI", return_value=mock_client),
            patch("mm.common.audio._openai._resolve_transcription_config", return_value=("", "")),
            patch("mm.common.audio._openai._resolve_profile_url", return_value=("", "")),
        ):
            from mm.common.audio import GATEWAY_MODEL, transcribe
            from mm.common.audio._base import _reset

            _reset()
            transcribe(audio, backend="openai", api_key="vlmrun")
            call_kwargs = mock_client.audio.transcriptions.create.call_args
            assert call_kwargs[1]["model"] == GATEWAY_MODEL

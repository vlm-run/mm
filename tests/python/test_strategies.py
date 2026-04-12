"""Tests for mm.strategies — YAML loading, schema validation, prompt rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from mm.strategies import load, render_prompt, run_pyfunc
from mm.strategies.schema import Encode, Generate, TemplateSpec


class TestTemplateSpecSchema:
    """Pydantic model validation for strategy YAML files."""

    def test_valid_minimal(self):
        spec = TemplateSpec.model_validate({
            "kind": "image",
            "mode": "fast",
            "generate": {"prompt": "Describe this image."},
        })
        assert spec.kind == "image"
        assert spec.mode == "fast"
        assert spec.generate.prompt == "Describe this image."
        assert spec.generate.max_tokens == 256
        assert spec.generate.temperature is None
        assert spec.generate.json_mode is False
        assert spec.encode.strategy is None

    def test_valid_full(self):
        spec = TemplateSpec.model_validate({
            "kind": "video",
            "mode": "accurate",
            "encode": {
                "strategy": "frame-sample",
                "max_width": 512,
                "transcribe": True,
                "whisper_model": "medium",
            },
            "generate": {
                "prompt": "Describe the video {filename}.",
                "max_tokens": 1024,
                "temperature": 0.7,
                "json_mode": True,
            },
        })
        assert spec.encode.strategy == "frame-sample"
        assert spec.encode.max_width == 512
        assert spec.encode.transcribe is True
        assert spec.encode.whisper_model == "medium"
        assert spec.generate.max_tokens == 1024
        assert spec.generate.temperature == 0.7
        assert spec.generate.json_mode is True

    def test_missing_generate_prompt_raises(self):
        with pytest.raises(ValidationError):
            TemplateSpec.model_validate({
                "kind": "image",
                "mode": "fast",
                "generate": {"max_tokens": 256},
            })

    def test_missing_generate_raises(self):
        with pytest.raises(ValidationError):
            TemplateSpec.model_validate({
                "kind": "image",
                "mode": "fast",
            })

    def test_missing_kind_raises(self):
        with pytest.raises(ValidationError):
            TemplateSpec.model_validate({
                "mode": "fast",
                "generate": {"prompt": "test"},
            })

    def test_encode_defaults(self):
        enc = Encode()
        assert enc.strategy is None
        assert enc.strategy_kwargs == {}
        assert enc.max_width is None
        assert enc.mosaic_tile is None
        assert enc.transcribe is False
        assert enc.pyfunc is None

    def test_generate_defaults(self):
        gen = Generate(prompt="Hello")
        assert gen.max_tokens == 256
        assert gen.temperature is None
        assert gen.json_mode is False

    def test_extra_fields_ignored(self):
        spec = TemplateSpec.model_validate({
            "kind": "image",
            "mode": "fast",
            "generate": {"prompt": "test"},
            "extra_unknown": "should not break",
        })
        assert spec.kind == "image"


class TestLoad:
    """Tests for strategies.load() — YAML loading and caching."""

    def test_load_image_fast(self):
        spec = load("image", "fast")
        assert spec.kind == "image"
        assert spec.mode == "fast"
        assert isinstance(spec.generate.prompt, str)
        assert len(spec.generate.prompt) > 0

    def test_load_image_accurate(self):
        spec = load("image", "accurate")
        assert spec.kind == "image"
        assert spec.mode == "accurate"

    def test_load_video_fast(self):
        spec = load("video", "fast")
        assert spec.kind == "video"
        assert spec.mode == "fast"

    def test_load_video_accurate(self):
        spec = load("video", "accurate")
        assert spec.kind == "video"
        assert spec.mode == "accurate"

    def test_load_document_fast(self):
        spec = load("document", "fast")
        assert spec.kind == "document"

    def test_load_audio_fast(self):
        spec = load("audio", "fast")
        assert spec.kind == "audio"

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError, match="No strategy"):
            load("nonexistent_kind_xyz", "nonexistent_mode_abc")

    def test_all_builtin_yamls_valid(self):
        """Every builtin YAML should parse into a valid TemplateSpec."""
        strategies_dir = Path(__file__).resolve().parent.parent.parent / "python" / "mm" / "strategies"
        yaml_files = list(strategies_dir.rglob("*.yaml"))
        yaml_files = [f for f in yaml_files if f.name != "spec.yaml"]
        assert len(yaml_files) >= 8, f"Expected at least 8 YAML files, got {len(yaml_files)}"

        for yaml_file in yaml_files:
            data = yaml.safe_load(yaml_file.read_text())
            spec = TemplateSpec.model_validate(data)
            assert spec.kind in ("image", "video", "audio", "document")
            assert spec.mode in ("fast", "accurate")
            assert len(spec.generate.prompt) > 0


class TestRenderPrompt:
    """Tests for render_prompt — template interpolation."""

    def test_simple_substitution(self):
        spec = TemplateSpec.model_validate({
            "kind": "image",
            "mode": "fast",
            "generate": {"prompt": "Describe {filename} in {word_count} words."},
        })
        result = render_prompt(spec, {"filename": "photo.jpg", "word_count": "20"})
        assert result == "Describe photo.jpg in 20 words."

    def test_missing_key_becomes_empty(self):
        spec = TemplateSpec.model_validate({
            "kind": "video",
            "mode": "fast",
            "generate": {"prompt": "Video: {filename}. Duration: {duration_ctx}"},
        })
        result = render_prompt(spec, {"filename": "clip.mp4"})
        assert "clip.mp4" in result
        assert "Duration: " in result
        assert "{duration_ctx}" not in result

    def test_empty_context(self):
        spec = TemplateSpec.model_validate({
            "kind": "image",
            "mode": "fast",
            "generate": {"prompt": "Hello {name}!"},
        })
        result = render_prompt(spec, {})
        assert result == "Hello !"

    def test_no_placeholders(self):
        spec = TemplateSpec.model_validate({
            "kind": "image",
            "mode": "fast",
            "generate": {"prompt": "Just a plain prompt."},
        })
        result = render_prompt(spec, {"anything": "should not appear"})
        assert result == "Just a plain prompt."


class TestRunPyfunc:
    """Tests for run_pyfunc — inline Python transforms."""

    def test_no_pyfunc_passthrough(self):
        spec = TemplateSpec.model_validate({
            "kind": "image",
            "mode": "fast",
            "encode": {},
            "generate": {"prompt": "test"},
        })
        parts: list[dict[str, Any]] = [{"type": "text", "text": "hello"}]
        result = run_pyfunc(spec, parts, {})
        assert result == parts

    def test_pyfunc_filters_parts(self):
        spec = TemplateSpec.model_validate({
            "kind": "image",
            "mode": "fast",
            "encode": {
                "pyfunc": "return [p for p in parts if p.get('type') == 'text']"
            },
            "generate": {"prompt": "test"},
        })
        parts: list[dict[str, Any]] = [
            {"type": "text", "text": "keep"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ]
        result = run_pyfunc(spec, parts, {})
        assert len(result) == 1
        assert result[0]["type"] == "text"

    def test_pyfunc_accesses_context(self):
        spec = TemplateSpec.model_validate({
            "kind": "image",
            "mode": "fast",
            "encode": {
                "pyfunc": "return parts + [{'type': 'text', 'text': context.get('extra', '')}]"
            },
            "generate": {"prompt": "test"},
        })
        parts: list[dict[str, Any]] = []
        result = run_pyfunc(spec, parts, {"extra": "injected"})
        assert len(result) == 1
        assert result[0]["text"] == "injected"

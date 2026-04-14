"""Tests for mm.pipelines — YAML loading, schema validation, prompt rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mm.pipelines import apply_overrides, load, render_prompt, run_pyfunc
from mm.pipelines.schema import Encode, Generate, PipelineSpec, PipelineValidationError

ValidationError = PipelineValidationError

TemplateSpec = PipelineSpec


class TestPipelineSpecSchema:
    """Schema validation for pipeline YAML files."""

    def test_valid_minimal_with_generate(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "generate": {"prompt": "Describe this image."},
            }
        )
        assert spec.kind == "image"
        assert spec.mode == "fast"
        assert spec.generate is not None
        assert spec.generate.prompt == "Describe this image."
        assert spec.generate.max_tokens == 256
        assert spec.generate.temperature is None
        assert spec.generate.json_mode is False
        assert spec.encode.strategy is None

    def test_valid_encode_only(self):
        """generate is optional — None means encode-only pipeline."""
        spec = TemplateSpec.from_dict(
            {
                "kind": "document",
                "mode": "fast",
            }
        )
        assert spec.kind == "document"
        assert spec.mode == "fast"
        assert spec.generate is None
        assert spec.encode.strategy is None

    def test_explicit_generate_null(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "text",
                "mode": "fast",
                "encode": {"strategy": None},
                "generate": None,
            }
        )
        assert spec.generate is None

    def test_valid_full(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "video",
                "mode": "accurate",
                "encode": {
                    "strategy": "frame-sample",
                    "strategy_opts": {
                        "max_width": 512,
                        "transcribe": True,
                        "whisper_model": "medium",
                    },
                },
                "generate": {
                    "prompt": "Describe the video {filename}.",
                    "max_tokens": 1024,
                    "temperature": 0.7,
                    "json_mode": True,
                },
            }
        )
        assert spec.encode.strategy == "frame-sample"
        assert spec.encode.strategy_opts["max_width"] == 512
        assert spec.encode.strategy_opts["transcribe"] is True
        assert spec.encode.strategy_opts["whisper_model"] == "medium"
        assert spec.generate is not None
        assert spec.generate.max_tokens == 1024
        assert spec.generate.temperature == 0.7
        assert spec.generate.json_mode is True

    def test_missing_generate_prompt_raises(self):
        with pytest.raises(ValidationError):
            TemplateSpec.from_dict(
                {
                    "kind": "image",
                    "mode": "fast",
                    "generate": {"max_tokens": 256},
                }
            )

    def test_missing_generate_is_ok(self):
        """generate is optional — omitting it defaults to None."""
        spec = TemplateSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
            }
        )
        assert spec.generate is None

    def test_missing_kind_raises(self):
        with pytest.raises(ValidationError):
            TemplateSpec.from_dict(
                {
                    "mode": "fast",
                    "generate": {"prompt": "test"},
                }
            )

    def test_encode_defaults(self):
        enc = Encode()
        assert enc.strategy is None
        assert enc.pyfunc is None
        assert enc.strategy_opts == {}

    def test_generate_defaults(self):
        gen = Generate(prompt="Hello")
        assert gen.max_tokens == 256
        assert gen.temperature is None
        assert gen.json_mode is False

    def test_extra_fields_ignored(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "generate": {"prompt": "test"},
                "extra_unknown": "should not break",
            }
        )
        assert spec.kind == "image"


class TestLoad:
    """Tests for pipelines.load() — YAML loading and caching."""

    def test_load_image_fast(self):
        spec = load("image", "fast")
        assert spec.kind == "image"
        assert spec.mode == "fast"
        # image/fast.yaml ships with a generate stage to LLM-ify fast mode
        assert spec.generate is not None

    def test_load_image_accurate(self):
        spec = load("image", "accurate")
        assert spec.kind == "image"
        assert spec.mode == "accurate"
        assert spec.generate is not None
        assert len(spec.generate.prompt) > 0

    def test_load_video_fast(self):
        spec = load("video", "fast")
        assert spec.kind == "video"
        assert spec.mode == "fast"
        assert spec.generate is not None

    def test_load_video_accurate(self):
        spec = load("video", "accurate")
        assert spec.kind == "video"
        assert spec.mode == "accurate"
        assert spec.generate is not None

    def test_load_document_fast(self):
        spec = load("document", "fast")
        assert spec.kind == "document"
        assert spec.generate is None

    def test_load_document_accurate(self):
        spec = load("document", "accurate")
        assert spec.kind == "document"
        assert spec.generate is not None

    def test_load_audio_fast(self):
        spec = load("audio", "fast")
        assert spec.kind == "audio"
        assert spec.generate is None

    def test_load_audio_accurate(self):
        spec = load("audio", "accurate")
        assert spec.kind == "audio"
        assert spec.generate is not None

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError, match="No pipeline"):
            load("nonexistent_kind_xyz", "nonexistent_mode_abc")

    def test_all_builtin_yamls_valid(self):
        """Every builtin YAML should parse into a valid PipelineSpec."""
        pipelines_dir = (
            Path(__file__).resolve().parent.parent.parent / "python" / "mm" / "pipelines"
        )
        yaml_files = list(pipelines_dir.rglob("*.yaml"))
        yaml_files = [f for f in yaml_files if f.name != "spec.yaml"]
        assert len(yaml_files) >= 8, f"Expected at least 8 YAML files, got {len(yaml_files)}"

        for yaml_file in yaml_files:
            data = yaml.safe_load(yaml_file.read_text())
            spec = PipelineSpec.from_dict(data)
            assert spec.kind in ("image", "video", "audio", "document")
            assert spec.mode in ("fast", "accurate")
            if spec.generate is not None:
                assert len(spec.generate.prompt) > 0


class TestRenderPrompt:
    """Tests for render_prompt — template interpolation."""

    def test_simple_substitution(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "generate": {"prompt": "Describe {filename} in {word_count} words."},
            }
        )
        result = render_prompt(spec, {"filename": "photo.jpg", "word_count": "20"})
        assert result == "Describe photo.jpg in 20 words."

    def test_missing_key_becomes_empty(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "video",
                "mode": "fast",
                "generate": {"prompt": "Video: {filename}. Duration: {duration_ctx}"},
            }
        )
        result = render_prompt(spec, {"filename": "clip.mp4"})
        assert "clip.mp4" in result
        assert "Duration: " in result
        assert "{duration_ctx}" not in result

    def test_empty_context(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "generate": {"prompt": "Hello {name}!"},
            }
        )
        result = render_prompt(spec, {})
        assert result == "Hello !"

    def test_no_placeholders(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "generate": {"prompt": "Just a plain prompt."},
            }
        )
        result = render_prompt(spec, {"anything": "should not appear"})
        assert result == "Just a plain prompt."

    def test_encode_only_returns_empty(self):
        """When generate is None, render_prompt returns empty string."""
        spec = TemplateSpec.from_dict(
            {
                "kind": "text",
                "mode": "fast",
            }
        )
        result = render_prompt(spec, {"filename": "test.txt"})
        assert result == ""


class TestRunPyfunc:
    """Tests for run_pyfunc — inline Python transforms."""

    @pytest.fixture(autouse=True)
    def _allow_pyfunc(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MM_ALLOW_PYFUNC", "1")

    def test_no_pyfunc_passthrough(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "encode": {},
            }
        )
        parts: list[dict[str, Any]] = [{"type": "text", "text": "hello"}]
        result = run_pyfunc(spec, parts, {})
        assert result == parts

    def test_pyfunc_filters_parts(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "encode": {"pyfunc": "return [p for p in parts if p.get('type') == 'text']"},
            }
        )
        parts: list[dict[str, Any]] = [
            {"type": "text", "text": "keep"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ]
        result = run_pyfunc(spec, parts, {})
        assert len(result) == 1
        assert result[0]["type"] == "text"

    def test_pyfunc_accesses_context(self):
        spec = TemplateSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "encode": {
                    "pyfunc": "return parts + [{'type': 'text', 'text': context.get('extra', '')}]"
                },
            }
        )
        parts: list[dict[str, Any]] = []
        result = run_pyfunc(spec, parts, {"extra": "injected"})
        assert len(result) == 1
        assert result[0]["text"] == "injected"


class TestApplyOverrides:
    """Tests for apply_overrides — CLI override merging."""

    def _base_spec(self) -> PipelineSpec:
        return PipelineSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "encode": {
                    "strategy": "resize",
                    "strategy_opts": {"max_width": 1024},
                },
                "generate": {"prompt": "Describe this image.", "max_tokens": 256},
            }
        )

    def _encode_only_spec(self) -> PipelineSpec:
        return PipelineSpec.from_dict(
            {
                "kind": "document",
                "mode": "fast",
            }
        )

    def test_no_overrides_returns_same(self):
        spec = self._base_spec()
        result = apply_overrides(spec)
        assert result.encode.strategy == "resize"
        assert result.generate is not None
        assert result.generate.max_tokens == 256

    def test_encode_strategy_override(self):
        spec = self._base_spec()
        result = apply_overrides(spec, encode_overrides={"strategy": "tile"})
        assert result.encode.strategy == "tile"
        assert result.encode.strategy_opts["max_width"] == 1024

    def test_encode_max_width_override(self):
        spec = self._base_spec()
        result = apply_overrides(spec, encode_overrides={"max_width": "2048"})
        assert result.encode.strategy_opts["max_width"] == "2048"

    def test_generate_max_tokens_override(self):
        spec = self._base_spec()
        result = apply_overrides(spec, generate_overrides={"max_tokens": "1024"})
        assert result.generate is not None
        assert result.generate.max_tokens == 1024

    def test_generate_temperature_override(self):
        spec = self._base_spec()
        result = apply_overrides(spec, generate_overrides={"temperature": "0.5"})
        assert result.generate is not None
        assert result.generate.temperature == 0.5
        assert isinstance(result.generate.temperature, float)

    def test_generate_json_mode_override(self):
        spec = self._base_spec()
        result = apply_overrides(spec, generate_overrides={"json_mode": "true"})
        assert result.generate is not None
        assert result.generate.json_mode is True

    def test_bool_false_override(self):
        spec = self._base_spec()
        result = apply_overrides(spec, encode_overrides={"transcribe": "false"})
        assert result.encode.strategy_opts["transcribe"] == "false"

    def test_both_overrides_at_once(self):
        spec = self._base_spec()
        result = apply_overrides(
            spec,
            encode_overrides={"strategy": "tile"},
            generate_overrides={"max_tokens": "512", "temperature": "0.8"},
        )
        assert result.encode.strategy == "tile"
        assert result.generate is not None
        assert result.generate.max_tokens == 512
        assert result.generate.temperature == 0.8

    def test_unknown_encode_field_becomes_strategy_opt(self):
        spec = self._base_spec()
        result = apply_overrides(spec, encode_overrides={"custom_param": "val"})
        assert result.encode.strategy_opts["custom_param"] == "val"

    def test_unknown_generate_field_ignored(self):
        spec = self._base_spec()
        result = apply_overrides(spec, generate_overrides={"nonexistent_field": "val"})
        assert result.generate is not None
        assert not hasattr(result.generate, "nonexistent_field")

    def test_original_spec_unchanged(self):
        spec = self._base_spec()
        apply_overrides(spec, generate_overrides={"max_tokens": "9999"})
        assert spec.generate is not None
        assert spec.generate.max_tokens == 256

    def test_mosaic_image_width_override(self):
        spec = self._base_spec()
        result = apply_overrides(spec, encode_overrides={"mosaic_image_width": "320"})
        assert result.encode.strategy_opts.get("mosaic_image_width") == "320"

    def test_frame_selection_override(self):
        spec = self._base_spec()
        result = apply_overrides(spec, encode_overrides={"frame_selection": "scene"})
        assert result.encode.strategy_opts.get("frame_selection") == "scene"

    def test_pyfunc_override(self):
        spec = self._base_spec()
        result = apply_overrides(spec, encode_overrides={"pyfunc": "my_filter.py"})
        assert result.encode.pyfunc == "my_filter.py"

    def test_generate_override_on_encode_only(self):
        """Overriding generate on an encode-only spec creates the generate section."""
        spec = self._encode_only_spec()
        result = apply_overrides(spec, generate_overrides={"max_tokens": "512"})
        assert result.generate is not None
        assert result.generate.max_tokens == 512


class TestEncodeStrategyOpts:
    """Validate strategy_opts carries encoder parameters."""

    def test_defaults_empty(self):
        enc = Encode()
        assert enc.strategy_opts == {}

    def test_set_via_constructor(self):
        enc = Encode(strategy_opts={"mosaic_image_width": 320, "frame_selection": "scene"})
        assert enc.strategy_opts["mosaic_image_width"] == 320
        assert enc.strategy_opts["frame_selection"] == "scene"

    def test_roundtrip_yaml(self, tmp_path: Path):
        data = {
            "kind": "video",
            "mode": "fast",
            "encode": {
                "strategy": "mosaic",
                "strategy_opts": {
                    "tile_cols": 6,
                    "tile_rows": 4,
                    "thumb_width": 200,
                },
            },
        }
        p = tmp_path / "pipeline.yaml"
        p.write_text(yaml.dump(data))
        spec = PipelineSpec.from_dict(yaml.safe_load(p.read_text()))
        assert spec.encode.strategy_opts["tile_cols"] == 6
        assert spec.encode.strategy_opts["tile_rows"] == 4
        assert spec.encode.strategy_opts["thumb_width"] == 200


class TestLoadFile:
    """Tests for load_file() — explicit YAML loading."""

    def test_single_doc(self, tmp_path: Path):
        from mm.pipelines import load_file

        data = {
            "kind": "image",
            "mode": "fast",
            "generate": {"prompt": "Describe."},
        }
        p = tmp_path / "img.yaml"
        p.write_text(yaml.dump(data))
        specs = load_file(p)
        assert len(specs) == 1
        assert specs[0].kind == "image"

    def test_single_doc_encode_only(self, tmp_path: Path):
        from mm.pipelines import load_file

        data = {
            "kind": "document",
            "mode": "fast",
        }
        p = tmp_path / "doc.yaml"
        p.write_text(yaml.dump(data))
        specs = load_file(p)
        assert len(specs) == 1
        assert specs[0].generate is None

    def test_multi_doc(self, tmp_path: Path):
        from mm.pipelines import load_file

        doc1 = {"kind": "image", "mode": "fast", "generate": {"prompt": "img"}}
        doc2 = {"kind": "video", "mode": "fast"}
        p = tmp_path / "multi.yaml"
        p.write_text(yaml.dump(doc1) + "---\n" + yaml.dump(doc2))
        specs = load_file(p)
        assert len(specs) == 2
        kinds = {s.kind for s in specs}
        assert kinds == {"image", "video"}

    def test_nonexistent_raises(self):
        from mm.pipelines import load_file

        with pytest.raises(FileNotFoundError, match="Pipeline file not found"):
            load_file("/nonexistent/path.yaml")

    def test_empty_doc_raises(self, tmp_path: Path):
        from mm.pipelines import load_file

        p = tmp_path / "empty.yaml"
        p.write_text("")
        with pytest.raises(ValueError, match="No valid pipeline"):
            load_file(p)


class TestPyfuncFileRef:
    """Tests for file-path pyfunc references in run_pyfunc."""

    @pytest.fixture(autouse=True)
    def _allow_pyfunc(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MM_ALLOW_PYFUNC", "1")

    def test_file_pyfunc(self, tmp_path: Path):
        py_file = tmp_path / "my_transform.py"
        py_file.write_text(
            "def transform(parts, context):\n    return [{'type': 'text', 'text': 'filtered'}]\n"
        )
        spec = PipelineSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "encode": {"pyfunc": str(py_file)},
            }
        )
        result = run_pyfunc(spec, [{"type": "text", "text": "original"}], {})
        assert len(result) == 1
        assert result[0]["text"] == "filtered"

    def test_inline_full_def(self):
        code = "def transform(parts, context):\n    return [{'type': 'text', 'text': 'inline'}]"
        spec = PipelineSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "encode": {"pyfunc": code},
            }
        )
        result = run_pyfunc(spec, [{"type": "text", "text": "original"}], {})
        assert result[0]["text"] == "inline"

    def test_legacy_body_only(self):
        body = "return [{'type': 'text', 'text': 'legacy'}]"
        spec = PipelineSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "encode": {"pyfunc": body},
            }
        )
        result = run_pyfunc(spec, [], {})
        assert result[0]["text"] == "legacy"

    def test_nonexistent_file_raises(self):
        spec = PipelineSpec.from_dict(
            {
                "kind": "image",
                "mode": "fast",
                "encode": {"pyfunc": "/nonexistent/file.py"},
            }
        )
        with pytest.raises(FileNotFoundError, match="pyfunc file not found"):
            run_pyfunc(spec, [], {})


class TestTomlPipelinePaths:
    """Test that TOML pipeline path overrides work."""

    def test_get_pipeline_path_returns_none_when_not_set(self):
        from unittest.mock import patch

        with patch("mm.config._read_config_file", return_value={}):
            from mm.config import get_pipeline_path

            assert get_pipeline_path("image", "fast") is None

    def test_get_pipeline_path_returns_path_when_set(self, tmp_path: Path):
        from unittest.mock import patch

        yaml_file = tmp_path / "my_image_fast.yaml"
        yaml_file.write_text("kind: image\nmode: fast\n")

        config_data = {"pipelines": {"image": {"fast": str(yaml_file)}}}
        with patch("mm.config._read_config_file", return_value=config_data):
            from mm.config import get_pipeline_path

            result = get_pipeline_path("image", "fast")
            assert result is not None
            assert "my_image_fast.yaml" in result

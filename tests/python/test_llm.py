"""Tests for mm.llm — LlmBackend, _extract_answer_from_thinking, image_part."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from mm.llm import LlmUsage, _extract_answer_from_thinking, image_part


class TestLlmUsage:
    def test_defaults(self):
        u = LlmUsage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0

    def test_custom_values(self):
        u = LlmUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        assert u.prompt_tokens == 10
        assert u.total_tokens == 30


class TestExtractAnswerFromThinking:
    def test_quoted_answer(self):
        thinking = (
            'The user asked for a description. "A beautiful sunset over the ocean" seems right.'
        )
        result = _extract_answer_from_thinking(thinking)
        assert result == "A beautiful sunset over the ocean"

    def test_multiple_quotes_picks_last(self):
        thinking = '"First answer" but maybe "Better answer here" is more accurate.'
        result = _extract_answer_from_thinking(thinking)
        assert result == "Better answer here"

    def test_short_quotes_ignored(self):
        """Quotes shorter than 10 chars are ignored."""
        thinking = '"short" so we fall back to paragraphs.\n\nThe final answer is here.'
        result = _extract_answer_from_thinking(thinking)
        assert "final answer" in result

    def test_paragraph_extraction(self):
        thinking = "Some reasoning.\n\nMore reasoning.\n\nThe answer: a cat sitting on a mat."
        result = _extract_answer_from_thinking(thinking)
        assert "cat sitting on a mat" in result

    def test_strips_answer_prefix(self):
        thinking = "Let me think.\n\nAnswer: The image shows a dog."
        result = _extract_answer_from_thinking(thinking)
        assert result.startswith("The image shows a dog")

    def test_strips_summary_prefix(self):
        thinking = "Lots of thought.\n\nSummary: A red car."
        result = _extract_answer_from_thinking(thinking)
        assert "A red car" in result

    def test_bare_text_fallback(self):
        thinking = "Just one line of text."
        result = _extract_answer_from_thinking(thinking)
        assert result == "Just one line of text."


class TestImagePart:
    def test_builds_openai_format(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
        part = image_part(img)
        assert part["type"] == "image_url"
        assert part["image_url"]["url"].startswith("data:image/jpeg;base64,")

    def test_custom_mime(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 50)
        part = image_part(img, mime="image/png")
        assert "image/png" in part["image_url"]["url"]


class TestLlmBackendChat:
    """Test _chat, generate, generate_chunked via mocking."""

    def _make_backend(self):
        with patch("mm.profile.get_profile") as mock_profile:
            mock_profile.return_value = MagicMock(
                base_url="http://localhost:11434/v1",
                api_key="test-key",
                model="test-model",
            )
            with patch("mm.llm.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_openai_cls.return_value = mock_client
                from mm.llm import LlmBackend

                backend = LlmBackend()
                return backend, mock_client

    def _mock_response(self, content: str, usage=None, reasoning=None):
        choice = MagicMock()
        choice.content = content
        choice.reasoning = reasoning
        choice.reasoning_content = None
        response = MagicMock()
        response.choices = [MagicMock(message=choice)]
        response.usage = usage
        return response

    def test_chat_returns_content(self):
        backend, client = self._make_backend()
        resp = self._mock_response("Hello world")
        client.chat.completions.create.return_value = resp
        result = backend._chat([{"role": "user", "content": "Hi"}])
        assert result == "Hello world"

    def test_chat_tracks_usage(self):
        backend, client = self._make_backend()
        usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        resp = self._mock_response("test", usage=usage)
        client.chat.completions.create.return_value = resp
        backend._chat([{"role": "user", "content": "Hi"}])
        assert backend.last_usage.prompt_tokens == 10
        assert backend.last_usage.total_tokens == 15

    def test_chat_empty_content_falls_back_to_reasoning(self):
        backend, client = self._make_backend()
        resp = self._mock_response("", reasoning='I think the answer is "A dog on a hill"')
        client.chat.completions.create.return_value = resp
        result = backend._chat([{"role": "user", "content": "test"}])
        assert "dog on a hill" in result

    def test_chat_error_returns_error_string(self):
        backend, client = self._make_backend()
        client.chat.completions.create.side_effect = RuntimeError("Connection refused")
        result = backend._chat([{"role": "user", "content": "test"}])
        assert result.startswith("[LLM error:")
        assert "Connection refused" in result

    def test_chat_json_mode(self):
        backend, client = self._make_backend()
        resp = self._mock_response('{"key": "value"}')
        client.chat.completions.create.return_value = resp
        backend._chat(
            [{"role": "user", "content": "test"}],
            json_mode=True,
        )
        call_kwargs = client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("response_format") == {"type": "json_object"} or call_kwargs[
            1
        ].get("response_format") == {"type": "json_object"}

    def test_generate_loads_template_and_calls_chat(self):
        backend, client = self._make_backend()
        resp = self._mock_response("A sunset photo")
        client.chat.completions.create.return_value = resp

        result = backend.generate(
            "image",
            "accurate",
            context={"filename": "test.jpg"},
            parts=[{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}}],
        )
        assert result == "A sunset photo"
        client.chat.completions.create.assert_called_once()

    def test_generate_encode_only_returns_empty(self):
        """When pipeline has generate=None, generate() returns '' without calling LLM."""
        backend, client = self._make_backend()

        # document/fast.yaml ships with no `generate` stage (encode-only pipeline).
        result = backend.generate(
            "document",
            "fast",
            context={"filename": "test.pdf"},
            parts=[{"type": "text", "text": "page content"}],
        )
        assert result == ""
        client.chat.completions.create.assert_not_called()

    def test_generate_chunked_concatenates(self):
        backend, client = self._make_backend()
        call_count = [0]

        def side_effect(**kwargs):
            call_count[0] += 1
            return self._mock_response(f"chunk{call_count[0]}")

        client.chat.completions.create.side_effect = side_effect

        chunks = [
            [{"type": "text", "text": "part1"}],
            [{"type": "text", "text": "part2"}],
            [{"type": "text", "text": "part3"}],
        ]
        result = backend.generate_chunked("image", "accurate", chunks=chunks)
        assert "chunk1" in result
        assert "chunk2" in result
        assert "chunk3" in result
        assert client.chat.completions.create.call_count == 3

    def test_generate_chunked_filters_errors(self):
        backend, client = self._make_backend()
        responses = iter(
            [
                self._mock_response("good result"),
                self._mock_response("[LLM error: timeout]"),
                self._mock_response("another good result"),
            ]
        )
        client.chat.completions.create.side_effect = lambda **kw: next(responses)

        chunks = [
            [{"type": "text", "text": "a"}],
            [{"type": "text", "text": "b"}],
            [{"type": "text", "text": "c"}],
        ]
        result = backend.generate_chunked("image", "accurate", chunks=chunks)
        assert "good result" in result
        assert "another good result" in result
        assert "[LLM error" not in result

    def test_generate_chunked_on_chunk_callback(self):
        backend, client = self._make_backend()
        client.chat.completions.create.return_value = self._mock_response("ok")

        callback_calls: list[tuple[int, int, str]] = []

        def on_chunk(idx, total, result):
            callback_calls.append((idx, total, result))

        chunks = [[{"type": "text", "text": "a"}], [{"type": "text", "text": "b"}]]
        backend.generate_chunked("image", "accurate", chunks=chunks, on_chunk=on_chunk)
        assert len(callback_calls) == 2
        assert callback_calls[0] == (0, 2, "ok")
        assert callback_calls[1] == (1, 2, "ok")

    def test_generate_chunked_accumulates_usage(self):
        backend, client = self._make_backend()
        usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        client.chat.completions.create.return_value = self._mock_response("ok", usage=usage)

        chunks = [[{"type": "text", "text": "a"}], [{"type": "text", "text": "b"}]]
        backend.generate_chunked("image", "accurate", chunks=chunks)
        assert backend.last_usage.prompt_tokens == 200
        assert backend.last_usage.total_tokens == 300

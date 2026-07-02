"""Tests for mm.errors — ChatCompletionError hierarchy and from_openai_error."""

from __future__ import annotations

from unittest.mock import MagicMock


from mm.errors import (
    AuthenticationError,
    BadRequestError,
    ChatCompletionError,
    GatewayError,
    ImageURLError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    from_openai_error,
)


class TestChatCompletionError:
    def test_carries_status_and_message(self):
        err = ChatCompletionError(502, "Bad gateway")
        assert err.status_code == 502
        assert err.message == "Bad gateway"
        assert err.body is None
        assert "[502]" in str(err)

    def test_carries_body(self):
        body = {"error": {"message": "model not found"}}
        err = ChatCompletionError(404, "Not found", body=body)
        assert err.body == body


class TestSubclasses:
    def test_bad_request(self):
        err = BadRequestError("invalid image URL")
        assert err.status_code == 400

    def test_authentication(self):
        err = AuthenticationError("invalid API key")
        assert err.status_code == 401

    def test_permission_denied(self):
        err = PermissionDeniedError("insufficient permissions")
        assert err.status_code == 403

    def test_not_found(self):
        err = NotFoundError("model does not exist")
        assert err.status_code == 404

    def test_rate_limit(self):
        err = RateLimitError("too many requests")
        assert err.status_code == 429

    def test_gateway_error_default(self):
        err = GatewayError("internal server error")
        assert err.status_code == 500

    def test_gateway_error_custom_status(self):
        err = GatewayError("bad gateway", status_code=502)
        assert err.status_code == 502

    def test_isinstance_hierarchy(self):
        err = BadRequestError("bad input")
        assert isinstance(err, ChatCompletionError)
        assert isinstance(err, BadRequestError)

    def test_image_url_error(self):
        err = ImageURLError("https://example.com/bad.txt", "not an image")
        assert err.status_code == 400
        assert isinstance(err, BadRequestError)
        assert isinstance(err, ChatCompletionError)
        assert err.url == "https://example.com/bad.txt"
        assert err.reason == "not an image"
        assert "bad.txt" in str(err)


class TestFromOpenaiError:
    def _make_api_error(self, status_code: int, body: dict | None = None):
        exc = MagicMock()
        exc.status_code = status_code
        exc.body = body
        exc.__str__ = lambda self: f"Error code: {status_code}"
        return exc

    def test_400_maps_to_bad_request(self):
        exc = self._make_api_error(400, {"error": {"message": "invalid image"}})
        result = from_openai_error(exc)
        assert isinstance(result, BadRequestError)
        assert result.status_code == 400
        assert result.message == "invalid image"

    def test_401_maps_to_authentication(self):
        exc = self._make_api_error(401, {"error": {"message": "invalid key"}})
        result = from_openai_error(exc)
        assert isinstance(result, AuthenticationError)
        assert result.status_code == 401

    def test_403_maps_to_permission_denied(self):
        exc = self._make_api_error(403)
        result = from_openai_error(exc)
        assert isinstance(result, PermissionDeniedError)

    def test_404_maps_to_not_found(self):
        exc = self._make_api_error(404, {"error": {"message": "model not found"}})
        result = from_openai_error(exc)
        assert isinstance(result, NotFoundError)
        assert result.message == "model not found"

    def test_429_maps_to_rate_limit(self):
        exc = self._make_api_error(429)
        result = from_openai_error(exc)
        assert isinstance(result, RateLimitError)

    def test_500_maps_to_gateway_error(self):
        exc = self._make_api_error(500)
        result = from_openai_error(exc)
        assert isinstance(result, GatewayError)
        assert result.status_code == 500

    def test_502_maps_to_gateway_error(self):
        exc = self._make_api_error(502)
        result = from_openai_error(exc)
        assert isinstance(result, GatewayError)
        assert result.status_code == 502

    def test_unknown_status_maps_to_base(self):
        exc = self._make_api_error(418)
        result = from_openai_error(exc)
        assert type(result) is ChatCompletionError
        assert result.status_code == 418

    def test_body_message_extraction(self):
        exc = self._make_api_error(400, {"error": {"message": "specific error"}})
        result = from_openai_error(exc)
        assert result.message == "specific error"

    def test_flat_body_message(self):
        exc = self._make_api_error(400, {"message": "flat error"})
        result = from_openai_error(exc)
        assert result.message == "flat error"

    def test_no_body_uses_str(self):
        exc = self._make_api_error(400)
        result = from_openai_error(exc)
        assert "400" in result.message

    def test_no_status_code(self):
        exc = RuntimeError("connection failed")
        result = from_openai_error(exc)
        assert result.status_code == 0
        assert "connection failed" in result.message


class TestImageURLErrorDetails:
    def test_url_and_reason_in_message(self):
        err = ImageURLError("https://example.com/page.html", "expected image, got text/html")
        assert "page.html" in err.message
        assert "text/html" in err.message
        assert err.url == "https://example.com/page.html"
        assert err.reason == "expected image, got text/html"

    def test_is_subclass_chain(self):
        err = ImageURLError("http://x.com/a.txt", "not an image")
        assert isinstance(err, BadRequestError)
        assert isinstance(err, ChatCompletionError)
        assert isinstance(err, Exception)

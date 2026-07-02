"""Structured errors for chat completions and media processing.

Provides a typed exception hierarchy so callers can distinguish gateway
HTTP status codes (400, 401, 403, 404, 429, 500+) from transient
connection failures and from local input-validation problems.

Usage::

    from mm.errors import ChatCompletionError, ImageURLError

    try:
        result = backend.generate(...)
    except ChatCompletionError as exc:
        print(exc.status_code, exc.message)
"""

from __future__ import annotations

from typing import Any


class ChatCompletionError(Exception):
    """Error from a chat completions call with HTTP status context.

    Attributes:
        status_code: HTTP status code from the gateway (e.g. 400, 404, 500).
        message: Human-readable error description.
        body: Optional raw error body from the gateway response.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        body: Any = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.body = body
        super().__init__(f"[{status_code}] {message}")


class BadRequestError(ChatCompletionError):
    """400 — the request was malformed or contained invalid input."""

    def __init__(self, message: str, *, body: Any = None) -> None:
        super().__init__(400, message, body=body)


class AuthenticationError(ChatCompletionError):
    """401 — missing or invalid API key."""

    def __init__(self, message: str, *, body: Any = None) -> None:
        super().__init__(401, message, body=body)


class PermissionDeniedError(ChatCompletionError):
    """403 — valid credentials but insufficient permissions."""

    def __init__(self, message: str, *, body: Any = None) -> None:
        super().__init__(403, message, body=body)


class NotFoundError(ChatCompletionError):
    """404 — the requested model or resource does not exist."""

    def __init__(self, message: str, *, body: Any = None) -> None:
        super().__init__(404, message, body=body)


class RateLimitError(ChatCompletionError):
    """429 — rate limit exceeded; retry after backoff."""

    def __init__(self, message: str, *, body: Any = None) -> None:
        super().__init__(429, message, body=body)


class GatewayError(ChatCompletionError):
    """5xx — server-side error from the gateway."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        body: Any = None,
    ) -> None:
        super().__init__(status_code, message, body=body)


class ImageURLError(BadRequestError):
    """The supplied image URL could not be fetched or is not a valid image.

    Raised *before* the chat completions call when mm detects that a
    user-provided URL will fail at the gateway (non-image content type,
    DNS failure, 404, etc.).
    """

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Invalid image URL {url!r}: {reason}")


def from_openai_error(exc: Exception) -> ChatCompletionError:
    """Convert an ``openai.APIStatusError`` into the corresponding mm error.

    Falls back to :class:`GatewayError` for unrecognised status codes and
    to :class:`ChatCompletionError` for errors without a status code.
    """
    status: int = getattr(exc, "status_code", 0) or 0
    body: Any = getattr(exc, "body", None)
    msg = _extract_message(exc, body)

    if status == 400:
        return BadRequestError(msg, body=body)
    if status == 401:
        return AuthenticationError(msg, body=body)
    if status == 403:
        return PermissionDeniedError(msg, body=body)
    if status == 404:
        return NotFoundError(msg, body=body)
    if status == 429:
        return RateLimitError(msg, body=body)
    if status >= 500:
        return GatewayError(msg, status_code=status, body=body)
    if status > 0:
        return ChatCompletionError(status, msg, body=body)
    return ChatCompletionError(0, msg, body=body)


def _extract_message(exc: Exception, body: Any) -> str:
    """Best-effort extraction of a human-readable message from the gateway error body."""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if msg:
                return str(msg)
        msg = body.get("message")
        if msg:
            return str(msg)
    return str(exc)

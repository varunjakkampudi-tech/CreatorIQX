"""Web-protection middleware: security headers and a request body-size limit.

Spec §10 (Web protection): secure headers, CSP, HSTS only over HTTPS, and an
input-size guard. Strict CORS is configured separately in the app factory with
Starlette's CORSMiddleware, allowing only the configured browser origin.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TOO_LARGE_BODY = json.dumps(
    {
        "type": "/problems/request-too-large",
        "title": "Request body too large",
        "status": 413,
    }
).encode()

# Applied to every response. The API returns JSON only, so the CSP is maximally
# strict; the web app sets its own page CSP with nonces (P0-082).
_BASE_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"cross-origin-opener-policy", b"same-origin"),
)
_HSTS = (b"strict-transport-security", b"max-age=63072000; includeSubDomains")


class SecurityHeadersMiddleware:
    """Adds hardening headers; HSTS only when the request arrived over HTTPS."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        is_https = scope.get("scheme") == "https"

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend(_BASE_HEADERS)
                if is_https:
                    headers.append(_HSTS)
            await send(message)

        await self._app(scope, receive, send_wrapper)


class BodySizeLimitMiddleware:
    """Rejects a request body larger than ``max_bytes`` with 413.

    Checks the Content-Length header up front, and also counts streamed bytes so
    a chunked request without Content-Length cannot exceed the limit.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max:
            await self._reject(send)
            return

        seen = 0

        async def receive_capped() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self._max:
                    raise _BodyTooLargeError
            return message

        try:
            await self._app(scope, receive_capped, send)
        except _BodyTooLargeError:
            await self._reject(send)

    async def _reject(self, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/problem+json")],
            }
        )
        await send({"type": "http.response.body", "body": _TOO_LARGE_BODY})


class _BodyTooLargeError(Exception):
    """Internal signal that the streamed body exceeded the limit."""

"""Correlation-id and request-logging ASGI middleware (spec §10, §17 Observability).

One correlation id per request is bound to the structlog context, returned in
the ``X-Request-ID`` response header, and included in the start/end log lines.
Request headers and bodies are never logged, so credentials never reach a log.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from creatoriqx_api.platform.logging import get_logger

REQUEST_ID_HEADER = b"x-request-id"
_MAX_ID_LENGTH = 128
_logger = get_logger("creatoriqx.request")


def _clean_incoming_id(raw: bytes) -> str | None:
    """Accept a client-supplied id only if it is short and printable ASCII."""
    try:
        value = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    if value and len(value) <= _MAX_ID_LENGTH and value.isprintable():
        return value
    return None


class CorrelationMiddleware:
    """Assigns a correlation id, binds it to logs, echoes it in the response."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        incoming = headers.get(REQUEST_ID_HEADER)
        request_id = (incoming and _clean_incoming_id(incoming)) or uuid.uuid4().hex

        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers_list = message.setdefault("headers", [])
                headers_list.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        finally:
            _logger.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_holder["status"],
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            structlog.contextvars.clear_contextvars()

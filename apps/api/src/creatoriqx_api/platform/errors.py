"""Typed domain errors mapped to RFC 9457 problem+json (spec §8, §12).

Domain and application code raise ``DomainError`` subclasses; the handlers here
turn them into ``application/problem+json`` responses. Unhandled exceptions
become a generic 500 problem with no stack trace or internal detail.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from creatoriqx_api.platform.logging import get_logger

PROBLEM_JSON = "application/problem+json"
_logger = get_logger("creatoriqx.error")


class DomainError(Exception):
    """Base class for expected, typed failures.

    ``status`` is the HTTP status; ``title`` is a short, stable, human-readable
    summary; ``code`` is a machine-readable slug used as the problem ``type``.
    ``headers``, when set, are added to the response (for example
    ``Retry-After`` on a rate-limit error).
    """

    status: int = 400
    title: str = "Request could not be processed"
    code: str = "domain-error"

    def __init__(
        self, detail: str | None = None, headers: Mapping[str, str] | None = None
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.headers = headers


def _problem(
    status: int,
    title: str,
    code: str,
    headers: Mapping[str, str] | None = None,
    **extra: object,
) -> JSONResponse:
    body = {"type": f"/problems/{code}", "title": title, "status": status, **extra}
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    """Register the problem+json handlers on the app."""

    @app.exception_handler(DomainError)
    async def _domain(_request: Request, exc: DomainError) -> JSONResponse:
        return _problem(exc.status, exc.title, exc.code, headers=exc.headers, detail=exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's error list is safe to return; it describes the request, not internals.
        return _problem(422, "Request validation failed", "validation-error", errors=exc.errors())

    @app.exception_handler(HTTPException)
    async def _http(_request: Request, exc: HTTPException) -> JSONResponse:
        return _problem(exc.status_code, str(exc.detail), f"http-{exc.status_code}")

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # Log the real error server-side; never expose it to the client.
        _logger.error("unhandled_exception", error_type=type(exc).__name__)
        return _problem(500, "Internal server error", "internal-error")

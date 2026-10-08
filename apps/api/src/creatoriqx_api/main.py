"""Composition root: builds the FastAPI application.

Run locally with:
    uv run uvicorn creatoriqx_api.main:create_app --factory --env-file .env
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from creatoriqx_api import __version__
from creatoriqx_api.platform.health import HealthCheck, PostgresCheck, RedisCheck, run_checks
from creatoriqx_api.settings import Settings, get_settings

API_V1_PREFIX = "/api/v1"
_NO_STORE = {"Cache-Control": "no-store"}


def default_checks(settings: Settings) -> list[HealthCheck]:
    """The production dependency checks, built from settings."""
    timeout = settings.readiness_timeout_seconds
    return [
        PostgresCheck(settings.database_app_url.get_secret_value(), timeout),
        RedisCheck(settings.redis_url.get_secret_value(), timeout),
    ]


def create_app(
    settings: Settings | None = None, checks: Sequence[HealthCheck] | None = None
) -> FastAPI:
    """Build the app. Tests inject settings and fake checks; production uses defaults."""
    settings = settings or get_settings()
    readiness_checks = list(checks) if checks is not None else default_checks(settings)

    app = FastAPI(
        title=f"{settings.product_name} API",
        version=__version__,
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
        docs_url=f"{API_V1_PREFIX}/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )

    @app.get("/healthz", tags=["health"], summary="Liveness: the process is up")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "alive"}, headers=_NO_STORE)

    @app.get("/readyz", tags=["health"], summary="Readiness: dependencies answer")
    async def readyz() -> JSONResponse:
        results = await run_checks(readiness_checks, settings.readiness_timeout_seconds)
        ready = all(status == "ok" for status in results.values())
        return JSONResponse(
            {"status": "ready" if ready else "not_ready", "checks": results},
            status_code=200 if ready else 503,
            headers=_NO_STORE,
        )

    # Feature modules attach their routers here as they are built.
    app.include_router(APIRouter(prefix=API_V1_PREFIX))

    # Prometheus metrics. Restricted to the internal network in production (Phase 1E).
    app.mount("/metrics", make_asgi_app())
    return app

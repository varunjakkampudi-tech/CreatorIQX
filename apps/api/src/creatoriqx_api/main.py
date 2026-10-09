"""Composition root: builds the FastAPI application.

Run locally with:
    uv run uvicorn creatoriqx_api.main:create_app --factory --env-file .env
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from creatoriqx_api import __version__
from creatoriqx_api.modules.identity.api.auth import router as auth_router
from creatoriqx_api.modules.identity.api.me import router as me_router
from creatoriqx_api.modules.identity.api.sessions import router as sessions_router
from creatoriqx_api.modules.identity.application.auth_service import AuthService
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.google_oidc import GoogleOIDCProvider
from creatoriqx_api.modules.identity.infrastructure.key_value_store import RedisKeyValueStore
from creatoriqx_api.modules.workspaces.api.routes import router as workspaces_router
from creatoriqx_api.modules.workspaces.application.access_service import WorkspaceAccessService
from creatoriqx_api.modules.workspaces.application.bootstrap_service import (
    WorkspaceBootstrapService,
)
from creatoriqx_api.modules.workspaces.infrastructure.sql_access_store import (
    SqlWorkspaceAccessStore,
)
from creatoriqx_api.modules.workspaces.infrastructure.sql_store import SqlPersonalWorkspaceStore
from creatoriqx_api.platform.database import create_engine, create_session_factory
from creatoriqx_api.platform.errors import install_error_handlers
from creatoriqx_api.platform.health import HealthCheck, PostgresCheck, RedisCheck, run_checks
from creatoriqx_api.platform.logging import configure_logging
from creatoriqx_api.platform.middleware import CorrelationMiddleware
from creatoriqx_api.platform.rate_limit import RedisTokenBucketLimiter
from creatoriqx_api.platform.security import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from creatoriqx_api.settings import Settings, get_settings

API_V1_PREFIX = "/api/v1"
_NO_STORE = {"Cache-Control": "no-store"}
_CORS_HEADERS = [
    "authorization",
    "content-type",
    "x-request-id",
    "idempotency-key",
    "x-csrf-token",
]


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
    configure_logging(settings)
    readiness_checks = list(checks) if checks is not None else default_checks(settings)
    redis = Redis.from_url(settings.redis_url.get_secret_value())
    engine = create_engine(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await redis.aclose()
            await engine.dispose()

    app = FastAPI(
        title=f"{settings.product_name} API",
        version=__version__,
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
        docs_url=f"{API_V1_PREFIX}/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    # Middleware is applied outermost-last. Request order: CORS, security
    # headers, body-size guard, correlation; responses unwind in reverse.
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.app_base_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=_CORS_HEADERS,
    )
    install_error_handlers(app)

    _wire_sessions(app, settings, redis)
    _wire_workspaces(app, engine)

    if settings.oidc_client_id:
        provider = GoogleOIDCProvider(
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret.get_secret_value(),
        )
        app.state.auth_service = AuthService(
            provider=provider,
            allowed_emails=settings.allowed_emails_set,
        )
        app.include_router(auth_router, prefix=API_V1_PREFIX)

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

    app.include_router(sessions_router, prefix=API_V1_PREFIX)
    app.include_router(me_router, prefix=API_V1_PREFIX)
    app.include_router(workspaces_router, prefix=API_V1_PREFIX)

    # Feature modules attach their routers here as they are built.
    app.include_router(APIRouter(prefix=API_V1_PREFIX))

    # Prometheus metrics. Restricted to the internal network in production (Phase 1E).
    app.mount("/metrics", make_asgi_app())
    return app


def _wire_workspaces(app: FastAPI, engine: AsyncEngine) -> None:
    """Bootstrap and access checks both run as the runtime role under forced RLS (ADR 0011)."""
    factory = create_session_factory(engine)
    app.state.session_factory = factory
    app.state.bootstrap_service = WorkspaceBootstrapService(SqlPersonalWorkspaceStore(factory))
    app.state.workspace_access_service = WorkspaceAccessService(SqlWorkspaceAccessStore(factory))


def _wire_sessions(app: FastAPI, settings: Settings, redis: Redis) -> None:
    """Server-side sessions and login flows live in Redis (ADR 0010)."""
    store = RedisKeyValueStore(redis)
    policy = SessionPolicy(
        idle_timeout=timedelta(minutes=settings.session_idle_timeout_minutes),
        absolute_timeout=timedelta(hours=settings.session_absolute_timeout_hours),
    )
    app.state.settings = settings
    app.state.key_value_store = store
    app.state.session_service = SessionService(store, policy)
    app.state.rate_limiter = RedisTokenBucketLimiter(redis)

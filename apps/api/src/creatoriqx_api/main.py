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
from creatoriqx_api.modules.content.api.chapters import router as chapters_router
from creatoriqx_api.modules.content.api.metadata import router as content_metadata_router
from creatoriqx_api.modules.content.api.scripts import router as scripts_router
from creatoriqx_api.modules.content.application.chapter_service import ChapterService
from creatoriqx_api.modules.content.application.metadata_service import MetadataService
from creatoriqx_api.modules.content.application.script_service import ScriptService
from creatoriqx_api.modules.content.infrastructure.sql_chapter_store import SqlChapterStore
from creatoriqx_api.modules.content.infrastructure.sql_metadata_store import SqlMetadataStore
from creatoriqx_api.modules.content.infrastructure.sql_script_store import SqlScriptStore
from creatoriqx_api.modules.identity.api.auth import router as auth_router
from creatoriqx_api.modules.identity.api.me import router as me_router
from creatoriqx_api.modules.identity.api.sessions import router as sessions_router
from creatoriqx_api.modules.identity.application.auth_service import AuthService
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.google_oidc import GoogleOIDCProvider
from creatoriqx_api.modules.identity.infrastructure.key_value_store import RedisKeyValueStore
from creatoriqx_api.modules.intelligence.api.audit import router as intelligence_router
from creatoriqx_api.modules.intelligence.application.audit_service import ChannelAuditService
from creatoriqx_api.modules.intelligence.infrastructure.sql_recommendation_store import (
    SqlRecommendationStore,
)
from creatoriqx_api.modules.intelligence.infrastructure.youtube_video_reader import (
    YouTubeChannelVideoReader,
)
from creatoriqx_api.modules.jobs.infrastructure.celery_task_queue import CeleryTaskQueue
from creatoriqx_api.modules.planning.api.planner import router as planner_router
from creatoriqx_api.modules.planning.api.videos import router as videos_router
from creatoriqx_api.modules.planning.application.planner_service import PlannerService
from creatoriqx_api.modules.planning.application.video_lifecycle_service import (
    VideoLifecycleService,
)
from creatoriqx_api.modules.planning.infrastructure.sql_plan_store import SqlPlanStore
from creatoriqx_api.modules.planning.infrastructure.sql_video_store import SqlVideoStore
from creatoriqx_api.modules.publishing.api.approval import router as approval_router
from creatoriqx_api.modules.publishing.api.qa import router as qa_router
from creatoriqx_api.modules.publishing.api.youtube_sync import router as youtube_sync_router
from creatoriqx_api.modules.publishing.application.approval_service import ApprovalService
from creatoriqx_api.modules.publishing.application.capability_service import CapabilityService
from creatoriqx_api.modules.publishing.application.qa_service import QaService
from creatoriqx_api.modules.publishing.application.youtube_sync_service import (
    YoutubeSyncService,
)
from creatoriqx_api.modules.publishing.infrastructure.sql_publish_snapshot_store import (
    SqlPublishSnapshotStore,
)
from creatoriqx_api.modules.publishing.infrastructure.sql_remote_snapshot_store import (
    SqlRemoteSnapshotStore,
)
from creatoriqx_api.modules.publishing.infrastructure.sql_sync_operation_store import (
    SqlSyncOperationStore,
)
from creatoriqx_api.modules.publishing.infrastructure.sql_video_link_store import (
    SqlYoutubeVideoLinkStore,
)
from creatoriqx_api.modules.transcripts.api.transcripts import router as transcripts_router
from creatoriqx_api.modules.transcripts.application.transcript_service import TranscriptService
from creatoriqx_api.modules.transcripts.infrastructure.sql_transcript_store import (
    SqlTranscriptStore,
)
from creatoriqx_api.modules.workspaces.api.routes import router as workspaces_router
from creatoriqx_api.modules.workspaces.application.access_service import WorkspaceAccessService
from creatoriqx_api.modules.workspaces.application.bootstrap_service import (
    WorkspaceBootstrapService,
)
from creatoriqx_api.modules.workspaces.infrastructure.sql_access_store import (
    SqlWorkspaceAccessStore,
)
from creatoriqx_api.modules.workspaces.infrastructure.sql_store import SqlPersonalWorkspaceStore
from creatoriqx_api.modules.youtube.api.connect import router as youtube_connect_router
from creatoriqx_api.modules.youtube.api.ingestion import router as youtube_ingestion_router
from creatoriqx_api.modules.youtube.application.connection_service import (
    ChannelConnectionService,
)
from creatoriqx_api.modules.youtube.infrastructure.google_oauth import GoogleYouTubeOAuthProvider
from creatoriqx_api.modules.youtube.infrastructure.quota_ledger import RedisPostgresQuotaLedger
from creatoriqx_api.modules.youtube.infrastructure.sql_capability_store import SqlCapabilityStore
from creatoriqx_api.modules.youtube.infrastructure.sql_connection_store import (
    SqlChannelConnectionStore,
    SqlChannelVideoStore,
)
from creatoriqx_api.modules.youtube.infrastructure.youtube_data_api import (
    HttpYouTubeDataApiClient,
)
from creatoriqx_api.platform.crypto import TokenCipher, load_key
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
    _wire_planning(app, engine)
    app.include_router(planner_router, prefix=API_V1_PREFIX)
    app.include_router(videos_router, prefix=API_V1_PREFIX)
    _wire_transcripts(app, engine)
    app.include_router(transcripts_router, prefix=API_V1_PREFIX)
    _wire_content(app, engine)
    app.include_router(scripts_router, prefix=API_V1_PREFIX)
    app.include_router(content_metadata_router, prefix=API_V1_PREFIX)
    app.include_router(chapters_router, prefix=API_V1_PREFIX)
    _wire_publishing(app, engine)
    app.include_router(qa_router, prefix=API_V1_PREFIX)
    app.include_router(approval_router, prefix=API_V1_PREFIX)
    app.state.task_queue = CeleryTaskQueue()

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

    if settings.youtube_oauth_client_id:
        _wire_youtube(app, settings, engine, redis)
        app.include_router(youtube_connect_router, prefix=API_V1_PREFIX)
        app.include_router(youtube_ingestion_router, prefix=API_V1_PREFIX)
        app.include_router(intelligence_router, prefix=API_V1_PREFIX)
        app.include_router(youtube_sync_router, prefix=API_V1_PREFIX)

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


def _wire_planning(app: FastAPI, engine: AsyncEngine) -> None:
    """The planner and video-lifecycle services (Phase 1B). No feature flag:

    unlike YouTube connect/ingestion, the planner and video board need no
    external credentials, so they are always wired, like workspaces.
    """
    factory = create_session_factory(engine)
    plan_store = SqlPlanStore(factory)
    video_store = SqlVideoStore(factory)
    app.state.planner_service = PlannerService(plan_store, video_store)
    app.state.video_lifecycle_service = VideoLifecycleService(video_store)


def _wire_transcripts(app: FastAPI, engine: AsyncEngine) -> None:
    """The shared transcript service (Phase 1C, spec feature 22). No feature
    flag: paste/upload need no external credentials, like the planner.
    """
    factory = create_session_factory(engine)
    transcript_store = SqlTranscriptStore(factory)
    app.state.transcript_store = transcript_store
    app.state.transcript_service = TranscriptService(transcript_store)


def _wire_content(app: FastAPI, engine: AsyncEngine) -> None:
    """Script, metadata/SEO and chapter version services (Phase 1C).

    ``ChapterService`` is built after ``_wire_transcripts`` and takes the
    same ``SqlTranscriptStore`` instance directly - it satisfies the
    ``TranscriptStore`` protocol, so no new port is needed to read a
    transcript from inside the content module.
    """
    factory = create_session_factory(engine)
    app.state.script_service = ScriptService(SqlScriptStore(factory))
    app.state.metadata_service = MetadataService(SqlMetadataStore(factory))
    app.state.chapter_service = ChapterService(SqlChapterStore(factory), app.state.transcript_store)


def _wire_publishing(app: FastAPI, engine: AsyncEngine) -> None:
    """QA, approval and capability services (Phase 1D). No feature flag: like
    the planner, transcripts and content, none of this needs external
    credentials - only ``YoutubeSyncService`` (wired inside ``_wire_youtube``
    below) does, because it is the one piece that calls the real YouTube API.

    The stores built here are also stashed on ``app.state`` so
    ``_wire_youtube`` can hand the exact same instances to
    ``YoutubeSyncService`` rather than constructing a second, redundant set.
    """
    factory = create_session_factory(engine)
    link_store = SqlYoutubeVideoLinkStore(factory)
    snapshot_store = SqlPublishSnapshotStore(factory)
    remote_snapshot_store = SqlRemoteSnapshotStore(factory)
    sync_op_store = SqlSyncOperationStore(factory)
    capability_store = SqlCapabilityStore(factory)
    metadata_store = SqlMetadataStore(factory)

    qa_service = QaService(
        script_store=SqlScriptStore(factory),
        metadata_store=metadata_store,
        chapter_store=SqlChapterStore(factory),
        video_link_store=link_store,
        remote_snapshot_store=remote_snapshot_store,
    )
    app.state.qa_service = qa_service
    app.state.approval_service = ApprovalService(
        qa_service=qa_service,
        script_store=SqlScriptStore(factory),
        metadata_store=metadata_store,
        chapter_store=SqlChapterStore(factory),
        snapshot_store=snapshot_store,
        video_store=SqlVideoStore(factory),
    )
    app.state.capability_service = CapabilityService(capability_store)

    app.state.publish_snapshot_store = snapshot_store
    app.state.youtube_video_link_store = link_store
    app.state.sync_operation_store = sync_op_store
    app.state.remote_snapshot_store = remote_snapshot_store
    app.state.publishing_metadata_store = metadata_store


def _wire_youtube(app: FastAPI, settings: Settings, engine: AsyncEngine, redis: Redis) -> None:
    """The youtube connection/ingestion and intelligence/audit services (Phase 1A).

    Gated on ``youtube_oauth_client_id`` being set, same convention as login's
    ``oidc_client_id`` gate: a deployment that hasn't configured the YouTube
    OAuth client yet runs without these routes rather than crash-looping on
    missing config, and a required-key check only happens once a connection
    is actually attempted (``TokenCipher`` is built here, not deferred,
    because a misconfigured key should fail fast at startup, not mid-request).
    """
    factory = create_session_factory(engine)
    cipher = TokenCipher(
        settings.token_encryption_key_id, load_key(settings.token_encryption_key.get_secret_value())
    )
    connection_store = SqlChannelConnectionStore(factory, cipher)
    video_store = SqlChannelVideoStore(factory)
    oauth_provider = GoogleYouTubeOAuthProvider(
        client_id=settings.youtube_oauth_client_id,
        client_secret=settings.youtube_oauth_client_secret.get_secret_value(),
    )
    data_api_client = HttpYouTubeDataApiClient()

    app.state.youtube_connection_service = ChannelConnectionService(
        oauth_provider=oauth_provider,
        data_api_client=data_api_client,
        store=connection_store,
        state_store=app.state.key_value_store,
        flow_ttl_seconds=settings.youtube_oauth_flow_ttl_seconds,
    )
    app.state.quota_ledger = RedisPostgresQuotaLedger(
        redis_client=redis, session_factory=factory, daily_cap=settings.youtube_daily_quota_units
    )
    app.state.recommendation_store = SqlRecommendationStore(factory)
    app.state.channel_audit_service = ChannelAuditService(
        video_reader=YouTubeChannelVideoReader(video_store),
        recommendation_store=app.state.recommendation_store,
    )

    # YoutubeSyncService is the one publishing-module service that needs a
    # real channel connection and write client, so it is wired here, gated
    # exactly like the rest of this function, rather than in the always-on
    # ``_wire_publishing`` - reusing the stores that function already put on
    # ``app.state`` instead of constructing a second set.
    app.state.youtube_sync_service = YoutubeSyncService(
        link_store=app.state.youtube_video_link_store,
        snapshot_store=app.state.publish_snapshot_store,
        sync_op_store=app.state.sync_operation_store,
        remote_snapshot_store=app.state.remote_snapshot_store,
        metadata_store=app.state.publishing_metadata_store,
        capabilities=app.state.capability_service,
        connection_store=connection_store,
        data_api_client=data_api_client,
        write_client=data_api_client,
    )


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

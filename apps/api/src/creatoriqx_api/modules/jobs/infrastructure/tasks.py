"""Celery tasks (ADR 0003, P0-060: "one working job"; P0-061: outbox relay).

Imported by ``celery_app.py`` once the app exists, so decorating with
``@celery_app.task`` registers these on the one shared app instance.

``ops.ping`` is the one working example the Phase 0 depth rule asks for: it
carries a correlation id into its own structured logs and returns a result
the caller can observe through the Celery result backend. ``ops.flaky`` only
exists to prove retry-with-backoff-then-failed behavior in the P0-060
integration test; it is not meant to be enqueued by product code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import async_sessionmaker

from creatoriqx_api.modules.jobs.application.outbox_relay import HandlerRegistry, OutboxRelay
from creatoriqx_api.modules.jobs.application.ports import OutboxEventRecord
from creatoriqx_api.modules.jobs.infrastructure.celery_app import celery_app
from creatoriqx_api.modules.jobs.infrastructure.outbox_gateway import SqlOutboxGateway
from creatoriqx_api.platform.database import create_engine, create_session_factory
from creatoriqx_api.settings import get_settings

if TYPE_CHECKING:
    # Type-checking only: the module boundary (ADR 0003's jobs-celery-boundary
    # contract permits jobs.infrastructure to build other modules' adapters,
    # same as _default_relay() already does for the outbox) stays a runtime
    # lazy import inside each function below, not a module-level dependency.
    from creatoriqx_api.modules.intelligence.application.audit_service import (
        ChannelAuditService,
    )
    from creatoriqx_api.modules.youtube.application.ingestion_service import (
        ChannelIngestionService,
    )

logger = structlog.get_logger(__name__)


async def _handle_workspace_created(event: OutboxEventRecord) -> None:
    # No other module consumes this yet (P0-061 is the relay mechanism, not a
    # subscriber); logging it is the one working example, matching how
    # ``ops.ping`` is the one working job rather than a real product task.
    logger.info("outbox.workspace_created", payload=event.payload)


def _default_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.on("workspace.created", _handle_workspace_created)
    return registry


def _default_relay() -> OutboxRelay:
    # Built per task invocation, not at import time: Celery imports this
    # module to register tasks before Settings' required DB fields are
    # necessarily available (same reasoning as celery_app.py's broker URL).
    settings = get_settings()
    factory: async_sessionmaker[Any] = create_session_factory(create_engine(settings))
    return OutboxRelay(SqlOutboxGateway(factory), _default_registry())


@celery_app.task(name="ops.ping")
def ops_ping(
    payload: dict[str, Any] | None = None, correlation_id: str | None = None
) -> dict[str, Any]:
    """Prove the queue works end to end: enqueue, run, return an observable result."""
    with structlog.contextvars.bound_contextvars(correlation_id=correlation_id):
        logger.info("ops.ping.start", payload=payload)
        result = {"ok": True, "echo": payload or {}, "correlation_id": correlation_id}
        logger.info("ops.ping.done", result=result)
        return result


@celery_app.task(
    name="ops.flaky",
    bind=True,
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=2,
    retry_jitter=True,
)
def ops_flaky(
    self: Task, payload: dict[str, Any] | None = None, correlation_id: str | None = None
) -> None:
    """Always fail, to prove retries-with-backoff-then-failed (P0-060 acceptance test).

    Never enqueued outside tests. Celery schedules the retries itself from
    ``self.retry()``; once ``max_retries`` is exhausted, the next retry call
    re-raises the original exception and the task lands in FAILURE.
    """
    with structlog.contextvars.bound_contextvars(correlation_id=correlation_id):
        logger.info("ops.flaky.attempt", attempt=self.request.retries + 1)
        try:
            raise RuntimeError("ops.flaky always fails, by design")
        except RuntimeError as exc:
            # self.retry(throw=True, the default) already raises internally; once
            # max_retries is exhausted it re-raises `exc` itself, which is what the
            # integration test's pytest.raises(RuntimeError, ...) observes.
            self.retry(exc=exc)


@celery_app.task(name="outbox.relay")
def outbox_relay(limit: int = 50, correlation_id: str | None = None) -> dict[str, Any]:
    """Drain up to ``limit`` unpublished ``outbox_events`` (P0-061).

    Minimal relay, not a scheduler: in production this task is invoked
    periodically (Celery beat or an equivalent trigger outside this ticket's
    scope). At-least-once delivery - see ``OutboxGateway.relay_batch`` - so
    every registered handler must be idempotent.
    """
    import asyncio

    with structlog.contextvars.bound_contextvars(correlation_id=correlation_id):
        logger.info("outbox.relay.start", limit=limit)
        relayed = asyncio.run(_default_relay().run_once(limit=limit))
        logger.info("outbox.relay.done", relayed=relayed)
        return {"relayed": relayed}


def _build_youtube_ingestion_service() -> ChannelIngestionService:
    # Built per task invocation, same reasoning as _default_relay(): Celery
    # imports this module to register tasks before Settings' required
    # fields are necessarily available.
    from redis.asyncio import Redis

    from creatoriqx_api.modules.youtube.application.ingestion_service import (
        ChannelIngestionService,
    )
    from creatoriqx_api.modules.youtube.infrastructure.quota_ledger import (
        RedisPostgresQuotaLedger,
    )
    from creatoriqx_api.modules.youtube.infrastructure.sql_connection_store import (
        SqlChannelConnectionStore,
        SqlChannelVideoStore,
    )
    from creatoriqx_api.modules.youtube.infrastructure.youtube_data_api import (
        HttpYouTubeDataApiClient,
    )
    from creatoriqx_api.platform.crypto import TokenCipher, load_key

    settings = get_settings()
    factory: async_sessionmaker[Any] = create_session_factory(create_engine(settings))
    cipher = TokenCipher(
        settings.token_encryption_key_id, load_key(settings.token_encryption_key.get_secret_value())
    )
    redis_client = Redis.from_url(settings.redis_url.get_secret_value())
    return ChannelIngestionService(
        connection_store=SqlChannelConnectionStore(factory, cipher),
        video_store=SqlChannelVideoStore(factory),
        data_api_client=HttpYouTubeDataApiClient(),
        quota_ledger=RedisPostgresQuotaLedger(
            redis_client=redis_client,
            session_factory=factory,
            daily_cap=settings.youtube_daily_quota_units,
        ),
    )


@celery_app.task(name="youtube.ingest_channel")
def youtube_ingest_channel(
    payload: dict[str, Any] | None = None, correlation_id: str | None = None
) -> dict[str, Any]:
    """Refresh one connected channel's own data from the YouTube Data API (spec §3).

    At-least-once delivery: ``ChannelIngestionService.ingest`` is idempotent
    (channel stats and video rows are upserted, never appended), so a
    redelivered task is safe to run again.
    """
    import asyncio
    import uuid

    payload = payload or {}
    with structlog.contextvars.bound_contextvars(correlation_id=correlation_id):
        workspace_id = uuid.UUID(payload["workspace_id"])
        channel_id = uuid.UUID(payload["channel_id"])
        logger.info("youtube.ingest_channel.start", workspace_id=str(workspace_id))
        service = _build_youtube_ingestion_service()
        ingested = asyncio.run(service.ingest(workspace_id=workspace_id, channel_id=channel_id))
        logger.info("youtube.ingest_channel.done", ingested=ingested)
        return {"ingested": ingested}


def _build_channel_audit_service() -> ChannelAuditService:
    from creatoriqx_api.modules.intelligence.application.audit_service import (
        ChannelAuditService,
    )
    from creatoriqx_api.modules.intelligence.infrastructure.sql_recommendation_store import (
        SqlRecommendationStore,
    )
    from creatoriqx_api.modules.intelligence.infrastructure.youtube_video_reader import (
        YouTubeChannelVideoReader,
    )
    from creatoriqx_api.modules.youtube.infrastructure.sql_connection_store import (
        SqlChannelVideoStore,
    )

    settings = get_settings()
    factory: async_sessionmaker[Any] = create_session_factory(create_engine(settings))
    return ChannelAuditService(
        video_reader=YouTubeChannelVideoReader(SqlChannelVideoStore(factory)),
        recommendation_store=SqlRecommendationStore(factory),
    )


@celery_app.task(name="intelligence.run_audit")
def intelligence_run_audit(
    payload: dict[str, Any] | None = None, correlation_id: str | None = None
) -> dict[str, Any]:
    """Run a channel audit and persist its findings as recommendations (spec §4 feature #2).

    Enqueued after ``youtube.ingest_channel`` completes (or run on demand via
    the API's own synchronous route); safe to run again, since each run
    simply appends a fresh batch of recommendations.
    """
    import asyncio
    import uuid

    payload = payload or {}
    with structlog.contextvars.bound_contextvars(correlation_id=correlation_id):
        workspace_id = uuid.UUID(payload["workspace_id"])
        channel_id = uuid.UUID(payload["channel_id"])
        logger.info("intelligence.run_audit.start", workspace_id=str(workspace_id))
        service = _build_channel_audit_service()
        recommendations = asyncio.run(service.run(workspace_id=workspace_id, channel_id=channel_id))
        logger.info("intelligence.run_audit.done", count=len(recommendations))
        return {"recommendation_count": len(recommendations)}

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

from typing import Any

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import async_sessionmaker

from creatoriqx_api.modules.jobs.application.outbox_relay import HandlerRegistry, OutboxRelay
from creatoriqx_api.modules.jobs.application.ports import OutboxEventRecord
from creatoriqx_api.modules.jobs.infrastructure.celery_app import celery_app
from creatoriqx_api.modules.jobs.infrastructure.outbox_gateway import SqlOutboxGateway
from creatoriqx_api.platform.database import create_engine, create_session_factory
from creatoriqx_api.settings import get_settings

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

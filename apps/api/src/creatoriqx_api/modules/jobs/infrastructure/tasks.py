"""Celery tasks (ADR 0003, P0-060: "one working job").

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

from creatoriqx_api.modules.jobs.infrastructure.celery_app import celery_app

logger = structlog.get_logger(__name__)


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

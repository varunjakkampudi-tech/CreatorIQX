"""The Celery adapter for the ``TaskQueue`` port (ADR 0003)."""

from __future__ import annotations

from celery import Celery

from creatoriqx_api.modules.jobs.domain.ports import JobHandle, JobRequest, TaskQueue
from creatoriqx_api.modules.jobs.infrastructure.celery_app import celery_app as _default_app


class CeleryTaskQueue(TaskQueue):
    """Enqueues a ``JobRequest`` as a Celery task by name.

    Takes the Celery app as a constructor argument (defaulting to the one
    process-wide ``celery_app`` singleton) rather than importing it as a
    bare module-level name, so an integration test can point this at its own
    app - built with its own broker URL and its own registered tasks -
    instead of silently talking to the production singleton.
    """

    def __init__(self, app: Celery | None = None) -> None:
        self._app = app if app is not None else _default_app

    def enqueue(self, request: JobRequest) -> JobHandle:
        async_result = self._app.send_task(
            request.name,
            kwargs={"payload": request.payload, "correlation_id": request.correlation_id},
        )
        return JobHandle(job_id=async_result.id)

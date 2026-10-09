"""The Celery application (ADR 0003): Redis broker, Redis result backend.

Only this module, ``tasks.py`` and ``celery_task_queue.py`` may import
Celery or Redis directly - enforced by import-linter's
``jobs-celery-boundary`` contract (``pyproject.toml``). Everything else in
the codebase enqueues through the ``TaskQueue`` port (``domain/ports.py``)
and never sees Celery.
"""

from __future__ import annotations

import os

from celery import Celery

_DEFAULT_BROKER_URL = "redis://127.0.0.1:56379/1"


def create_celery_app(broker_url: str | None = None) -> Celery:
    """Build the Celery app.

    Deliberately reads ``CELERY_BROKER_URL`` from the environment directly
    rather than through ``creatoriqx_api.settings.get_settings()``: this
    module is imported (and the app built) at collection time by any test
    that touches a job, and ``Settings`` has unrelated required fields
    (``database_app_url``, ``redis_url``) with no defaults. Integration
    tests that need a different broker (or a fake one) pass ``broker_url``
    explicitly instead of depending on process-wide environment variables,
    matching how ``tests/integration/*`` build their own ``Settings`` rather
    than trusting ``get_settings()`` (see ``test_readiness.py``).
    """
    broker_url = broker_url or os.environ.get("CELERY_BROKER_URL", _DEFAULT_BROKER_URL)
    app = Celery("creatoriqx", broker=broker_url, backend=broker_url)
    app.conf.update(
        # At-least-once delivery (ADR 0003 decision 3): a job that crashes
        # mid-run is redelivered rather than silently lost, so every job
        # must be safe to run more than once.
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        # Visible progress/result without a separate status table (Phase 0
        # depth rule: the result backend is enough evidence for one job).
        task_track_started=True,
        result_extended=True,
        worker_prefetch_multiplier=1,
        timezone="UTC",
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
    )
    return app


celery_app = create_celery_app()

# Tasks register themselves on `celery_app` by decorating with @celery_app.task
# at import time, so importing this module here (after the app exists, to
# avoid a circular import) is what makes them known to both the enqueuing
# side and the worker process.
from creatoriqx_api.modules.jobs.infrastructure import tasks  # noqa: E402,F401

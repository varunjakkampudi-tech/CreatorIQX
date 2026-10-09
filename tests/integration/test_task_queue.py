"""TaskQueue port against a real Celery worker and Redis broker (P0-060).

Needs ``py scripts/dev.py up``. Runs an embedded worker thread (Celery's own
test helper) against the real local Redis, so retry backoff/jitter and
result-backend behavior are exercised for real, not mocked.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from celery.contrib.testing.worker import start_worker
from dotenv import dotenv_values

from creatoriqx_api.modules.jobs.domain.ports import JobRequest
from creatoriqx_api.modules.jobs.infrastructure.celery_app import create_celery_app
from creatoriqx_api.modules.jobs.infrastructure.celery_task_queue import CeleryTaskQueue

pytestmark = pytest.mark.integration

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _task_queue_broker_url() -> str:
    """Same host/port as ``REDIS_URL`` in ``.env``, but Celery's own logical db (1)."""
    redis_url = dotenv_values(ENV_FILE).get("REDIS_URL")
    if not redis_url:
        pytest.fail(".env is missing or incomplete. Run: py scripts/dev.py setup")
    return re.sub(r"/\d+$", "/1", redis_url)


@pytest.fixture
def celery_app() -> Iterator[object]:
    app = create_celery_app(broker_url=_task_queue_broker_url())
    # Importing tasks.py registers ops.ping/ops.flaky on *this* app instance
    # too (Celery tasks can be bound to more than one app); the module-level
    # `celery_app` singleton stays untouched for production use.
    from creatoriqx_api.modules.jobs.infrastructure import tasks as tasks_module

    app.register_task(tasks_module.ops_ping)
    app.register_task(tasks_module.ops_flaky)
    app.conf.update(result_expires=60)
    # perform_ping_check (default True) blocks start_worker() until the
    # embedded worker has actually started consuming, over the broker's
    # control/pidbox channel. Skipping it let the test send a task before
    # the worker was listening, so the job sat unacked until the client gave
    # up waiting on the result (visible as "Restoring unacknowledged
    # message(s)" at teardown).
    with start_worker(app, pool="solo", shutdown_timeout=30):
        yield app


def test_enqueue_via_port_job_completes_result_observed(celery_app: object) -> None:
    queue = CeleryTaskQueue(app=celery_app)  # type: ignore[arg-type]
    correlation_id = str(uuid.uuid4())
    handle = queue.enqueue(
        JobRequest(name="ops.ping", payload={"hello": "world"}, correlation_id=correlation_id)
    )

    async_result = celery_app.AsyncResult(handle.job_id)  # type: ignore[attr-defined]
    result = async_result.get(timeout=15)

    assert async_result.state == "SUCCESS"
    assert result == {
        "ok": True,
        "echo": {"hello": "world"},
        "correlation_id": correlation_id,
    }


def test_failing_job_retries_then_lands_in_failed_state(celery_app: object) -> None:
    queue = CeleryTaskQueue(app=celery_app)  # type: ignore[arg-type]
    handle = queue.enqueue(JobRequest(name="ops.flaky"))

    async_result = celery_app.AsyncResult(handle.job_id)  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match=re.escape("ops.flaky always fails, by design")):
        async_result.get(timeout=30)

    assert async_result.state == "FAILURE"
    # max_retries=2: the task retried at least once before Celery gave up
    # and marked it FAILURE (exact count depends on backend timing, so this
    # checks "it actually retried", not a precise number).
    assert async_result.retries >= 1

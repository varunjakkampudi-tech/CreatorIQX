"""Unit tests for the TaskQueue port and its Celery adapter (P0-060, ADR 0003).

No broker needed: ``send_task`` is monkeypatched, so this runs everywhere
`uv run pytest` does. The real end-to-end behavior (a job actually completing,
a failing job actually retrying with backoff then landing in FAILURE) is
proven against a real Redis broker in ``tests/integration/test_task_queue.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

from creatoriqx_api.modules.jobs.domain.ports import JobHandle, JobRequest
from creatoriqx_api.modules.jobs.infrastructure.celery_task_queue import CeleryTaskQueue


class _FakeAsyncResult:
    def __init__(self, task_id: str) -> None:
        self.id = task_id


def test_enqueue_sends_the_named_task_with_payload_and_correlation_id(
    monkeypatch: Any,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_send_task(name: str, kwargs: dict[str, Any]) -> _FakeAsyncResult:
        calls.append((name, kwargs))
        return _FakeAsyncResult(task_id="fake-task-id")

    monkeypatch.setattr(
        "creatoriqx_api.modules.jobs.infrastructure.celery_task_queue._default_app.send_task",
        fake_send_task,
    )

    workspace_id = uuid.uuid4()
    request = JobRequest(
        name="ops.ping",
        payload={"foo": "bar"},
        workspace_id=workspace_id,
        correlation_id="corr-123",
    )

    handle = CeleryTaskQueue().enqueue(request)

    assert handle == JobHandle(job_id="fake-task-id")
    assert calls == [("ops.ping", {"payload": {"foo": "bar"}, "correlation_id": "corr-123"})]

"""The ``TaskQueue`` port (ADR 0003).

Application code depends only on this protocol, never on Celery directly -
that keeps use-case tests fast (a fake adapter needs no broker) and the
execution engine replaceable (spec §18 forbids locking into one workflow
engine without an ADR). Only ``jobs.infrastructure`` may import Celery or
Redis (enforced by import-linter's ``jobs-celery-boundary`` contract).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class JobRequest:
    """A unit of background work to enqueue.

    ``correlation_id`` is carried into the job so its logs can be joined back
    to the request (or caller) that triggered it (spec §10 Logging).
    ``idempotency_key`` is reserved for callers that need at-most-once side
    effects on top of Celery's at-least-once delivery; Phase 0's one job
    (``ops.ping``) doesn't need it, but the field exists so callers don't need
    a breaking change later.
    """

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    workspace_id: uuid.UUID | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class JobHandle:
    """What enqueuing returns: enough to look the job back up."""

    job_id: str


class TaskQueue(Protocol):
    """Enqueue a named job and get back a handle to its eventual result."""

    def enqueue(self, request: JobRequest) -> JobHandle: ...

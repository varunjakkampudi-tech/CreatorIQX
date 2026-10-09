"""Ports for the outbox relay use case (spec §6 event-driven, P0-061).

Mirrors the ``TaskQueue`` port: application code depends only on these
protocols, never on SQLAlchemy or Celery directly, so the relay's dispatch
logic can be unit-tested with a fake gateway and only ``jobs.infrastructure``
needs a real database connection.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class OutboxEventRecord:
    """One row read from ``outbox_events``, as seen by a handler."""

    id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


EventHandler = Callable[[OutboxEventRecord], Awaitable[None]]


class EventDispatcher(Protocol):
    """Routes one event to whatever in-process handler(s) care about it."""

    async def dispatch(self, event: OutboxEventRecord) -> None:
        """Handle ``event``. Raising aborts the batch that contains it."""


class OutboxGateway(Protocol):
    """Owns the lock-dispatch-commit cycle against the real ``outbox_events`` table."""

    async def relay_batch(self, dispatcher: EventDispatcher, *, limit: int) -> int:
        """Lock up to ``limit`` unpublished events and hand each to ``dispatcher``.

        Implementations must: select with ``FOR UPDATE SKIP LOCKED`` (so a
        concurrent relay never processes the same row twice); dispatch events
        in order; mark an event published only after its dispatch returns
        without raising; commit the whole batch atomically. If any dispatch
        raises, the entire batch rolls back - already-locked rows are
        released unpublished and will be picked up by the next call. This
        gives at-least-once delivery: a handler may be called more than once
        for the same event and must be idempotent.

        Returns the number of events relayed (dispatched and marked published).
        """

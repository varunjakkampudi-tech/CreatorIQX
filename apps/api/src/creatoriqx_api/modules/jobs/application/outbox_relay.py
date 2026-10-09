"""The outbox relay use case (spec §6 event-driven, ticket P0-061).

``HandlerRegistry`` is the one working example the Phase 0 depth rule asks
for: a plain dict of in-process async callables keyed by event type, not a
generalized event bus. An event type with no registered handler is logged
and skipped rather than raising, so one unknown event type never blocks the
rest of a batch or wedges the relay.
"""

from __future__ import annotations

import structlog

from creatoriqx_api.modules.jobs.application.ports import (
    EventHandler,
    OutboxEventRecord,
    OutboxGateway,
)

logger = structlog.get_logger(__name__)


class HandlerRegistry:
    """Maps an event type to the in-process handler(s) that act on it."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def on(self, event_type: str, handler: EventHandler) -> None:
        """Register ``handler`` to run whenever ``event_type`` is relayed."""
        self._handlers.setdefault(event_type, []).append(handler)

    async def dispatch(self, event: OutboxEventRecord) -> None:
        handlers = self._handlers.get(event.event_type)
        if not handlers:
            logger.warning("outbox.unhandled_event_type", event_type=event.event_type)
            return
        for handler in handlers:
            await handler(event)


class OutboxRelay:
    """Drains unpublished outbox events through a ``HandlerRegistry``-style dispatcher."""

    def __init__(self, gateway: OutboxGateway, dispatcher: HandlerRegistry) -> None:
        self._gateway = gateway
        self._dispatcher = dispatcher

    async def run_once(self, *, limit: int = 50) -> int:
        """Relay up to ``limit`` events in one locked batch. Returns the count relayed."""
        return await self._gateway.relay_batch(self._dispatcher, limit=limit)

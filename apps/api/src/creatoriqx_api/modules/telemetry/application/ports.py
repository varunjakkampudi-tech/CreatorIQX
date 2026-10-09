"""The ``TelemetrySink`` port (ticket P0-062).

Application code depends only on this protocol, never on SQLAlchemy
directly - mirrors the ``TaskQueue`` and ``OutboxGateway`` ports in the
``jobs`` module.
"""

from __future__ import annotations

from typing import Protocol

from creatoriqx_api.modules.telemetry.domain.usage_event import UsageEventRecord


class TelemetrySink(Protocol):
    """Persists one already-sanitized usage event."""

    async def emit(self, event: UsageEventRecord) -> None: ...

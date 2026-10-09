"""The real ``OutboxGateway`` adapter (ticket P0-061).

``outbox_events`` carries no ``workspace_id`` and has no RLS policy (see
``tables.py``): the relay is a platform-level process that must see every
tenant's unpublished events, so it connects and queries like any other
infrastructure code, with no ``set_tenant_context`` call.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.jobs.application.ports import EventDispatcher, OutboxEventRecord
from creatoriqx_api.modules.jobs.infrastructure.tables import OutboxEvent
from creatoriqx_api.platform.database import session_scope


class SqlOutboxGateway:
    """Locks, dispatches and marks published - one Postgres transaction per batch."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def relay_batch(self, dispatcher: EventDispatcher, *, limit: int = 50) -> int:
        async with session_scope(self._session_factory) as session:
            result = await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = result.scalars().all()
            for row in rows:
                record = OutboxEventRecord(
                    id=row.id,
                    event_type=row.event_type,
                    payload=row.payload,
                    created_at=row.created_at,
                )
                # Not yet committed: if this raises, session_scope rolls back
                # the whole batch and every locked row stays unpublished for
                # the next caller to pick up (at-least-once, crash-safe).
                await dispatcher.dispatch(record)
                row.published_at = datetime.now(UTC)
            return len(rows)

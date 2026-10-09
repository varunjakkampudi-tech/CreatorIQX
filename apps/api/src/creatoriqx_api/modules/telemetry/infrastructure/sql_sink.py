"""The real ``TelemetrySink`` adapter (ticket P0-062).

``usage_events`` is an ordinary forced-RLS tenant table (unlike
``outbox_events``), so every write sets the tenant context first. When the
event carries no ``user_id`` (not the case for ``auth.login_succeeded``, but
the port allows it), a nil UUID stands in: the ``usage_events`` RLS policy
only checks ``workspace_id`` (see migration 0004), so this is never checked
against, only required because ``set_tenant_context`` always sets one.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.telemetry.domain.usage_event import UsageEventRecord
from creatoriqx_api.modules.telemetry.infrastructure.tables import UsageEvent
from creatoriqx_api.platform.database import session_scope, set_tenant_context

_NO_ACTOR = uuid.UUID(int=0)


class SqlTelemetrySink:
    """Writes one usage event in its own transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def emit(self, event: UsageEventRecord) -> None:
        async with session_scope(self._session_factory) as session:
            await set_tenant_context(
                session, workspace_id=event.workspace_id, user_id=event.user_id or _NO_ACTOR
            )
            session.add(
                UsageEvent(
                    workspace_id=event.workspace_id,
                    user_id=event.user_id,
                    name=event.name,
                    schema_version=event.schema_version,
                    properties=event.properties,
                )
            )

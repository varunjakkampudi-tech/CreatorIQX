"""SQLAlchemy adapter for :class:`VideoStore`.

Every create and every status change writes an ``audit_log`` row and an
``outbox_events`` row in the same transaction as the ``videos`` write (spec
§3: "Every transition writes an audit log entry and emits a domain event").
This mirrors the pattern ``workspaces.infrastructure.sql_store`` already
uses for workspace creation - cross-cutting concerns (audit, the outbox) are
written to directly from a module's infrastructure layer rather than through
a port, since they are shared-kernel tables, not another bounded context's
owned aggregate.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.audit.infrastructure.tables import AuditLog
from creatoriqx_api.modules.jobs.infrastructure.tables import OutboxEvent
from creatoriqx_api.modules.planning.application.ports import NewVideo
from creatoriqx_api.modules.planning.domain.errors import VideoNotFoundError
from creatoriqx_api.modules.planning.domain.video import Video, VideoStatus
from creatoriqx_api.modules.planning.infrastructure.tables import VideoRow
from creatoriqx_api.platform.database import session_scope, set_tenant_context

# videos' RLS policy only checks workspace_id, never user_id; reads have no
# acting user to attribute, so a nil UUID stands in (same convention as
# youtube.infrastructure.quota_ledger._NO_ACTOR).
_NO_ACTOR = uuid.UUID(int=0)


class SqlVideoStore:
    """Persists videos, their audit trail and their domain events together."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def create(
        self, video: NewVideo, *, actor_user_id: uuid.UUID, correlation_id: str | None
    ) -> Video:
        async with session_scope(self._factory) as session:
            await set_tenant_context(
                session, workspace_id=video.workspace_id, user_id=actor_user_id
            )
            row = VideoRow(
                workspace_id=video.workspace_id,
                channel_id=video.channel_id,
                plan_id=video.plan_id,
                title=video.title,
                status=video.status.value,
            )
            session.add(row)
            await session.flush()
            _record_transition(
                session,
                workspace_id=video.workspace_id,
                video_id=row.id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
                action="video.created",
                event_type="video.created",
                to_status=video.status,
                from_status=None,
            )
            await session.flush()
            return _to_domain(row)

    async def get(self, *, workspace_id: uuid.UUID, video_id: uuid.UUID) -> Video | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            row = await _fetch(session, workspace_id=workspace_id, video_id=video_id)
            return _to_domain(row) if row is not None else None

    async def list_for_workspace(self, *, workspace_id: uuid.UUID) -> list[Video]:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(VideoRow)
                .where(VideoRow.workspace_id == workspace_id)
                .order_by(VideoRow.created_at.desc())
            )
            return [_to_domain(row) for row in result.scalars().all()]

    async def update_status(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        status: VideoStatus,
        actor_user_id: uuid.UUID,
        correlation_id: str | None,
    ) -> Video:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=actor_user_id)
            row = await _fetch(session, workspace_id=workspace_id, video_id=video_id)
            if row is None:
                raise VideoNotFoundError()
            previous = VideoStatus(row.status)
            row.status = status.value
            await session.flush()
            _record_transition(
                session,
                workspace_id=workspace_id,
                video_id=video_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
                action="video.transitioned",
                event_type="video.transitioned",
                to_status=status,
                from_status=previous,
            )
            await session.flush()
            return _to_domain(row)


async def _fetch(
    session: AsyncSession, *, workspace_id: uuid.UUID, video_id: uuid.UUID
) -> VideoRow | None:
    result = await session.execute(
        select(VideoRow).where(VideoRow.workspace_id == workspace_id, VideoRow.id == video_id)
    )
    return result.scalar_one_or_none()


def _record_transition(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    video_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: str | None,
    action: str,
    event_type: str,
    to_status: VideoStatus,
    from_status: VideoStatus | None,
) -> None:
    session.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type="video",
            resource_id=video_id,
            correlation_id=correlation_id,
            detail={
                "from_status": from_status.value if from_status is not None else None,
                "to_status": to_status.value,
            },
        )
    )
    session.add(
        OutboxEvent(
            event_type=event_type,
            payload={
                "workspace_id": str(workspace_id),
                "video_id": str(video_id),
                "from_status": from_status.value if from_status is not None else None,
                "to_status": to_status.value,
            },
        )
    )


def _to_domain(row: VideoRow) -> Video:
    return Video(
        id=row.id,
        workspace_id=row.workspace_id,
        channel_id=row.channel_id,
        plan_id=row.plan_id,
        title=row.title,
        status=VideoStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )

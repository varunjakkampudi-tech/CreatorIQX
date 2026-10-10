"""SQLAlchemy adapter for :class:`RemoteSnapshotStore`.

Every read supersedes the previous row rather than updating it in place
(domain module docstring) - ``save`` always inserts.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.publishing.application.ports import NewRemoteSnapshot
from creatoriqx_api.modules.publishing.domain.remote_snapshot import RemoteSnapshot
from creatoriqx_api.modules.publishing.infrastructure.tables import RemoteSnapshotRow
from creatoriqx_api.platform.database import session_scope, set_tenant_context

_NO_ACTOR = uuid.UUID(int=0)


class SqlRemoteSnapshotStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def save(self, snapshot: NewRemoteSnapshot) -> RemoteSnapshot:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=snapshot.workspace_id, user_id=_NO_ACTOR)
            row = RemoteSnapshotRow(
                workspace_id=snapshot.workspace_id,
                video_link_id=snapshot.video_link_id,
                fields=snapshot.fields,
                privacy_status=snapshot.privacy_status,
                has_been_published=snapshot.has_been_published,
            )
            session.add(row)
            await session.flush()
            return _to_domain(row)

    async def get_latest_for_link(
        self, *, workspace_id: uuid.UUID, video_link_id: uuid.UUID
    ) -> RemoteSnapshot | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(RemoteSnapshotRow)
                .where(
                    RemoteSnapshotRow.workspace_id == workspace_id,
                    RemoteSnapshotRow.video_link_id == video_link_id,
                )
                .order_by(RemoteSnapshotRow.captured_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row is not None else None


def _to_domain(row: RemoteSnapshotRow) -> RemoteSnapshot:
    return RemoteSnapshot(
        id=row.id,
        workspace_id=row.workspace_id,
        video_link_id=row.video_link_id,
        fields=row.fields,
        privacy_status=row.privacy_status,
        has_been_published=row.has_been_published,
        captured_at=row.captured_at,
    )

"""SQLAlchemy adapter for :class:`PublishSnapshotStore` (ADR 0006).

Insert-only at the application layer *and* at the privilege layer -
migration 0009 grants the app role ``INSERT``/``SELECT`` only on
``publish_snapshots``, so there is deliberately no ``update``/``delete``
method here to even tempt a caller.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.publishing.application.ports import NewPublishSnapshot
from creatoriqx_api.modules.publishing.domain.snapshot import PublishSnapshot
from creatoriqx_api.modules.publishing.infrastructure.tables import PublishSnapshotRow
from creatoriqx_api.platform.database import session_scope, set_tenant_context

_NO_ACTOR = uuid.UUID(int=0)


class SqlPublishSnapshotStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def create(self, snapshot: NewPublishSnapshot) -> PublishSnapshot:
        async with session_scope(self._factory) as session:
            await set_tenant_context(
                session, workspace_id=snapshot.workspace_id, user_id=snapshot.approved_by
            )
            row = PublishSnapshotRow(
                workspace_id=snapshot.workspace_id,
                video_id=snapshot.video_id,
                script_version_id=snapshot.script_version_id,
                metadata_version_id=snapshot.metadata_version_id,
                chapter_version_id=snapshot.chapter_version_id,
                thumbnail_variant_id=snapshot.thumbnail_variant_id,
                disclosure_altered=snapshot.disclosure_altered,
                disclosure_synthetic=snapshot.disclosure_synthetic,
                scheduled_at=snapshot.scheduled_at,
                approved_by=snapshot.approved_by,
            )
            session.add(row)
            await session.flush()
            return _to_domain(row)

    async def get(
        self, *, workspace_id: uuid.UUID, snapshot_id: uuid.UUID
    ) -> PublishSnapshot | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(PublishSnapshotRow).where(
                    PublishSnapshotRow.workspace_id == workspace_id,
                    PublishSnapshotRow.id == snapshot_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def get_latest_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> PublishSnapshot | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(PublishSnapshotRow)
                .where(
                    PublishSnapshotRow.workspace_id == workspace_id,
                    PublishSnapshotRow.video_id == video_id,
                )
                .order_by(PublishSnapshotRow.approved_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row is not None else None


def _to_domain(row: PublishSnapshotRow) -> PublishSnapshot:
    return PublishSnapshot(
        id=row.id,
        workspace_id=row.workspace_id,
        video_id=row.video_id,
        script_version_id=row.script_version_id,
        metadata_version_id=row.metadata_version_id,
        chapter_version_id=row.chapter_version_id,
        thumbnail_variant_id=row.thumbnail_variant_id,
        disclosure_altered=row.disclosure_altered,
        disclosure_synthetic=row.disclosure_synthetic,
        scheduled_at=row.scheduled_at,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        created_at=row.created_at,
    )

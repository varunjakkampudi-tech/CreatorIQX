"""SQLAlchemy adapter for :class:`SyncOperationStore` (spec §3: "Record every
attempt as a per-operation row").
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.publishing.application.ports import NewSyncOperation
from creatoriqx_api.modules.publishing.domain.sync_operation import (
    SyncFieldGroup,
    SyncOperation,
    SyncOperationStatus,
)
from creatoriqx_api.modules.publishing.infrastructure.tables import SyncOperationRow
from creatoriqx_api.platform.database import session_scope, set_tenant_context

_NO_ACTOR = uuid.UUID(int=0)


class SqlSyncOperationStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def create(self, operation: NewSyncOperation) -> SyncOperation:
        async with session_scope(self._factory) as session:
            await set_tenant_context(
                session, workspace_id=operation.workspace_id, user_id=_NO_ACTOR
            )
            row = SyncOperationRow(
                workspace_id=operation.workspace_id,
                video_link_id=operation.video_link_id,
                applied_snapshot_id=operation.applied_snapshot_id,
                field_group=operation.field_group.value,
                status=operation.status.value,
                error_details=operation.error_details,
                quota_cost=operation.quota_cost,
                remote_etag=operation.remote_etag,
                readback_verified=operation.readback_verified,
                finished_at=operation.finished_at,
            )
            session.add(row)
            await session.flush()
            return _to_domain(row)

    async def list_for_link(
        self, *, workspace_id: uuid.UUID, video_link_id: uuid.UUID
    ) -> list[SyncOperation]:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(SyncOperationRow)
                .where(
                    SyncOperationRow.workspace_id == workspace_id,
                    SyncOperationRow.video_link_id == video_link_id,
                )
                .order_by(SyncOperationRow.created_at.desc())
            )
            return [_to_domain(row) for row in result.scalars().all()]


def _to_domain(row: SyncOperationRow) -> SyncOperation:
    return SyncOperation(
        id=row.id,
        workspace_id=row.workspace_id,
        video_link_id=row.video_link_id,
        applied_snapshot_id=row.applied_snapshot_id,
        field_group=SyncFieldGroup(row.field_group),
        status=SyncOperationStatus(row.status),
        error_details=row.error_details,
        quota_cost=row.quota_cost,
        remote_etag=row.remote_etag,
        readback_verified=row.readback_verified,
        finished_at=row.finished_at,
        created_at=row.created_at,
    )

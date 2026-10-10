"""SQLAlchemy adapter for :class:`MetadataVersionStore`."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.content.application.ports import NewMetadataVersion
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion
from creatoriqx_api.modules.content.infrastructure.tables import MetadataVersionRow
from creatoriqx_api.platform.database import session_scope, set_tenant_context

_NO_ACTOR = uuid.UUID(int=0)


class SqlMetadataStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def create(self, version: NewMetadataVersion) -> MetadataVersion:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=version.workspace_id, user_id=_NO_ACTOR)
            await session.execute(
                update(MetadataVersionRow)
                .where(
                    MetadataVersionRow.workspace_id == version.workspace_id,
                    MetadataVersionRow.video_id == version.video_id,
                )
                .values(is_current=False)
            )
            row = MetadataVersionRow(
                workspace_id=version.workspace_id,
                video_id=version.video_id,
                title=version.title,
                description=version.description,
                tags=list(version.tags),
                category=version.category,
                disclosure_altered=version.disclosure_altered,
                disclosure_synthetic=version.disclosure_synthetic,
                rationale=version.rationale,
                parent_version_id=version.parent_version_id,
                is_current=True,
            )
            session.add(row)
            await session.flush()
            return _to_domain(row)

    async def get(
        self, *, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> MetadataVersion | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(MetadataVersionRow).where(
                    MetadataVersionRow.workspace_id == workspace_id,
                    MetadataVersionRow.id == version_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[MetadataVersion]:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(MetadataVersionRow)
                .where(
                    MetadataVersionRow.workspace_id == workspace_id,
                    MetadataVersionRow.video_id == video_id,
                )
                .order_by(MetadataVersionRow.created_at.desc())
            )
            return [_to_domain(row) for row in result.scalars().all()]


def _to_domain(row: MetadataVersionRow) -> MetadataVersion:
    return MetadataVersion(
        id=row.id,
        workspace_id=row.workspace_id,
        video_id=row.video_id,
        title=row.title,
        description=row.description,
        tags=tuple(row.tags),
        category=row.category,
        disclosure_altered=row.disclosure_altered,
        disclosure_synthetic=row.disclosure_synthetic,
        rationale=row.rationale,
        parent_version_id=row.parent_version_id,
        is_current=row.is_current,
        created_at=row.created_at,
    )

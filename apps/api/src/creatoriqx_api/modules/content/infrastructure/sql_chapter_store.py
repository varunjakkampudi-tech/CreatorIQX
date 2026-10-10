"""SQLAlchemy adapter for :class:`ChapterVersionStore`."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.content.application.ports import NewChapterVersion
from creatoriqx_api.modules.content.domain.chapters import Chapter, ChapterVersion
from creatoriqx_api.modules.content.infrastructure.tables import ChapterVersionRow
from creatoriqx_api.platform.database import session_scope, set_tenant_context

_NO_ACTOR = uuid.UUID(int=0)


class SqlChapterStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def create(self, version: NewChapterVersion) -> ChapterVersion:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=version.workspace_id, user_id=_NO_ACTOR)
            await session.execute(
                update(ChapterVersionRow)
                .where(
                    ChapterVersionRow.workspace_id == version.workspace_id,
                    ChapterVersionRow.video_id == version.video_id,
                )
                .values(is_current=False)
            )
            row = ChapterVersionRow(
                workspace_id=version.workspace_id,
                video_id=version.video_id,
                transcript_id=version.transcript_id,
                chapters=[
                    {"start_seconds": c.start_seconds, "title": c.title} for c in version.chapters
                ],
                parent_version_id=version.parent_version_id,
                is_current=True,
            )
            session.add(row)
            await session.flush()
            return _to_domain(row)

    async def get(self, *, workspace_id: uuid.UUID, version_id: uuid.UUID) -> ChapterVersion | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(ChapterVersionRow).where(
                    ChapterVersionRow.workspace_id == workspace_id,
                    ChapterVersionRow.id == version_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[ChapterVersion]:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(ChapterVersionRow)
                .where(
                    ChapterVersionRow.workspace_id == workspace_id,
                    ChapterVersionRow.video_id == video_id,
                )
                .order_by(ChapterVersionRow.created_at.desc())
            )
            return [_to_domain(row) for row in result.scalars().all()]


def _to_domain(row: ChapterVersionRow) -> ChapterVersion:
    return ChapterVersion(
        id=row.id,
        workspace_id=row.workspace_id,
        video_id=row.video_id,
        transcript_id=row.transcript_id,
        chapters=tuple(
            Chapter(
                start_seconds=cast(int, c["start_seconds"]),
                title=cast(str, c["title"]),
            )
            for c in row.chapters
        ),
        parent_version_id=row.parent_version_id,
        is_current=row.is_current,
        created_at=row.created_at,
    )

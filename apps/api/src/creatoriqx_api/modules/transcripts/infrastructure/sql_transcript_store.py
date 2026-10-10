"""SQLAlchemy adapter for :class:`TranscriptStore`.

No audit-log/outbox write here, unlike ``planning.infrastructure.sql_video_store``:
spec §3's "every transition writes an audit log entry" is about the video
lifecycle state machine specifically, and creating a transcript version is
not a lifecycle transition. This is a scope decision, recorded in ADR 0014.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.transcripts.application.ports import NewTranscript
from creatoriqx_api.modules.transcripts.domain.transcript import (
    Transcript,
    TranscriptSegment,
    TranscriptSource,
)
from creatoriqx_api.modules.transcripts.infrastructure.tables import (
    TranscriptRow,
    TranscriptSegmentRow,
)
from creatoriqx_api.platform.database import session_scope, set_tenant_context

# transcripts' RLS policy only checks workspace_id, never user_id; this port
# carries no acting user (same convention as planning.infrastructure.sql_plan_store).
_NO_ACTOR = uuid.UUID(int=0)


class SqlTranscriptStore:
    """Persists transcripts and their segments under the caller's tenant context."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def create(self, transcript: NewTranscript) -> Transcript:
        async with session_scope(self._factory) as session:
            await set_tenant_context(
                session, workspace_id=transcript.workspace_id, user_id=_NO_ACTOR
            )
            version = 1
            if transcript.parent_transcript_id is not None:
                parent = await session.get(TranscriptRow, transcript.parent_transcript_id)
                if parent is not None:
                    version = parent.version + 1
            row = TranscriptRow(
                workspace_id=transcript.workspace_id,
                video_id=transcript.video_id,
                source=transcript.source.value,
                language=transcript.language,
                version=version,
                parent_transcript_id=transcript.parent_transcript_id,
            )
            session.add(row)
            await session.flush()
            for ordinal, segment in enumerate(transcript.segments):
                session.add(
                    TranscriptSegmentRow(
                        workspace_id=transcript.workspace_id,
                        transcript_id=row.id,
                        ordinal=ordinal,
                        start_seconds=segment.start_seconds,
                        end_seconds=segment.end_seconds,
                        text=segment.text,
                        confidence=segment.confidence,
                    )
                )
            await session.flush()
            return await _load(session, workspace_id=transcript.workspace_id, transcript_id=row.id)

    async def get(self, *, workspace_id: uuid.UUID, transcript_id: uuid.UUID) -> Transcript | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            try:
                return await _load(session, workspace_id=workspace_id, transcript_id=transcript_id)
            except LookupError:
                return None

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[Transcript]:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(TranscriptRow)
                .where(
                    TranscriptRow.workspace_id == workspace_id, TranscriptRow.video_id == video_id
                )
                .order_by(TranscriptRow.created_at.desc())
            )
            transcripts = []
            for row in result.scalars().all():
                transcripts.append(
                    await _load(session, workspace_id=workspace_id, transcript_id=row.id)
                )
            return transcripts


async def _load(
    session: AsyncSession, *, workspace_id: uuid.UUID, transcript_id: uuid.UUID
) -> Transcript:
    result = await session.execute(
        select(TranscriptRow).where(
            TranscriptRow.workspace_id == workspace_id, TranscriptRow.id == transcript_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise LookupError(transcript_id)
    seg_result = await session.execute(
        select(TranscriptSegmentRow)
        .where(
            TranscriptSegmentRow.workspace_id == workspace_id,
            TranscriptSegmentRow.transcript_id == transcript_id,
        )
        .order_by(TranscriptSegmentRow.ordinal.asc())
    )
    segments = tuple(
        TranscriptSegment(
            start_seconds=seg.start_seconds,
            end_seconds=seg.end_seconds,
            text=seg.text,
            confidence=seg.confidence,
        )
        for seg in seg_result.scalars().all()
    )
    return Transcript(
        id=row.id,
        workspace_id=row.workspace_id,
        video_id=row.video_id,
        source=TranscriptSource(row.source),
        language=row.language,
        version=row.version,
        parent_transcript_id=row.parent_transcript_id,
        segments=segments,
        created_at=row.created_at,
    )

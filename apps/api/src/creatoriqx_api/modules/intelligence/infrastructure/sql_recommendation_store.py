"""SQLAlchemy adapter for ``RecommendationStore``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.intelligence.domain.recommendation import (
    EvidenceStrength,
    NewRecommendation,
    Recommendation,
    RecommendationStatus,
    RecommendationType,
)
from creatoriqx_api.modules.intelligence.domain.errors import RecommendationNotFoundError
from creatoriqx_api.modules.intelligence.infrastructure.tables import RecommendationRow
from creatoriqx_api.platform.database import session_scope


class SqlRecommendationStore:
    """Persists recommendations under the caller's tenant context."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def save_many(self, recommendations: list[NewRecommendation]) -> list[Recommendation]:
        if not recommendations:
            return []
        async with session_scope(self._factory) as session:
            rows = [
                RecommendationRow(
                    workspace_id=rec.workspace_id,
                    channel_id=rec.channel_id,
                    video_id=rec.video_id,
                    type=rec.type.value,
                    source=rec.source,
                    recommendation=rec.recommendation,
                    evidence=rec.evidence,
                    confidence=rec.confidence,
                    evidence_strength=rec.evidence_strength.value,
                    sample_size=rec.sample_size,
                )
                for rec in recommendations
            ]
            session.add_all(rows)
            await session.flush()
            return [_to_domain(row) for row in rows]

    async def list_for_channel(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> list[Recommendation]:
        async with session_scope(self._factory) as session:
            result = await session.execute(
                select(RecommendationRow)
                .where(
                    RecommendationRow.workspace_id == workspace_id,
                    RecommendationRow.channel_id == channel_id,
                )
                .order_by(RecommendationRow.created_at.desc())
            )
            return [_to_domain(row) for row in result.scalars().all()]

    async def set_status(
        self, *, workspace_id: uuid.UUID, recommendation_id: uuid.UUID, status: str
    ) -> Recommendation:
        async with session_scope(self._factory) as session:
            result = await session.execute(
                select(RecommendationRow).where(
                    RecommendationRow.workspace_id == workspace_id,
                    RecommendationRow.id == recommendation_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise RecommendationNotFoundError()
            row.status = status
            now = datetime.now(UTC)
            if status == RecommendationStatus.ACCEPTED.value:
                row.accepted_at = now
            elif status == RecommendationStatus.DISMISSED.value:
                row.dismissed_at = now
            await session.flush()
            return _to_domain(row)


def _to_domain(row: RecommendationRow) -> Recommendation:
    return Recommendation(
        id=row.id,
        workspace_id=row.workspace_id,
        channel_id=row.channel_id,
        video_id=row.video_id,
        type=RecommendationType(row.type),
        source=row.source,
        recommendation=row.recommendation,
        evidence=row.evidence,
        confidence=row.confidence,
        evidence_strength=EvidenceStrength(row.evidence_strength),
        sample_size=row.sample_size,
        status=RecommendationStatus(row.status),
        created_at=row.created_at,
        accepted_at=row.accepted_at,
        dismissed_at=row.dismissed_at,
    )

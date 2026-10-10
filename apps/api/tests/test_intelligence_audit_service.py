"""Tests for ``ChannelAuditService`` (spec §4 feature #2, #21)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from creatoriqx_api.modules.intelligence.application.audit_service import ChannelAuditService
from creatoriqx_api.modules.intelligence.domain.audit import AuditVideo
from creatoriqx_api.modules.intelligence.domain.recommendation import (
    NewRecommendation,
    Recommendation,
    RecommendationStatus,
    RecommendationType,
)

_WORKSPACE = uuid.uuid4()
_CHANNEL = uuid.uuid4()


@dataclass
class FakeVideoReader:
    videos: list[AuditVideo] = field(default_factory=list)

    async def list_videos(self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID) -> list[AuditVideo]:
        return self.videos


@dataclass
class FakeRecommendationStore:
    saved: list[NewRecommendation] = field(default_factory=list)

    async def save_many(self, recommendations: list[NewRecommendation]) -> list[Recommendation]:
        self.saved.extend(recommendations)
        now = datetime.now(UTC)
        return [
            Recommendation(
                id=uuid.uuid4(),
                workspace_id=rec.workspace_id,
                channel_id=rec.channel_id,
                video_id=rec.video_id,
                type=rec.type,
                source=rec.source,
                recommendation=rec.recommendation,
                evidence=rec.evidence,
                confidence=rec.confidence,
                evidence_strength=rec.evidence_strength,
                sample_size=rec.sample_size,
                status=RecommendationStatus.OPEN,
                created_at=now,
                accepted_at=None,
                dismissed_at=None,
            )
            for rec in recommendations
        ]

    async def list_for_channel(self, **kwargs: object) -> list[Recommendation]:
        raise NotImplementedError

    async def set_status(self, **kwargs: object) -> Recommendation:
        raise NotImplementedError


class TestChannelAuditService:
    async def test_run_persists_one_recommendation_per_finding(self) -> None:
        video_reader = FakeVideoReader(
            videos=[
                AuditVideo(
                    youtube_video_id="v1",
                    title="A video",
                    published_at=datetime.now(UTC),
                    view_count=1000,
                    like_count=50,
                    comment_count=10,
                )
            ]
        )
        store = FakeRecommendationStore()
        service = ChannelAuditService(video_reader=video_reader, recommendation_store=store)

        recommendations = await service.run(workspace_id=_WORKSPACE, channel_id=_CHANNEL)

        assert len(recommendations) >= 1
        assert len(store.saved) == len(recommendations)
        for rec in store.saved:
            assert rec.workspace_id == _WORKSPACE
            assert rec.channel_id == _CHANNEL
            assert rec.evidence

    async def test_no_videos_still_produces_a_recommendation(self) -> None:
        service = ChannelAuditService(
            video_reader=FakeVideoReader(videos=[]), recommendation_store=FakeRecommendationStore()
        )
        recommendations = await service.run(workspace_id=_WORKSPACE, channel_id=_CHANNEL)
        assert len(recommendations) == 1
        assert recommendations[0].type == RecommendationType.CHANNEL_HEALTH

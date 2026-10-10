"""Runs a channel audit and persists its findings as recommendations.

Reads the channel's videos through ``ChannelVideoReader`` (the youtube
module's own public interface, never its tables directly - spec §3 module
rule), runs the pure domain logic in ``intelligence.domain.audit``, and
writes one ``NewRecommendation`` per finding.
"""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.intelligence.application.ports import (
    ChannelVideoReader,
    RecommendationStore,
)
from creatoriqx_api.modules.intelligence.domain.audit import AuditFinding, run_audit
from creatoriqx_api.modules.intelligence.domain.recommendation import (
    NewRecommendation,
    Recommendation,
    RecommendationType,
)

_FINDING_TYPE: dict[str, RecommendationType] = {
    "health_score": RecommendationType.CHANNEL_HEALTH,
    "best_video": RecommendationType.CHANNEL_HEALTH,
    "worst_video": RecommendationType.CHANNEL_HEALTH,
    "upload_gap": RecommendationType.CONTENT_IDEA,
    "quick_win": RecommendationType.QUICK_WIN,
}


class ChannelAuditService:
    """Orchestrates one audit run for a channel."""

    def __init__(
        self, *, video_reader: ChannelVideoReader, recommendation_store: RecommendationStore
    ) -> None:
        self._video_reader = video_reader
        self._recommendation_store = recommendation_store

    async def run(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> list[Recommendation]:
        videos = await self._video_reader.list_videos(
            workspace_id=workspace_id, channel_id=channel_id
        )
        result = run_audit(videos)
        new_recommendations = [
            _to_new_recommendation(finding, workspace_id=workspace_id, channel_id=channel_id)
            for finding in result.findings
        ]
        return await self._recommendation_store.save_many(new_recommendations)


def _to_new_recommendation(
    finding: AuditFinding, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
) -> NewRecommendation:
    return NewRecommendation(
        workspace_id=workspace_id,
        channel_id=channel_id,
        video_id=None,
        type=_FINDING_TYPE.get(finding.kind, RecommendationType.CHANNEL_HEALTH),
        source="intelligence.audit",
        recommendation=finding.summary,
        evidence=finding.evidence,
        confidence=finding.confidence,
        evidence_strength=finding.evidence_strength,
        sample_size=finding.sample_size,
    )

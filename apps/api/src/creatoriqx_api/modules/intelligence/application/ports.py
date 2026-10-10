"""Ports the intelligence application layer depends on."""

from __future__ import annotations

import uuid
from typing import Protocol

from creatoriqx_api.modules.intelligence.domain.audit import AuditVideo
from creatoriqx_api.modules.intelligence.domain.recommendation import (
    NewRecommendation,
    Recommendation,
)


class ChannelVideoReader(Protocol):
    """Reads a channel's videos - intelligence never touches youtube's tables
    directly (spec §3 module rule: consume another module only through its
    own public interface).
    """

    async def list_videos(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> list[AuditVideo]:
        """Every known video for this channel, in whatever order the reader prefers."""


class RecommendationStore(Protocol):
    """Persists and lists recommendations (spec §7 ``recommendations``)."""

    async def save_many(self, recommendations: list[NewRecommendation]) -> list[Recommendation]:
        """Persist each as a new, open recommendation."""

    async def list_for_channel(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> list[Recommendation]:
        """Every recommendation for this channel, most recent first."""

    async def set_status(
        self, *, workspace_id: uuid.UUID, recommendation_id: uuid.UUID, status: str
    ) -> Recommendation:
        """Mark a recommendation accepted or dismissed (spec §4 feature #21)."""

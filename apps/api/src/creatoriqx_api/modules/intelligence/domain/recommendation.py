"""The shared recommendation model (spec §4 feature #21, §7 ``recommendations``).

Every AI-ish suggestion in the product - audit findings, SEO ideas, retention
warnings - is one of these, so the UI renders them consistently and every
module writes evidence the same way. Pure data: no SQL, no HTTP.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime


class RecommendationType(enum.StrEnum):
    """Spec §7's listed types; audit (Phase 1A) uses the first four."""

    RETENTION_WARNING = "RETENTION_WARNING"
    THUMBNAIL_RECOMMENDATION = "THUMBNAIL_RECOMMENDATION"
    SEO_RECOMMENDATION = "SEO_RECOMMENDATION"
    CONTENT_IDEA = "CONTENT_IDEA"
    PUBLISH_TIME_RECOMMENDATION = "PUBLISH_TIME_RECOMMENDATION"
    SCRIPT_HOOK_WARNING = "SCRIPT_HOOK_WARNING"
    CHANNEL_HEALTH = "CHANNEL_HEALTH"
    QUICK_WIN = "QUICK_WIN"


class EvidenceStrength(enum.StrEnum):
    """Independent of confidence: how much and how good the underlying data is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(enum.StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class NewRecommendation:
    """A recommendation as a module produces it, before it has an id."""

    workspace_id: uuid.UUID
    channel_id: uuid.UUID | None
    video_id: uuid.UUID | None
    type: RecommendationType
    source: str
    recommendation: str
    evidence: str
    confidence: float
    evidence_strength: EvidenceStrength
    sample_size: int


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A recommendation as persisted and returned to the API layer."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    channel_id: uuid.UUID | None
    video_id: uuid.UUID | None
    type: RecommendationType
    source: str
    recommendation: str
    evidence: str
    confidence: float
    evidence_strength: EvidenceStrength
    sample_size: int
    status: RecommendationStatus
    created_at: datetime
    accepted_at: datetime | None
    dismissed_at: datetime | None

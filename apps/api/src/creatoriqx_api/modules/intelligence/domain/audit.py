"""Pure channel-audit logic (spec §4 feature #2): no SQL, no HTTP.

Every finding here becomes one ``NewRecommendation`` with evidence attached
(spec acceptance criterion: "every finding shows evidence and a suggested
action"). The health score and every finding are honest estimates from the
channel's own data, never a guarantee (spec §1 "Honesty" non-negotiable).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from creatoriqx_api.modules.intelligence.domain.recommendation import EvidenceStrength

# Below this many videos, per-video comparisons (best/worst, gaps) are too
# noisy to be worth showing; the health score itself still computes, just
# with a lower evidence_strength (small-sample honesty, spec §4 feature #11).
_MIN_VIDEOS_FOR_COMPARISONS = 3


@dataclass(frozen=True, slots=True)
class AuditVideo:
    """The slice of a channel_videos row the audit logic needs."""

    youtube_video_id: str
    title: str
    published_at: datetime
    view_count: int | None
    like_count: int | None
    comment_count: int | None


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """One evidence-backed observation, ready to become a recommendation."""

    kind: str  # "best_video" | "worst_video" | "upload_gap" | "quick_win" | "health_score"
    summary: str
    evidence: str
    confidence: float
    evidence_strength: EvidenceStrength
    sample_size: int


@dataclass(frozen=True, slots=True)
class ChannelAuditResult:
    health_score: float  # 0-100
    findings: list[AuditFinding]


def run_audit(videos: list[AuditVideo]) -> ChannelAuditResult:
    """Compute a health score and a list of evidence-backed findings."""
    if not videos:
        return ChannelAuditResult(
            health_score=0.0,
            findings=[
                AuditFinding(
                    kind="health_score",
                    summary="No videos ingested yet",
                    evidence="The channel's uploads playlist returned no videos.",
                    confidence=1.0,
                    evidence_strength=EvidenceStrength.LOW,
                    sample_size=0,
                )
            ],
        )

    findings: list[AuditFinding] = []
    sample_size = len(videos)
    strength = (
        EvidenceStrength.HIGH
        if sample_size >= 20
        else EvidenceStrength.MEDIUM
        if sample_size >= _MIN_VIDEOS_FOR_COMPARISONS
        else EvidenceStrength.LOW
    )

    views = [v.view_count for v in videos if v.view_count is not None]
    health_score = _health_score(views)
    findings.append(
        AuditFinding(
            kind="health_score",
            summary=f"Channel health score: {health_score:.0f}/100",
            evidence=(
                f"Based on {sample_size} videos' view counts "
                f"(median {statistics.median(views):.0f} views)"
                if views
                else f"Based on {sample_size} videos (no view data available)"
            ),
            confidence=0.7 if sample_size >= _MIN_VIDEOS_FOR_COMPARISONS else 0.4,
            evidence_strength=strength,
            sample_size=sample_size,
        )
    )

    if sample_size >= _MIN_VIDEOS_FOR_COMPARISONS and views:
        findings.extend(_best_worst_findings(videos, strength))
        findings.extend(_upload_gap_findings(videos, strength))
        findings.extend(_quick_win_findings(videos, strength))

    return ChannelAuditResult(health_score=health_score, findings=findings)


def _health_score(views: list[int]) -> float:
    """A simple, explainable 0-100 score: consistency matters as much as reach.

    Honest-by-design: this rewards a channel that performs evenly across its
    catalog, not one with a single viral outlier, and it is explicitly an
    estimate (spec §1: never promise virality or guaranteed reach).
    """
    if not views:
        return 50.0  # no data: a neutral score, not a penalty
    median_views = statistics.median(views)
    if median_views <= 0:
        return 0.0
    if len(views) < 2:
        return min(100.0, 50.0 + (median_views / 1000))
    # Coefficient of variation: lower spread (relative to the median) scores
    # higher consistency. Clamped so one outlier can't dominate the score.
    mean_views = statistics.mean(views)
    stdev_views = statistics.pstdev(views)
    consistency = 1.0 - min(1.0, (stdev_views / mean_views) if mean_views else 1.0)
    reach_component = min(50.0, (median_views / 1000) * 10)
    consistency_component = consistency * 50.0
    return round(min(100.0, reach_component + consistency_component), 1)


def _best_worst_findings(
    videos: list[AuditVideo], strength: EvidenceStrength
) -> list[AuditFinding]:
    ranked = sorted(
        (v for v in videos if v.view_count is not None), key=lambda v: v.view_count or 0
    )
    if len(ranked) < _MIN_VIDEOS_FOR_COMPARISONS:
        return []
    worst, best = ranked[0], ranked[-1]
    return [
        AuditFinding(
            kind="best_video",
            summary=f'Best performer: "{best.title}"',
            evidence=f"{best.view_count} views, published {best.published_at.date()}",
            confidence=0.9,
            evidence_strength=strength,
            sample_size=len(ranked),
        ),
        AuditFinding(
            kind="worst_video",
            summary=f'Lowest performer: "{worst.title}"',
            evidence=f"{worst.view_count} views, published {worst.published_at.date()}",
            confidence=0.9,
            evidence_strength=strength,
            sample_size=len(ranked),
        ),
    ]


def _upload_gap_findings(
    videos: list[AuditVideo], strength: EvidenceStrength
) -> list[AuditFinding]:
    ordered = sorted(videos, key=lambda v: v.published_at)
    gaps = [
        (ordered[i + 1].published_at - ordered[i].published_at).days
        for i in range(len(ordered) - 1)
    ]
    if not gaps:
        return []
    longest_gap = max(gaps)
    if longest_gap < 30:
        return []
    gap_index = gaps.index(longest_gap)
    return [
        AuditFinding(
            kind="upload_gap",
            summary=f"A {longest_gap}-day gap between uploads was found",
            evidence=(
                f'Between "{ordered[gap_index].title}" '
                f"({ordered[gap_index].published_at.date()}) and "
                f'"{ordered[gap_index + 1].title}" '
                f"({ordered[gap_index + 1].published_at.date()})"
            ),
            confidence=1.0,
            evidence_strength=strength,
            sample_size=len(ordered),
        )
    ]


def _quick_win_findings(videos: list[AuditVideo], strength: EvidenceStrength) -> list[AuditFinding]:
    """Videos with real views but a comment count of zero: a cheap, visible fix
    (ask a question in a pinned comment, reply to existing engagement) that
    doesn't require new content - a "quick win" per spec feature #2.
    """
    candidates = [v for v in videos if (v.view_count or 0) > 100 and (v.comment_count or 0) == 0]
    if not candidates:
        return []
    candidate = max(candidates, key=lambda v: v.view_count or 0)
    return [
        AuditFinding(
            kind="quick_win",
            summary=f'"{candidate.title}" has views but no comments',
            evidence=(
                f"{candidate.view_count} views, 0 comments - consider a pinned "
                "question to start a conversation"
            ),
            confidence=0.6,
            evidence_strength=strength,
            sample_size=len(videos),
        )
    ]

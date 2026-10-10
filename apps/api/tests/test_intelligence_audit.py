"""Tests for the pure channel-audit domain logic (spec §4 feature #2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from creatoriqx_api.modules.intelligence.domain.audit import AuditVideo, run_audit
from creatoriqx_api.modules.intelligence.domain.recommendation import EvidenceStrength

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _video(
    video_id: str,
    *,
    days_after_base: int = 0,
    views: int | None = 1000,
    likes: int | None = 50,
    comments: int | None = 10,
    title: str | None = None,
) -> AuditVideo:
    return AuditVideo(
        youtube_video_id=video_id,
        title=title or f"Video {video_id}",
        published_at=_BASE + timedelta(days=days_after_base),
        view_count=views,
        like_count=likes,
        comment_count=comments,
    )


class TestEmptyChannel:
    def test_no_videos_returns_zero_score_and_one_finding(self) -> None:
        result = run_audit([])
        assert result.health_score == 0.0
        assert len(result.findings) == 1
        assert result.findings[0].kind == "health_score"
        assert result.findings[0].sample_size == 0


class TestSmallSample:
    def test_below_min_sample_skips_comparisons(self) -> None:
        videos = [_video("a", days_after_base=0), _video("b", days_after_base=1)]
        result = run_audit(videos)
        kinds = {f.kind for f in result.findings}
        assert kinds == {"health_score"}
        assert result.findings[0].evidence_strength == EvidenceStrength.LOW

    def test_health_score_present_even_with_one_video(self) -> None:
        result = run_audit([_video("solo")])
        assert len(result.findings) == 1
        assert 0.0 <= result.health_score <= 100.0


class TestEveryFindingHasEvidence:
    def test_all_findings_carry_non_empty_evidence(self) -> None:
        videos = [
            _video("a", days_after_base=0, views=100),
            _video("b", days_after_base=1, views=5000),
            _video("c", days_after_base=50, views=1000, comments=0),
        ]
        result = run_audit(videos)
        assert len(result.findings) > 0
        for finding in result.findings:
            assert finding.evidence
            assert finding.summary
            assert 0.0 <= finding.confidence <= 1.0


class TestBestAndWorstVideo:
    def test_identifies_best_and_worst_by_views(self) -> None:
        videos = [
            _video("low", days_after_base=0, views=10, title="Low performer"),
            _video("mid", days_after_base=1, views=500, title="Mid performer"),
            _video("high", days_after_base=2, views=50_000, title="High performer"),
        ]
        result = run_audit(videos)
        best = next(f for f in result.findings if f.kind == "best_video")
        worst = next(f for f in result.findings if f.kind == "worst_video")
        assert "High performer" in best.summary
        assert "Low performer" in worst.summary


class TestUploadGap:
    def test_detects_a_long_gap(self) -> None:
        videos = [
            _video("a", days_after_base=0, title="Before the gap"),
            _video("b", days_after_base=5),
            _video("c", days_after_base=90, title="After the gap"),
        ]
        result = run_audit(videos)
        gaps = [f for f in result.findings if f.kind == "upload_gap"]
        assert len(gaps) == 1
        assert "90" in gaps[0].summary or "85" in gaps[0].summary
        assert "Before the gap" in gaps[0].evidence
        assert "After the gap" in gaps[0].evidence

    def test_no_finding_when_gaps_are_short(self) -> None:
        videos = [
            _video("a", days_after_base=0),
            _video("b", days_after_base=2),
            _video("c", days_after_base=4),
        ]
        result = run_audit(videos)
        assert not [f for f in result.findings if f.kind == "upload_gap"]


class TestQuickWin:
    def test_flags_views_with_zero_comments(self) -> None:
        videos = [
            _video("a", days_after_base=0, views=5000, comments=0, title="Silent hit"),
            _video("b", days_after_base=1, views=200, comments=5),
            _video("c", days_after_base=2, views=300, comments=3),
        ]
        result = run_audit(videos)
        quick_wins = [f for f in result.findings if f.kind == "quick_win"]
        assert len(quick_wins) == 1
        assert "Silent hit" in quick_wins[0].summary

    def test_no_quick_win_when_comments_present(self) -> None:
        videos = [
            _video("a", days_after_base=0, views=5000, comments=10),
            _video("b", days_after_base=1, views=200, comments=5),
            _video("c", days_after_base=2, views=300, comments=3),
        ]
        result = run_audit(videos)
        assert not [f for f in result.findings if f.kind == "quick_win"]


class TestHealthScoreNeverExceedsBounds:
    def test_score_is_within_zero_to_hundred(self) -> None:
        videos = [_video(str(i), days_after_base=i, views=1_000_000) for i in range(20)]
        result = run_audit(videos)
        assert 0.0 <= result.health_score <= 100.0

    def test_consistent_channel_scores_higher_than_erratic_one(self) -> None:
        consistent = [_video(f"c{i}", days_after_base=i, views=1000) for i in range(5)]
        erratic = [
            _video("e0", days_after_base=0, views=10),
            _video("e1", days_after_base=1, views=50_000),
            _video("e2", days_after_base=2, views=20),
            _video("e3", days_after_base=3, views=40_000),
            _video("e4", days_after_base=4, views=15),
        ]
        consistent_score = run_audit(consistent).health_score
        erratic_score = run_audit(erratic).health_score
        assert consistent_score > erratic_score

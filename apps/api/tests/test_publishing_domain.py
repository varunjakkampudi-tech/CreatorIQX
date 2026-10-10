"""Tests for the publishing module's domain layer (spec §3, §4 feature 12/13,
Phase 1D P1D-02).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from creatoriqx_api.modules.content.domain.chapters import Chapter
from creatoriqx_api.modules.planning.domain.video import VideoStatus
from creatoriqx_api.modules.publishing.domain.capability import (
    Capability,
    CapabilityEvidence,
    CapabilityStatus,
    assert_evidence_complete,
    is_evidence_complete,
)
from creatoriqx_api.modules.publishing.domain.drift import (
    has_drift,
    normalize_metadata_for_drift,
)
from creatoriqx_api.modules.publishing.domain.errors import (
    CapabilityEvidenceIncompleteError,
    InvalidSyncTransitionError,
    VideoNotReadyForSnapshotError,
)
from creatoriqx_api.modules.publishing.domain.qa import QaCheckId, QaInput, run_qa_checklist
from creatoriqx_api.modules.publishing.domain.snapshot import assert_video_eligible_for_snapshot
from creatoriqx_api.modules.publishing.domain.sync_state import (
    SyncState,
    assert_sync_transition,
    can_transition_sync_state,
)


def _clean_qa_input(**overrides: object) -> QaInput:
    defaults: dict[str, object] = dict(
        title="A perfectly good title",
        hook="This is a hook that is definitely long enough.",
        description="A full description of the video.",
        tags=("tag-one", "tag-two"),
        chapters=(Chapter(0, "Intro"), Chapter(30, "Middle"), Chapter(90, "End")),
        has_thumbnail=True,
        disclosure_altered=False,
        disclosure_synthetic=False,
        wants_scheduling=False,
        linked_video_privacy_status=None,
        linked_video_has_been_published=None,
    )
    defaults.update(overrides)
    return QaInput(**defaults)  # type: ignore[arg-type]


class TestQaChecklist:
    def test_a_clean_video_passes_every_check(self) -> None:
        result = run_qa_checklist(uuid.uuid4(), _clean_qa_input())
        assert result.passed is True
        assert result.failing_checks == ()

    def test_empty_title_fails_the_title_check(self) -> None:
        result = run_qa_checklist(uuid.uuid4(), _clean_qa_input(title=""))
        assert result.passed is False
        failing_ids = {check.id for check in result.failing_checks}
        assert QaCheckId.TITLE in failing_ids

    def test_short_hook_fails_the_hook_check(self) -> None:
        result = run_qa_checklist(uuid.uuid4(), _clean_qa_input(hook="hi"))
        assert QaCheckId.HOOK in {c.id for c in result.failing_checks}

    def test_empty_description_fails_the_seo_check(self) -> None:
        result = run_qa_checklist(uuid.uuid4(), _clean_qa_input(description=""))
        assert QaCheckId.SEO in {c.id for c in result.failing_checks}

    def test_invalid_chapters_fail_the_chapters_check(self) -> None:
        # Starts at 10s, not 00:00 - violates YouTube's chapter rules.
        bad_chapters = (Chapter(10, "Intro"), Chapter(40, "Mid"), Chapter(70, "End"))
        result = run_qa_checklist(uuid.uuid4(), _clean_qa_input(chapters=bad_chapters))
        assert QaCheckId.CHAPTERS in {c.id for c in result.failing_checks}

    def test_missing_chapters_is_allowed(self) -> None:
        result = run_qa_checklist(uuid.uuid4(), _clean_qa_input(chapters=None))
        assert QaCheckId.CHAPTERS not in {c.id for c in result.failing_checks}

    def test_missing_thumbnail_is_advisory_only(self) -> None:
        result = run_qa_checklist(uuid.uuid4(), _clean_qa_input(has_thumbnail=False))
        assert result.passed is True

    def test_scheduling_requested_without_a_link_fails_the_schedule_check(self) -> None:
        result = run_qa_checklist(uuid.uuid4(), _clean_qa_input(wants_scheduling=True))
        assert QaCheckId.SCHEDULE in {c.id for c in result.failing_checks}

    def test_scheduling_on_a_public_linked_video_fails_the_schedule_check(self) -> None:
        result = run_qa_checklist(
            uuid.uuid4(),
            _clean_qa_input(
                wants_scheduling=True,
                linked_video_privacy_status="public",
                linked_video_has_been_published=False,
            ),
        )
        assert QaCheckId.SCHEDULE in {c.id for c in result.failing_checks}

    def test_scheduling_on_an_already_published_video_fails_the_schedule_check(self) -> None:
        result = run_qa_checklist(
            uuid.uuid4(),
            _clean_qa_input(
                wants_scheduling=True,
                linked_video_privacy_status="private",
                linked_video_has_been_published=True,
            ),
        )
        assert QaCheckId.SCHEDULE in {c.id for c in result.failing_checks}

    def test_scheduling_on_a_private_unpublished_video_passes(self) -> None:
        result = run_qa_checklist(
            uuid.uuid4(),
            _clean_qa_input(
                wants_scheduling=True,
                linked_video_privacy_status="private",
                linked_video_has_been_published=False,
            ),
        )
        assert QaCheckId.SCHEDULE not in {c.id for c in result.failing_checks}


class TestSnapshotEligibility:
    def test_in_review_is_eligible(self) -> None:
        assert_video_eligible_for_snapshot(VideoStatus.IN_REVIEW)  # does not raise

    @pytest.mark.parametrize(
        "status",
        [
            VideoStatus.IDEA,
            VideoStatus.DRAFTING,
            VideoStatus.QA,
            VideoStatus.APPROVED,
            VideoStatus.PUBLISHED,
        ],
    )
    def test_other_statuses_are_refused(self, status: VideoStatus) -> None:
        with pytest.raises(VideoNotReadyForSnapshotError):
            assert_video_eligible_for_snapshot(status)


class TestCapabilityEvidence:
    def _evidence(self, **overrides: object) -> CapabilityEvidence:
        defaults: dict[str, object] = dict(
            capability=Capability.METADATA_UPDATE,
            status=CapabilityStatus.AVAILABLE,
            verified_on=date(2026, 10, 1),
            source_url="https://developers.google.com/youtube/v3/docs/videos/update",
            required_scopes=("https://www.googleapis.com/auth/youtube",),
            verification_notes="Verified against current docs.",
            updated_at=datetime.now(UTC),
        )
        defaults.update(overrides)
        return CapabilityEvidence(**defaults)  # type: ignore[arg-type]

    def test_complete_evidence_passes(self) -> None:
        assert is_evidence_complete(self._evidence()) is True
        assert_evidence_complete(self._evidence())  # does not raise

    @pytest.mark.parametrize(
        "field_name",
        ["verified_on", "source_url", "required_scopes", "verification_notes"],
    )
    def test_missing_any_field_fails(self, field_name: str) -> None:
        missing_value = None if field_name != "required_scopes" else ()
        evidence = self._evidence(**{field_name: missing_value})
        assert is_evidence_complete(evidence) is False
        with pytest.raises(CapabilityEvidenceIncompleteError):
            assert_evidence_complete(evidence)


class TestDriftNormalization:
    def test_whitespace_differences_do_not_count_as_drift(self) -> None:
        local = normalize_metadata_for_drift(
            title="My  Video", description="Line one.\nLine two.", tags=("a",), category="22"
        )
        remote = normalize_metadata_for_drift(
            title="My Video", description="Line one. Line two.", tags=("a",), category="22"
        )
        assert has_drift(local, remote) is False

    def test_tag_casing_differences_do_not_count_as_drift(self) -> None:
        local = normalize_metadata_for_drift(
            title="T", description="D", tags=("Tutorial", "howto"), category=None
        )
        remote = normalize_metadata_for_drift(
            title="T", description="D", tags=("tutorial", "HOWTO"), category=None
        )
        assert has_drift(local, remote) is False

    def test_html_entity_differences_do_not_count_as_drift(self) -> None:
        local = normalize_metadata_for_drift(
            title="Q&amp;A session", description="D", tags=(), category=None
        )
        remote = normalize_metadata_for_drift(
            title="Q&A session", description="D", tags=(), category=None
        )
        assert has_drift(local, remote) is False

    def test_a_real_content_difference_counts_as_drift(self) -> None:
        local = normalize_metadata_for_drift(
            title="Original Title", description="D", tags=(), category=None
        )
        remote = normalize_metadata_for_drift(
            title="Changed Title", description="D", tags=(), category=None
        )
        assert has_drift(local, remote) is True


class TestSyncStateTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (SyncState.NOT_LINKED, SyncState.LINKED),
            (SyncState.LINKED, SyncState.PENDING_SYNC),
            (SyncState.PENDING_SYNC, SyncState.SYNCED),
            (SyncState.PENDING_SYNC, SyncState.SYNC_FAILED),
            (SyncState.SYNCED, SyncState.DRIFT_DETECTED),
            (SyncState.DRIFT_DETECTED, SyncState.SYNCED),
        ],
    )
    def test_allowed_edges(self, current: SyncState, target: SyncState) -> None:
        assert can_transition_sync_state(current, target) is True
        assert_sync_transition(current, target)  # does not raise

    def test_cannot_skip_straight_from_not_linked_to_synced(self) -> None:
        assert can_transition_sync_state(SyncState.NOT_LINKED, SyncState.SYNCED) is False
        with pytest.raises(InvalidSyncTransitionError):
            assert_sync_transition(SyncState.NOT_LINKED, SyncState.SYNCED)

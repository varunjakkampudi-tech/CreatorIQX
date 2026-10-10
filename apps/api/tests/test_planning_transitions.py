"""Tests for the video lifecycle state machine (spec §3)."""

from __future__ import annotations

import pytest

from creatoriqx_api.modules.planning.domain.errors import InvalidTransitionError
from creatoriqx_api.modules.planning.domain.transitions import assert_transition, can_transition
from creatoriqx_api.modules.planning.domain.video import ALLOWED_TRANSITIONS, VideoStatus


class TestCanTransition:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (VideoStatus.IDEA, VideoStatus.PLANNED),
            (VideoStatus.PLANNED, VideoStatus.DRAFTING),
            (VideoStatus.DRAFTING, VideoStatus.QA),
            (VideoStatus.QA, VideoStatus.DRAFTING),
            (VideoStatus.QA, VideoStatus.IN_REVIEW),
            (VideoStatus.IN_REVIEW, VideoStatus.APPROVED),
            (VideoStatus.IN_REVIEW, VideoStatus.REJECTED),
            (VideoStatus.APPROVED, VideoStatus.SCHEDULED),
            (VideoStatus.APPROVED, VideoStatus.IN_REVIEW),
            (VideoStatus.SCHEDULED, VideoStatus.PUBLISHED),
            (VideoStatus.PUBLISHED, VideoStatus.ANALYZED),
            (VideoStatus.REJECTED, VideoStatus.DRAFTING),
        ],
    )
    def test_allowed_edges(self, current: VideoStatus, target: VideoStatus) -> None:
        assert can_transition(current, target) is True

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (VideoStatus.IDEA, VideoStatus.DRAFTING),  # skips planned
            (VideoStatus.IDEA, VideoStatus.PUBLISHED),  # skips the whole pipeline
            (VideoStatus.PUBLISHED, VideoStatus.DRAFTING),  # cannot un-publish backwards
            (VideoStatus.ANALYZED, VideoStatus.PUBLISHED),  # terminal except archive
            (VideoStatus.ARCHIVED, VideoStatus.IDEA),  # archive is a dead end
            (VideoStatus.APPROVED, VideoStatus.PLANNED),  # cannot jump backwards past review
        ],
    )
    def test_disallowed_edges(self, current: VideoStatus, target: VideoStatus) -> None:
        assert can_transition(current, target) is False

    def test_every_working_state_can_archive(self) -> None:
        for status in VideoStatus:
            if status is VideoStatus.ARCHIVED:
                continue
            assert can_transition(status, VideoStatus.ARCHIVED) is True

    def test_every_status_has_an_edge_set(self) -> None:
        # A status missing from the map would silently become "no transitions
        # allowed" rather than failing loudly - this pins every status down.
        assert set(ALLOWED_TRANSITIONS) == set(VideoStatus)


class TestAssertTransition:
    def test_allowed_transition_does_not_raise(self) -> None:
        assert_transition(VideoStatus.IDEA, VideoStatus.PLANNED)

    def test_disallowed_transition_raises_with_both_statuses(self) -> None:
        with pytest.raises(InvalidTransitionError) as exc_info:
            assert_transition(VideoStatus.IDEA, VideoStatus.PUBLISHED)
        assert exc_info.value.current is VideoStatus.IDEA
        assert exc_info.value.target is VideoStatus.PUBLISHED

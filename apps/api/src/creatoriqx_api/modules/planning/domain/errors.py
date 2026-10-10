"""Typed domain errors for the planning module (spec §8, §12: no bare exceptions)."""

from __future__ import annotations

from creatoriqx_api.modules.planning.domain.video import VideoStatus
from creatoriqx_api.platform.errors import DomainError


class PlanNotFoundError(DomainError):
    """No plan with the given id exists in this workspace."""

    status = 404
    title = "Plan not found"
    code = "plan-not-found"


class PlanAlreadyPromotedError(DomainError):
    """The plan already has a video; promotion is one-way (spec feature 4)."""

    status = 409
    title = "This plan has already become a video"
    code = "plan-already-promoted"


class VideoNotFoundError(DomainError):
    """No video with the given id exists in this workspace."""

    status = 404
    title = "Video not found"
    code = "video-not-found"


class InvalidTransitionError(DomainError):
    """``current -> target`` is not an edge of the lifecycle graph."""

    status = 409
    title = "This status change is not allowed from the video's current status"
    code = "video-invalid-transition"

    def __init__(self, *, current: VideoStatus, target: VideoStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"cannot transition from {current.value!r} to {target.value!r}")

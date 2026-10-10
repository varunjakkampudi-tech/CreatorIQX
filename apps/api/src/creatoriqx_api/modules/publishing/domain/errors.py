"""Typed domain errors for the publishing module (spec §8, §12: no bare exceptions)."""

from __future__ import annotations

from creatoriqx_api.platform.errors import DomainError


class QaNotPassedError(DomainError):
    """Approval was attempted before QA passed on the video's current artifacts."""

    status = 422
    title = "Pre-publish QA has not passed for this video"
    code = "qa-not-passed"

    def __init__(self, failing_checks: list[str]) -> None:
        self.failing_checks = failing_checks
        super().__init__("; ".join(failing_checks))


class VideoNotReadyForSnapshotError(DomainError):
    """The video's lifecycle status does not permit building a publish snapshot."""

    status = 409
    title = "This video cannot be approved from its current status"
    code = "video-not-ready-for-snapshot"


class PublishSnapshotNotFoundError(DomainError):
    status = 404
    title = "Publish snapshot not found"
    code = "publish-snapshot-not-found"


class CapabilityEvidenceIncompleteError(DomainError):
    """A capability cannot be marked ``available`` without full recorded evidence
    (spec §3: "Refuse to enable any write capability without recorded verification
    evidence.").
    """

    status = 422
    title = "This capability is missing required verification evidence"
    code = "capability-evidence-incomplete"


class CapabilityNotFoundError(DomainError):
    status = 404
    title = "Capability not found"
    code = "capability-not-found"


class CapabilityUnavailableError(DomainError):
    """The capability is not ``available`` and the caller required it to be."""

    status = 409
    title = "This capability is not available"
    code = "capability-unavailable"


class VideoLinkNotFoundError(DomainError):
    status = 404
    title = "This video is not linked to a YouTube video"
    code = "youtube-video-link-not-found"


class VideoAlreadyLinkedToAnotherChannelError(DomainError):
    """The target YouTube video id belongs to a channel other than the one requested,
    or is already linked from another workspace (spec §3: uniqueness on
    ``(workspace_id, youtube_video_id)``).
    """

    status = 409
    title = "This YouTube video belongs to a different channel or is already linked"
    code = "youtube-video-link-conflict"


class InvalidSyncTransitionError(DomainError):
    """``current -> target`` is not an edge of the sync-state graph."""

    status = 409
    title = "This sync-state change is not allowed from the link's current state"
    code = "youtube-sync-invalid-transition"


class DriftResolutionModeRequiredError(DomainError):
    """Drift must be resolved with one of the three explicit modes (spec §3: "always
    explicit"), never implicitly.
    """

    status = 422
    title = "Drift resolution requires adopt_remote, overwrite_remote, or ignore"
    code = "youtube-drift-resolution-mode-required"

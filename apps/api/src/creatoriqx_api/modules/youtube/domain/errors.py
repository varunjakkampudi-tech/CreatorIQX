"""Typed errors for the youtube module (spec §8)."""

from __future__ import annotations

from creatoriqx_api.platform.errors import DomainError


class YouTubeOAuthError(DomainError):
    """Google's authorization or token endpoint returned an error, or a state check failed."""

    status = 400
    title = "YouTube connection could not be completed"
    code = "youtube-oauth-error"


class YouTubeOAuthStateMismatchError(YouTubeOAuthError):
    """No connect flow in progress, or the state parameter does not match it."""

    title = "No YouTube connection in progress, or it has expired"
    code = "youtube-oauth-state-mismatch"


class ChannelNotConnectedError(DomainError):
    """The requested channel has no active connection in this workspace."""

    status = 404
    title = "This channel is not connected"
    code = "channel-not-connected"


class YouTubeApiError(DomainError):
    """The YouTube Data API returned an error response."""

    status = 502
    title = "YouTube API request failed"
    code = "youtube-api-error"


class QuotaExhaustedError(DomainError):
    """The workspace has used its daily YouTube API quota allowance."""

    status = 429
    title = "Daily YouTube API quota exhausted for this workspace"
    code = "youtube-quota-exhausted"

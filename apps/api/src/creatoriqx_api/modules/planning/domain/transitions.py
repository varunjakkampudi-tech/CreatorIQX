"""Transition enforcement for the video lifecycle (spec §3: "allowed transitions
enforced in the domain layer").
"""

from __future__ import annotations

from creatoriqx_api.modules.planning.domain.errors import InvalidTransitionError
from creatoriqx_api.modules.planning.domain.video import ALLOWED_TRANSITIONS, VideoStatus


def can_transition(current: VideoStatus, target: VideoStatus) -> bool:
    """Whether ``current -> target`` is one edge of the lifecycle graph."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: VideoStatus, target: VideoStatus) -> None:
    """Raise :class:`InvalidTransitionError` unless ``current -> target`` is allowed."""
    if not can_transition(current, target):
        raise InvalidTransitionError(current=current, target=target)

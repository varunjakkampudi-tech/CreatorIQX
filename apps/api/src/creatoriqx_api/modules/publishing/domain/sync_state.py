"""YouTube synchronization state (spec §3 "YouTube synchronization state
(separate from the video state machine)"). This tracks the *link* between a
local video and a real YouTube video, not the video's own lifecycle status
(``planning.domain.video.VideoStatus``) - the two state machines are
deliberately independent.
"""

from __future__ import annotations

import enum


class SyncState(enum.StrEnum):
    """One node of the sync-link graph (spec §3)."""

    NOT_LINKED = "not_linked"
    LINKED = "linked"
    PENDING_SYNC = "pending_sync"
    SYNCED = "synced"
    DRIFT_DETECTED = "drift_detected"
    SYNC_FAILED = "sync_failed"


ALLOWED_SYNC_TRANSITIONS: dict[SyncState, frozenset[SyncState]] = {
    SyncState.NOT_LINKED: frozenset({SyncState.LINKED}),
    SyncState.LINKED: frozenset({SyncState.PENDING_SYNC}),
    SyncState.PENDING_SYNC: frozenset({SyncState.SYNCED, SyncState.SYNC_FAILED}),
    SyncState.SYNCED: frozenset({SyncState.PENDING_SYNC, SyncState.DRIFT_DETECTED}),
    SyncState.DRIFT_DETECTED: frozenset({SyncState.PENDING_SYNC, SyncState.SYNCED}),
    SyncState.SYNC_FAILED: frozenset({SyncState.PENDING_SYNC}),
}


def can_transition_sync_state(current: SyncState, target: SyncState) -> bool:
    return target in ALLOWED_SYNC_TRANSITIONS.get(current, frozenset())


def assert_sync_transition(current: SyncState, target: SyncState) -> None:
    from creatoriqx_api.modules.publishing.domain.errors import InvalidSyncTransitionError

    if not can_transition_sync_state(current, target):
        raise InvalidSyncTransitionError(
            f"cannot move sync state from {current.value!r} to {target.value!r}"
        )

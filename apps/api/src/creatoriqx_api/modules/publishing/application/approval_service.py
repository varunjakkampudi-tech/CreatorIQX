"""Builds and freezes the immutable publish snapshot (spec §3 "Approval gate",
feature 13, ADR 0006).

Approval re-runs the QA checklist against the video's *current* artifacts
immediately before building the snapshot - a stale QA pass can never gate
an approval, since there is no separate "QA record" trusted after the fact
(see ``QaService``'s own docstring).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from creatoriqx_api.modules.content.application.ports import (
    ChapterVersionStore,
    MetadataVersionStore,
    ScriptVersionStore,
)
from creatoriqx_api.modules.content.domain.chapters import ChapterVersion
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion
from creatoriqx_api.modules.content.domain.script import ScriptVersion
from creatoriqx_api.modules.planning.application.ports import VideoStore
from creatoriqx_api.modules.planning.domain.errors import VideoNotFoundError
from creatoriqx_api.modules.planning.domain.video import VideoStatus
from creatoriqx_api.modules.publishing.application.ports import (
    NewPublishSnapshot,
    PublishSnapshotStore,
)
from creatoriqx_api.modules.publishing.application.qa_service import QaService
from creatoriqx_api.modules.publishing.domain.errors import (
    PublishSnapshotNotFoundError,
    QaNotPassedError,
)
from creatoriqx_api.modules.publishing.domain.snapshot import (
    PublishSnapshot,
    assert_video_eligible_for_snapshot,
)


def _current_metadata(versions: list[MetadataVersion]) -> MetadataVersion | None:
    return next((v for v in versions if v.is_current), None)


def _current_script(versions: list[ScriptVersion]) -> ScriptVersion | None:
    return next((v for v in versions if v.is_current), None)


def _current_chapters(versions: list[ChapterVersion]) -> ChapterVersion | None:
    return next((v for v in versions if v.is_current), None)


class ApprovalService:
    def __init__(
        self,
        *,
        qa_service: QaService,
        script_store: ScriptVersionStore,
        metadata_store: MetadataVersionStore,
        chapter_store: ChapterVersionStore,
        snapshot_store: PublishSnapshotStore,
        video_store: VideoStore,
    ) -> None:
        self._qa = qa_service
        self._scripts = script_store
        self._metadata = metadata_store
        self._chapters = chapter_store
        self._snapshots = snapshot_store
        self._videos = video_store

    async def approve(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        scheduled_at: datetime | None = None,
        wants_scheduling: bool = False,
        correlation_id: str | None = None,
    ) -> PublishSnapshot:
        video = await self._videos.get(workspace_id=workspace_id, video_id=video_id)
        if video is None:
            raise VideoNotFoundError()

        # Idempotent re-approval: calling this twice with no edit in between
        # (video still APPROVED, nothing moved it back to in_review) returns
        # the same snapshot rather than erroring or building a duplicate one.
        if video.status == VideoStatus.APPROVED:
            existing = await self._snapshots.get_latest_for_video(
                workspace_id=workspace_id, video_id=video_id
            )
            if existing is not None:
                return existing
            raise PublishSnapshotNotFoundError("video is approved but has no snapshot on record")

        assert_video_eligible_for_snapshot(video.status)

        qa_result = await self._qa.run(
            workspace_id=workspace_id, video_id=video_id, wants_scheduling=wants_scheduling
        )
        if not qa_result.passed:
            raise QaNotPassedError(
                [
                    f"{check.id.value}: {'; '.join(check.reasons)}"
                    for check in qa_result.failing_checks
                ]
            )

        metadata = _current_metadata(
            await self._metadata.list_for_video(workspace_id=workspace_id, video_id=video_id)
        )
        script = _current_script(
            await self._scripts.list_for_video(workspace_id=workspace_id, video_id=video_id)
        )
        chapters = _current_chapters(
            await self._chapters.list_for_video(workspace_id=workspace_id, video_id=video_id)
        )
        # QA already required a title/description/hook, which only exist on a
        # real metadata/script version, so both are guaranteed non-None here -
        # raised, not asserted, since assertions can be stripped at runtime.
        if metadata is None or script is None:
            raise QaNotPassedError(["metadata or script version disappeared mid-approval"])

        snapshot = await self._snapshots.create(
            NewPublishSnapshot(
                workspace_id=workspace_id,
                video_id=video_id,
                script_version_id=script.id,
                metadata_version_id=metadata.id,
                chapter_version_id=chapters.id if chapters else None,
                thumbnail_variant_id=None,
                disclosure_altered=metadata.disclosure_altered,
                disclosure_synthetic=metadata.disclosure_synthetic,
                scheduled_at=scheduled_at,
                approved_by=actor_user_id,
            )
        )

        await self._videos.update_status(
            workspace_id=workspace_id,
            video_id=video_id,
            status=VideoStatus.APPROVED,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        return snapshot

    async def get_latest_snapshot(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> PublishSnapshot | None:
        """The video's most recently approved snapshot, or ``None`` if it has never
        been approved. A pure read, kept on the service (rather than exposing the
        store to the API layer directly) for the same reason every other route in
        this codebase depends on a service, not a store.
        """
        return await self._snapshots.get_latest_for_video(
            workspace_id=workspace_id, video_id=video_id
        )

    async def invalidate_if_approved(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        correlation_id: str | None = None,
    ) -> None:
        """Approval invalidation (spec §3): call this after any edit to a
        snapshot-bound artifact. A no-op unless the video is currently
        ``approved`` - the old snapshot is never touched either way, only the
        video's lifecycle status moves back to ``in_review`` so a new approval
        creates a new snapshot.

        Not yet wired to ``content``'s own version-creation methods (that
        cross-module call is this phase's Known gap 3's remaining half); call
        this explicitly from the API layer until it is.
        """
        video = await self._videos.get(workspace_id=workspace_id, video_id=video_id)
        if video is None or video.status != VideoStatus.APPROVED:
            return
        await self._videos.update_status(
            workspace_id=workspace_id,
            video_id=video_id,
            status=VideoStatus.IN_REVIEW,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )

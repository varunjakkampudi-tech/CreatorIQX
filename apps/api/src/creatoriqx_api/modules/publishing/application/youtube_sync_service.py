"""Links a video to a real YouTube video and applies the approved snapshot
(spec §3, feature 14, ADR 0007).

Every write is capability-gated (``CapabilityService.require_available``),
immediately read back and verified, and recorded as its own
:class:`SyncOperation` row so partial failure stays visible. Drift is
detected by comparing normalized fields and is always resolved explicitly -
never silently adopted or overwritten (spec §3).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from creatoriqx_api.modules.content.application.ports import MetadataVersionStore
from creatoriqx_api.modules.publishing.application.capability_service import CapabilityService
from creatoriqx_api.modules.publishing.application.ports import (
    MetadataFields,
    NewRemoteSnapshot,
    NewSyncOperation,
    NewYoutubeVideoLink,
    PublishSnapshotStore,
    RemoteSnapshotStore,
    SyncOperationStore,
    YoutubeVideoLinkStore,
    YoutubeWriteClient,
)
from creatoriqx_api.modules.publishing.domain.capability import Capability
from creatoriqx_api.modules.publishing.domain.drift import (
    DriftResolutionMode,
    has_drift,
    normalize_metadata_for_drift,
)
from creatoriqx_api.modules.publishing.domain.errors import (
    CapabilityUnavailableError,
    PublishSnapshotNotFoundError,
    VideoAlreadyLinkedToAnotherChannelError,
    VideoLinkNotFoundError,
)
from creatoriqx_api.modules.publishing.domain.sync_operation import (
    SyncFieldGroup,
    SyncOperation,
    SyncOperationStatus,
)
from creatoriqx_api.modules.publishing.domain.sync_state import SyncState, assert_sync_transition
from creatoriqx_api.modules.publishing.domain.video_link import YoutubeVideoLink
from creatoriqx_api.modules.youtube.application.ports import (
    ChannelConnectionStore,
    YouTubeDataApiClient,
)


class YoutubeSyncService:
    def __init__(
        self,
        *,
        link_store: YoutubeVideoLinkStore,
        snapshot_store: PublishSnapshotStore,
        sync_op_store: SyncOperationStore,
        remote_snapshot_store: RemoteSnapshotStore,
        metadata_store: MetadataVersionStore,
        capabilities: CapabilityService,
        connection_store: ChannelConnectionStore,
        data_api_client: YouTubeDataApiClient,
        write_client: YoutubeWriteClient,
    ) -> None:
        self._links = link_store
        self._snapshots = snapshot_store
        self._sync_ops = sync_op_store
        self._remote_snapshots = remote_snapshot_store
        self._metadata = metadata_store
        self._capabilities = capabilities
        self._connections = connection_store
        self._data_api = data_api_client
        self._write_client = write_client

    async def link_video(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        channel_id: uuid.UUID,
        youtube_video_id: str,
    ) -> YoutubeVideoLink:
        """Link a local video to a real YouTube video id, verifying it belongs to
        the given channel through the uploads playlist (spec §3: discover
        manually uploaded videos this way, never ``search.list``).
        """
        existing = await self._links.get_by_youtube_video_id(
            workspace_id=workspace_id, youtube_video_id=youtube_video_id
        )
        if existing is not None and existing.video_id != video_id:
            raise VideoAlreadyLinkedToAnotherChannelError()

        connection = await self._connections.get_active_connection(
            workspace_id=workspace_id, channel_id=channel_id
        )
        if connection.uploads_playlist_id is None:
            raise VideoAlreadyLinkedToAnotherChannelError(
                "this channel has no known uploads playlist"
            )
        uploads = await self._data_api.list_uploads(
            connection.access_token,
            workspace_id=workspace_id,
            uploads_playlist_id=connection.uploads_playlist_id,
            limit=200,
        )
        if youtube_video_id not in uploads:
            raise VideoAlreadyLinkedToAnotherChannelError(
                "this video was not found in the channel's uploads"
            )

        return await self._links.create(
            NewYoutubeVideoLink(
                workspace_id=workspace_id,
                video_id=video_id,
                channel_id=channel_id,
                youtube_video_id=youtube_video_id,
            )
        )

    async def apply_snapshot(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[SyncOperation]:
        """Apply the latest approved snapshot's metadata to the linked YouTube
        video, per-field-group, with read-back verification after every write
        (spec §3, feature 14). Returns the recorded :class:`SyncOperation` rows.
        """
        link = await self._links.get_for_video(workspace_id=workspace_id, video_id=video_id)
        if link is None:
            raise VideoLinkNotFoundError()
        snapshot = await self._snapshots.get_latest_for_video(
            workspace_id=workspace_id, video_id=video_id
        )
        if snapshot is None:
            raise PublishSnapshotNotFoundError()

        connection = await self._connections.get_active_connection(
            workspace_id=workspace_id, channel_id=link.channel_id
        )

        operation = await self._apply_metadata(
            workspace_id=workspace_id,
            link=link,
            snapshot_id=snapshot.id,
            metadata_version_id=snapshot.metadata_version_id,
            access_token=connection.access_token,
        )

        new_sync_state = (
            SyncState.SYNCED
            if operation.status == SyncOperationStatus.SUCCEEDED
            else SyncState.SYNC_FAILED
        )
        assert_sync_transition(link.sync_state, SyncState.PENDING_SYNC)
        await self._links.update_sync_state(
            workspace_id=workspace_id, link_id=link.id, sync_state=SyncState.PENDING_SYNC
        )
        assert_sync_transition(SyncState.PENDING_SYNC, new_sync_state)
        await self._links.update_sync_state(
            workspace_id=workspace_id,
            link_id=link.id,
            sync_state=new_sync_state,
            last_synced_at=datetime.now(UTC),
            last_remote_etag=operation.remote_etag,
        )
        return [operation]

    async def _apply_metadata(
        self,
        *,
        workspace_id: uuid.UUID,
        link: YoutubeVideoLink,
        snapshot_id: uuid.UUID,
        metadata_version_id: uuid.UUID,
        access_token: str,
    ) -> SyncOperation:
        try:
            await self._capabilities.require_available(Capability.METADATA_UPDATE)
        except CapabilityUnavailableError as exc:
            return await self._sync_ops.create(
                NewSyncOperation(
                    workspace_id=workspace_id,
                    video_link_id=link.id,
                    applied_snapshot_id=snapshot_id,
                    field_group=SyncFieldGroup.METADATA,
                    status=SyncOperationStatus.MANUAL_FALLBACK,
                    error_details=str(exc),
                    quota_cost=0,
                    remote_etag=None,
                    readback_verified=False,
                    finished_at=datetime.now(UTC),
                )
            )

        metadata = await self._metadata.get(
            workspace_id=workspace_id, version_id=metadata_version_id
        )
        if metadata is None:
            raise PublishSnapshotNotFoundError("the snapshot's metadata version no longer exists")

        current = await self._write_client.get_video_state(
            access_token, workspace_id=workspace_id, youtube_video_id=link.youtube_video_id
        )
        updated = await self._write_client.update_metadata(
            access_token,
            workspace_id=workspace_id,
            youtube_video_id=link.youtube_video_id,
            current=current,
            fields=MetadataFields(
                title=metadata.title,
                description=metadata.description,
                tags=metadata.tags,
                category=metadata.category,
                publish_at=None,
            ),
        )

        local_norm = normalize_metadata_for_drift(
            title=metadata.title,
            description=metadata.description,
            tags=metadata.tags,
            category=metadata.category,
        )
        remote_norm = normalize_metadata_for_drift(
            title=updated.title,
            description=updated.description,
            tags=updated.tags,
            category=updated.category,
        )
        readback_verified = not has_drift(local_norm, remote_norm)

        await self._remote_snapshots.save(
            NewRemoteSnapshot(
                workspace_id=workspace_id,
                video_link_id=link.id,
                fields={
                    "title": updated.title,
                    "description": updated.description,
                    "tags": list(updated.tags),
                    "category": updated.category,
                },
                privacy_status=updated.privacy_status,
                has_been_published=updated.has_been_published,
            )
        )

        return await self._sync_ops.create(
            NewSyncOperation(
                workspace_id=workspace_id,
                video_link_id=link.id,
                applied_snapshot_id=snapshot_id,
                field_group=SyncFieldGroup.METADATA,
                status=(
                    SyncOperationStatus.SUCCEEDED
                    if readback_verified
                    else SyncOperationStatus.FAILED
                ),
                error_details=None
                if readback_verified
                else "read-back did not match what was sent",
                quota_cost=50,
                remote_etag=updated.etag,
                readback_verified=readback_verified,
                finished_at=datetime.now(UTC),
            )
        )

    async def detect_drift(self, *, workspace_id: uuid.UUID, video_id: uuid.UUID) -> bool:
        """Re-read the linked video and compare it against the approved snapshot's
        metadata. Flags drift on the link but never resolves it automatically
        (spec §3).
        """
        link = await self._links.get_for_video(workspace_id=workspace_id, video_id=video_id)
        if link is None:
            raise VideoLinkNotFoundError()
        snapshot = await self._snapshots.get_latest_for_video(
            workspace_id=workspace_id, video_id=video_id
        )
        if snapshot is None:
            raise PublishSnapshotNotFoundError()
        metadata = await self._metadata.get(
            workspace_id=workspace_id, version_id=snapshot.metadata_version_id
        )
        if metadata is None:
            raise PublishSnapshotNotFoundError("the snapshot's metadata version no longer exists")

        connection = await self._connections.get_active_connection(
            workspace_id=workspace_id, channel_id=link.channel_id
        )
        remote = await self._write_client.get_video_state(
            connection.access_token,
            workspace_id=workspace_id,
            youtube_video_id=link.youtube_video_id,
        )

        local_norm = normalize_metadata_for_drift(
            title=metadata.title,
            description=metadata.description,
            tags=metadata.tags,
            category=metadata.category,
        )
        remote_norm = normalize_metadata_for_drift(
            title=remote.title,
            description=remote.description,
            tags=remote.tags,
            category=remote.category,
        )
        drifted = has_drift(local_norm, remote_norm)
        if drifted and link.sync_state != SyncState.DRIFT_DETECTED:
            assert_sync_transition(link.sync_state, SyncState.DRIFT_DETECTED)
            await self._links.update_sync_state(
                workspace_id=workspace_id, link_id=link.id, sync_state=SyncState.DRIFT_DETECTED
            )
        return drifted

    async def resolve_drift(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        mode: DriftResolutionMode,
    ) -> None:
        """Explicit drift resolution (spec §3: "always explicit"). ``ignore`` keeps
        the link flagged as drifted; ``adopt_remote``/``overwrite_remote`` need a
        new local version or a new approval respectively, which belong to a
        follow-up ticket once this phase's routes exist to drive them end to
        end - recorded honestly as a known gap rather than faked here.
        """
        link = await self._links.get_for_video(workspace_id=workspace_id, video_id=video_id)
        if link is None:
            raise VideoLinkNotFoundError()

        if mode == DriftResolutionMode.IGNORE:
            return  # stays flagged, per spec §3 - never silently cleared

        # adopt_remote / overwrite_remote both require a fresh sync cycle
        # before the link can leave drift_detected; the actual content change
        # (new local version, or a re-apply) is driven by the caller.
        assert_sync_transition(link.sync_state, SyncState.PENDING_SYNC)
        await self._links.update_sync_state(
            workspace_id=workspace_id, link_id=link.id, sync_state=SyncState.PENDING_SYNC
        )

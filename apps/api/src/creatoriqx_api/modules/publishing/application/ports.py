"""Ports for the publishing use cases (QA, approval, capability, YouTube sync).

Infrastructure implements these; the application layer never imports
SQLAlchemy or httpx directly (spec §6 ports and adapters, mirroring every
other module's seam).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from creatoriqx_api.modules.publishing.domain.capability import Capability, CapabilityEvidence
from creatoriqx_api.modules.publishing.domain.remote_snapshot import RemoteSnapshot
from creatoriqx_api.modules.publishing.domain.snapshot import PublishSnapshot
from creatoriqx_api.modules.publishing.domain.sync_operation import (
    SyncFieldGroup,
    SyncOperation,
    SyncOperationStatus,
)
from creatoriqx_api.modules.publishing.domain.sync_state import SyncState
from creatoriqx_api.modules.publishing.domain.video_link import YoutubeVideoLink


@dataclass(frozen=True, slots=True)
class NewPublishSnapshot:
    """What ``ApprovalService`` asks a :class:`PublishSnapshotStore` to insert.
    Insert-only - there is no update method on the store (ADR 0006).
    """

    workspace_id: uuid.UUID
    video_id: uuid.UUID
    script_version_id: uuid.UUID
    metadata_version_id: uuid.UUID
    chapter_version_id: uuid.UUID | None
    thumbnail_variant_id: uuid.UUID | None
    disclosure_altered: bool
    disclosure_synthetic: bool
    scheduled_at: datetime | None
    approved_by: uuid.UUID


class PublishSnapshotStore(Protocol):
    async def create(self, snapshot: NewPublishSnapshot) -> PublishSnapshot: ...

    async def get(
        self, *, workspace_id: uuid.UUID, snapshot_id: uuid.UUID
    ) -> PublishSnapshot | None: ...

    async def get_latest_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> PublishSnapshot | None:
        """The most recently approved snapshot for this video, or ``None`` if it has
        never been approved.
        """


@dataclass(frozen=True, slots=True)
class NewYoutubeVideoLink:
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    channel_id: uuid.UUID
    youtube_video_id: str


class YoutubeVideoLinkStore(Protocol):
    async def create(self, link: NewYoutubeVideoLink) -> YoutubeVideoLink: ...

    async def get_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> YoutubeVideoLink | None: ...

    async def get_by_youtube_video_id(
        self, *, workspace_id: uuid.UUID, youtube_video_id: str
    ) -> YoutubeVideoLink | None:
        """Used to enforce the ``(workspace_id, youtube_video_id)`` uniqueness rule
        (spec §3) before a link is created.
        """

    async def update_sync_state(
        self,
        *,
        workspace_id: uuid.UUID,
        link_id: uuid.UUID,
        sync_state: SyncState,
        last_synced_at: datetime | None = None,
        last_remote_etag: str | None = None,
    ) -> YoutubeVideoLink: ...


@dataclass(frozen=True, slots=True)
class NewSyncOperation:
    workspace_id: uuid.UUID
    video_link_id: uuid.UUID
    applied_snapshot_id: uuid.UUID
    field_group: SyncFieldGroup
    status: SyncOperationStatus
    error_details: str | None
    quota_cost: int
    remote_etag: str | None
    readback_verified: bool
    finished_at: datetime | None


class SyncOperationStore(Protocol):
    async def create(self, operation: NewSyncOperation) -> SyncOperation: ...

    async def list_for_link(
        self, *, workspace_id: uuid.UUID, video_link_id: uuid.UUID
    ) -> list[SyncOperation]: ...


@dataclass(frozen=True, slots=True)
class NewRemoteSnapshot:
    workspace_id: uuid.UUID
    video_link_id: uuid.UUID
    fields: dict[str, object]
    privacy_status: str
    has_been_published: bool


class RemoteSnapshotStore(Protocol):
    async def save(self, snapshot: NewRemoteSnapshot) -> RemoteSnapshot: ...

    async def get_latest_for_link(
        self, *, workspace_id: uuid.UUID, video_link_id: uuid.UUID
    ) -> RemoteSnapshot | None: ...


class CapabilityStore(Protocol):
    """Reads and seeds the global ``youtube_capabilities`` table (spec §3). No
    tenant context - this table has no ``workspace_id``.
    """

    async def get(self, capability: Capability) -> CapabilityEvidence | None: ...

    async def list_all(self) -> list[CapabilityEvidence]: ...

    async def upsert(self, evidence: CapabilityEvidence) -> CapabilityEvidence:
        """Record new or changed evidence. Only an owner action (verifying against
        current Google docs) should ever move a capability to ``available``
        (spec §3: "Refuse to enable any write capability without recorded
        verification evidence.") - enforced by the domain's
        ``assert_evidence_complete``, which the service calls first.
        """


@dataclass(frozen=True, slots=True)
class RemoteVideoState:
    """Every mutable field this app manages on a YouTube video, as last read
    (spec §3 ADR 0007 #5: "read the current resource first and send back every
    mutable field that must be preserved").
    """

    youtube_video_id: str
    title: str
    description: str
    tags: tuple[str, ...]
    category: str | None
    privacy_status: str
    has_been_published: bool
    publish_at: datetime | None
    etag: str | None


@dataclass(frozen=True, slots=True)
class MetadataFields:
    """The subset of :class:`RemoteVideoState` an approved snapshot's metadata
    governs - what ``YoutubeSyncService`` asks the write client to set.
    """

    title: str
    description: str
    tags: tuple[str, ...]
    category: str | None
    publish_at: datetime | None


class YoutubeWriteClient(Protocol):
    """The YouTube Data API v3 write operations this module performs (spec §3).

    Built out for real in P1D-04 (extends the existing read-only
    ``youtube_data_api.py`` adapter); ``YoutubeSyncService`` depends on this
    protocol so it can be tested now against a fake.
    """

    async def get_video_state(
        self, access_token: str, *, workspace_id: uuid.UUID, youtube_video_id: str
    ) -> RemoteVideoState:
        """Read the video's current mutable fields (``videos.list``)."""

    async def update_metadata(
        self,
        access_token: str,
        *,
        workspace_id: uuid.UUID,
        youtube_video_id: str,
        current: RemoteVideoState,
        fields: MetadataFields,
    ) -> RemoteVideoState:
        """``videos.update``, resending every field in ``current`` with only the
        snapshot's managed fields overridden (ADR 0007 #5 - never send a partial
        payload). Returns the resource as read back after the write.
        """

    async def set_thumbnail(
        self,
        access_token: str,
        *,
        workspace_id: uuid.UUID,
        youtube_video_id: str,
        image_bytes: bytes,
        content_type: str,
    ) -> None:
        """``thumbnails.set``."""

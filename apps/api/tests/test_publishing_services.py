"""Tests for the publishing module's application services (spec §3, §4
feature 12-14, Phase 1D P1D-03), using in-memory fakes for every port.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pytest

from creatoriqx_api.modules.content.application.ports import (
    NewChapterVersion,
    NewMetadataVersion,
    NewScriptVersion,
)
from creatoriqx_api.modules.content.domain.chapters import Chapter, ChapterVersion
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion
from creatoriqx_api.modules.content.domain.script import ScriptAuthor, ScriptVersion
from creatoriqx_api.modules.planning.application.ports import NewVideo
from creatoriqx_api.modules.planning.domain.errors import VideoNotFoundError
from creatoriqx_api.modules.planning.domain.video import Video, VideoStatus
from creatoriqx_api.modules.publishing.application.approval_service import ApprovalService
from creatoriqx_api.modules.publishing.application.capability_service import CapabilityService
from creatoriqx_api.modules.publishing.application.ports import (
    MetadataFields,
    NewPublishSnapshot,
    NewRemoteSnapshot,
    NewSyncOperation,
    NewYoutubeVideoLink,
    RemoteVideoState,
)
from creatoriqx_api.modules.publishing.application.qa_service import QaService
from creatoriqx_api.modules.publishing.application.youtube_sync_service import YoutubeSyncService
from creatoriqx_api.modules.publishing.domain.capability import (
    Capability,
    CapabilityEvidence,
    CapabilityStatus,
)
from creatoriqx_api.modules.publishing.domain.drift import DriftResolutionMode
from creatoriqx_api.modules.publishing.domain.errors import (
    QaNotPassedError,
    VideoAlreadyLinkedToAnotherChannelError,
)
from creatoriqx_api.modules.publishing.domain.remote_snapshot import RemoteSnapshot
from creatoriqx_api.modules.publishing.domain.snapshot import PublishSnapshot
from creatoriqx_api.modules.publishing.domain.sync_operation import (
    SyncOperation,
    SyncOperationStatus,
)
from creatoriqx_api.modules.publishing.domain.sync_state import SyncState
from creatoriqx_api.modules.publishing.domain.video_link import YoutubeVideoLink
from creatoriqx_api.modules.youtube.application.ports import ActiveConnection, VideoStats
from creatoriqx_api.modules.youtube.domain.connection import (
    ChannelInfo,
    ConnectedChannel,
    OAuthTokens,
)

_WORKSPACE = uuid.uuid4()
_ACTOR = uuid.uuid4()
_CHANNEL = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(UTC)


# --- content fakes -----------------------------------------------------------


@dataclass
class FakeScriptStore:
    versions: dict[uuid.UUID, ScriptVersion] = field(default_factory=dict)

    async def create(self, version: NewScriptVersion) -> ScriptVersion:
        for key, existing in list(self.versions.items()):
            if existing.video_id == version.video_id:
                self.versions[key] = dataclasses.replace(existing, is_current=False)
        record = ScriptVersion(
            id=uuid.uuid4(),
            workspace_id=version.workspace_id,
            video_id=version.video_id,
            variant_label=version.variant_label,
            author=version.author,
            hook=version.hook,
            outline=version.outline,
            body=version.body,
            parent_version_id=version.parent_version_id,
            is_current=True,
            created_at=_now(),
        )
        self.versions[record.id] = record
        return record

    async def get(self, *, workspace_id: uuid.UUID, version_id: uuid.UUID) -> ScriptVersion | None:
        return self.versions.get(version_id)

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[ScriptVersion]:
        return [v for v in self.versions.values() if v.video_id == video_id]


@dataclass
class FakeMetadataStore:
    versions: dict[uuid.UUID, MetadataVersion] = field(default_factory=dict)

    async def create(self, version: NewMetadataVersion) -> MetadataVersion:
        for key, existing in list(self.versions.items()):
            if existing.video_id == version.video_id:
                self.versions[key] = dataclasses.replace(existing, is_current=False)
        record = MetadataVersion(
            id=uuid.uuid4(),
            workspace_id=version.workspace_id,
            video_id=version.video_id,
            title=version.title,
            description=version.description,
            tags=version.tags,
            category=version.category,
            disclosure_altered=version.disclosure_altered,
            disclosure_synthetic=version.disclosure_synthetic,
            rationale=version.rationale,
            parent_version_id=version.parent_version_id,
            is_current=True,
            created_at=_now(),
        )
        self.versions[record.id] = record
        return record

    async def get(
        self, *, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> MetadataVersion | None:
        return self.versions.get(version_id)

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[MetadataVersion]:
        return [v for v in self.versions.values() if v.video_id == video_id]


@dataclass
class FakeChapterStore:
    versions: dict[uuid.UUID, ChapterVersion] = field(default_factory=dict)

    async def create(self, version: NewChapterVersion) -> ChapterVersion:
        for key, existing in list(self.versions.items()):
            if existing.video_id == version.video_id:
                self.versions[key] = dataclasses.replace(existing, is_current=False)
        record = ChapterVersion(
            id=uuid.uuid4(),
            workspace_id=version.workspace_id,
            video_id=version.video_id,
            transcript_id=version.transcript_id,
            chapters=version.chapters,
            parent_version_id=version.parent_version_id,
            is_current=True,
            created_at=_now(),
        )
        self.versions[record.id] = record
        return record

    async def get(self, *, workspace_id: uuid.UUID, version_id: uuid.UUID) -> ChapterVersion | None:
        return self.versions.get(version_id)

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[ChapterVersion]:
        return [v for v in self.versions.values() if v.video_id == video_id]


# --- planning fake -----------------------------------------------------------


@dataclass
class FakeVideoStore:
    videos: dict[uuid.UUID, Video] = field(default_factory=dict)

    async def create(
        self, video: NewVideo, *, actor_user_id: uuid.UUID, correlation_id: str | None
    ) -> Video:
        now = _now()
        record = Video(
            id=uuid.uuid4(),
            workspace_id=video.workspace_id,
            channel_id=video.channel_id,
            plan_id=video.plan_id,
            title=video.title,
            status=video.status,
            created_at=now,
            updated_at=now,
        )
        self.videos[record.id] = record
        return record

    async def get(self, *, workspace_id: uuid.UUID, video_id: uuid.UUID) -> Video | None:
        video = self.videos.get(video_id)
        if video is None or video.workspace_id != workspace_id:
            return None
        return video

    async def list_for_workspace(self, *, workspace_id: uuid.UUID) -> list[Video]:
        return [v for v in self.videos.values() if v.workspace_id == workspace_id]

    async def update_status(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        status: VideoStatus,
        actor_user_id: uuid.UUID,
        correlation_id: str | None,
    ) -> Video:
        video = self.videos[video_id]
        updated = Video(
            id=video.id,
            workspace_id=video.workspace_id,
            channel_id=video.channel_id,
            plan_id=video.plan_id,
            title=video.title,
            status=status,
            created_at=video.created_at,
            updated_at=_now(),
        )
        self.videos[video_id] = updated
        return updated


# --- publishing fakes --------------------------------------------------------


@dataclass
class FakeSnapshotStore:
    snapshots: dict[uuid.UUID, PublishSnapshot] = field(default_factory=dict)

    async def create(self, snapshot: NewPublishSnapshot) -> PublishSnapshot:
        now = _now()
        record = PublishSnapshot(
            id=uuid.uuid4(),
            workspace_id=snapshot.workspace_id,
            video_id=snapshot.video_id,
            script_version_id=snapshot.script_version_id,
            metadata_version_id=snapshot.metadata_version_id,
            chapter_version_id=snapshot.chapter_version_id,
            thumbnail_variant_id=snapshot.thumbnail_variant_id,
            disclosure_altered=snapshot.disclosure_altered,
            disclosure_synthetic=snapshot.disclosure_synthetic,
            scheduled_at=snapshot.scheduled_at,
            approved_by=snapshot.approved_by,
            approved_at=now,
            created_at=now,
        )
        self.snapshots[record.id] = record
        return record

    async def get(
        self, *, workspace_id: uuid.UUID, snapshot_id: uuid.UUID
    ) -> PublishSnapshot | None:
        return self.snapshots.get(snapshot_id)

    async def get_latest_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> PublishSnapshot | None:
        matches = [s for s in self.snapshots.values() if s.video_id == video_id]
        return max(matches, key=lambda s: s.approved_at) if matches else None


@dataclass
class FakeLinkStore:
    links: dict[uuid.UUID, YoutubeVideoLink] = field(default_factory=dict)

    async def create(self, link: NewYoutubeVideoLink) -> YoutubeVideoLink:
        now = _now()
        record = YoutubeVideoLink(
            id=uuid.uuid4(),
            workspace_id=link.workspace_id,
            video_id=link.video_id,
            channel_id=link.channel_id,
            youtube_video_id=link.youtube_video_id,
            sync_state=SyncState.LINKED,
            linked_at=now,
            last_synced_at=None,
            last_remote_etag=None,
            created_at=now,
        )
        self.links[record.id] = record
        return record

    async def get_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> YoutubeVideoLink | None:
        return next((lk for lk in self.links.values() if lk.video_id == video_id), None)

    async def get_by_youtube_video_id(
        self, *, workspace_id: uuid.UUID, youtube_video_id: str
    ) -> YoutubeVideoLink | None:
        return next(
            (lk for lk in self.links.values() if lk.youtube_video_id == youtube_video_id), None
        )

    async def update_sync_state(
        self,
        *,
        workspace_id: uuid.UUID,
        link_id: uuid.UUID,
        sync_state: SyncState,
        last_synced_at: datetime | None = None,
        last_remote_etag: str | None = None,
    ) -> YoutubeVideoLink:
        link = self.links[link_id]
        updated = YoutubeVideoLink(
            id=link.id,
            workspace_id=link.workspace_id,
            video_id=link.video_id,
            channel_id=link.channel_id,
            youtube_video_id=link.youtube_video_id,
            sync_state=sync_state,
            linked_at=link.linked_at,
            last_synced_at=last_synced_at or link.last_synced_at,
            last_remote_etag=last_remote_etag or link.last_remote_etag,
            created_at=link.created_at,
        )
        self.links[link_id] = updated
        return updated


@dataclass
class FakeSyncOperationStore:
    operations: list[SyncOperation] = field(default_factory=list)

    async def create(self, operation: NewSyncOperation) -> SyncOperation:
        record = SyncOperation(
            id=uuid.uuid4(),
            workspace_id=operation.workspace_id,
            video_link_id=operation.video_link_id,
            applied_snapshot_id=operation.applied_snapshot_id,
            field_group=operation.field_group,
            status=operation.status,
            error_details=operation.error_details,
            quota_cost=operation.quota_cost,
            remote_etag=operation.remote_etag,
            readback_verified=operation.readback_verified,
            finished_at=operation.finished_at,
            created_at=_now(),
        )
        self.operations.append(record)
        return record

    async def list_for_link(
        self, *, workspace_id: uuid.UUID, video_link_id: uuid.UUID
    ) -> list[SyncOperation]:
        return [o for o in self.operations if o.video_link_id == video_link_id]


@dataclass
class FakeRemoteSnapshotStore:
    snapshots: list[RemoteSnapshot] = field(default_factory=list)

    async def save(self, snapshot: NewRemoteSnapshot) -> RemoteSnapshot:
        record = RemoteSnapshot(
            id=uuid.uuid4(),
            workspace_id=snapshot.workspace_id,
            video_link_id=snapshot.video_link_id,
            fields=snapshot.fields,
            privacy_status=snapshot.privacy_status,
            has_been_published=snapshot.has_been_published,
            captured_at=_now(),
        )
        self.snapshots.append(record)
        return record

    async def get_latest_for_link(
        self, *, workspace_id: uuid.UUID, video_link_id: uuid.UUID
    ) -> RemoteSnapshot | None:
        matches = [s for s in self.snapshots if s.video_link_id == video_link_id]
        return max(matches, key=lambda s: s.captured_at) if matches else None


@dataclass
class FakeCapabilityStore:
    evidence: dict[Capability, CapabilityEvidence] = field(default_factory=dict)

    async def get(self, capability: Capability) -> CapabilityEvidence | None:
        return self.evidence.get(capability)

    async def list_all(self) -> list[CapabilityEvidence]:
        return list(self.evidence.values())

    async def upsert(self, evidence: CapabilityEvidence) -> CapabilityEvidence:
        self.evidence[evidence.capability] = evidence
        return evidence


def _available_evidence(capability: Capability) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=capability,
        status=CapabilityStatus.AVAILABLE,
        verified_on=date(2026, 10, 1),
        source_url="https://developers.google.com/youtube/v3",
        required_scopes=("https://www.googleapis.com/auth/youtube",),
        verification_notes="verified",
        updated_at=_now(),
    )


def _restricted_evidence(capability: Capability) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=capability,
        status=CapabilityStatus.RESTRICTED,
        verified_on=None,
        source_url=None,
        required_scopes=(),
        verification_notes=None,
        updated_at=_now(),
    )


@dataclass
class FakeConnectionStore:
    uploads_playlist_id: str = "UU_channel"

    async def save_connection(
        self,
        *,
        workspace_id: uuid.UUID,
        connected_by_user_id: uuid.UUID,
        tokens: OAuthTokens,
        channel: ChannelInfo,
    ) -> ConnectedChannel:
        raise NotImplementedError

    async def list_channels(self, workspace_id: uuid.UUID) -> list[ConnectedChannel]:
        raise NotImplementedError

    async def get_active_connection(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> ActiveConnection:
        return ActiveConnection(
            connection_id=uuid.uuid4(),
            channel_id=channel_id,
            youtube_channel_id="UC_channel",
            uploads_playlist_id=self.uploads_playlist_id,
            access_token="token",
            access_token_expires_at=_now(),
            refresh_token="refresh",
        )

    async def update_access_token(
        self, *, workspace_id: uuid.UUID, connection_id: uuid.UUID, tokens: OAuthTokens
    ) -> None:
        raise NotImplementedError

    async def disconnect(self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID) -> None:
        raise NotImplementedError

    async def update_channel_stats(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID, channel: ChannelInfo
    ) -> None:
        raise NotImplementedError


@dataclass
class FakeDataApiClient:
    uploads: list[str] = field(default_factory=lambda: ["yt-video-1"])

    async def get_own_channel(self, access_token: str, *, workspace_id: uuid.UUID) -> ChannelInfo:
        raise NotImplementedError

    async def list_uploads(
        self, access_token: str, *, workspace_id: uuid.UUID, uploads_playlist_id: str, limit: int
    ) -> list[str]:
        return self.uploads

    async def list_video_stats(self, *args: object, **kwargs: object) -> list[VideoStats]:
        raise NotImplementedError


@dataclass
class FakeWriteClient:
    remote_title: str = "Old Title"

    async def get_video_state(
        self, access_token: str, *, workspace_id: uuid.UUID, youtube_video_id: str
    ) -> RemoteVideoState:
        return RemoteVideoState(
            youtube_video_id=youtube_video_id,
            title=self.remote_title,
            description="old description",
            tags=("old",),
            category="22",
            privacy_status="private",
            has_been_published=False,
            publish_at=None,
            etag="etag-1",
        )

    async def update_metadata(
        self,
        access_token: str,
        *,
        workspace_id: uuid.UUID,
        youtube_video_id: str,
        current: RemoteVideoState,
        fields: MetadataFields,
    ) -> RemoteVideoState:
        return RemoteVideoState(
            youtube_video_id=youtube_video_id,
            title=fields.title,
            description=fields.description,
            tags=fields.tags,
            category=fields.category,
            privacy_status=current.privacy_status,
            has_been_published=current.has_been_published,
            publish_at=fields.publish_at,
            etag="etag-2",
        )

    async def set_thumbnail(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError


# --- fixtures -----------------------------------------------------------------


async def _seed_video(video_store: FakeVideoStore, *, status: VideoStatus) -> Video:
    return await video_store.create(
        NewVideo(
            workspace_id=_WORKSPACE,
            channel_id=_CHANNEL,
            plan_id=None,
            title="My Video",
            status=status,
        ),
        actor_user_id=_ACTOR,
        correlation_id=None,
    )


async def _seed_clean_artifacts(
    *,
    video_id: uuid.UUID,
    scripts: FakeScriptStore,
    metadata: FakeMetadataStore,
    chapters: FakeChapterStore,
) -> None:
    await scripts.create(
        NewScriptVersion(
            workspace_id=_WORKSPACE,
            video_id=video_id,
            variant_label="A",
            author=ScriptAuthor.HUMAN,
            hook="A hook that is definitely long enough to pass.",
            outline="outline",
            body="body",
        )
    )
    await metadata.create(
        NewMetadataVersion(
            workspace_id=_WORKSPACE,
            video_id=video_id,
            title="A Good Title",
            description="A full description.",
            tags=("one", "two"),
            category="22",
            disclosure_altered=False,
            disclosure_synthetic=False,
            rationale="because",
        )
    )
    await chapters.create(
        NewChapterVersion(
            workspace_id=_WORKSPACE,
            video_id=video_id,
            transcript_id=uuid.uuid4(),
            chapters=(Chapter(0, "Intro"), Chapter(30, "Middle"), Chapter(90, "End")),
        )
    )


def _qa_service(
    scripts: FakeScriptStore,
    metadata: FakeMetadataStore,
    chapters: FakeChapterStore,
    links: FakeLinkStore,
    remote_snapshots: FakeRemoteSnapshotStore,
) -> QaService:
    return QaService(
        script_store=scripts,
        metadata_store=metadata,
        chapter_store=chapters,
        video_link_store=links,
        remote_snapshot_store=remote_snapshots,
    )


class TestQaService:
    async def test_a_complete_video_passes(self) -> None:
        scripts, metadata, chapters = FakeScriptStore(), FakeMetadataStore(), FakeChapterStore()
        links, remotes = FakeLinkStore(), FakeRemoteSnapshotStore()
        video_id = uuid.uuid4()
        await _seed_clean_artifacts(
            video_id=video_id, scripts=scripts, metadata=metadata, chapters=chapters
        )
        service = _qa_service(scripts, metadata, chapters, links, remotes)
        result = await service.run(workspace_id=_WORKSPACE, video_id=video_id)
        assert result.passed is True

    async def test_a_video_with_no_artifacts_fails_with_specific_checks(self) -> None:
        scripts, metadata, chapters = FakeScriptStore(), FakeMetadataStore(), FakeChapterStore()
        links, remotes = FakeLinkStore(), FakeRemoteSnapshotStore()
        service = _qa_service(scripts, metadata, chapters, links, remotes)
        result = await service.run(workspace_id=_WORKSPACE, video_id=uuid.uuid4())
        assert result.passed is False
        assert len(result.failing_checks) >= 2  # at least title and hook


class TestApprovalService:
    def _service(
        self,
        *,
        scripts: FakeScriptStore,
        metadata: FakeMetadataStore,
        chapters: FakeChapterStore,
        links: FakeLinkStore,
        remotes: FakeRemoteSnapshotStore,
        snapshots: FakeSnapshotStore,
        videos: FakeVideoStore,
    ) -> ApprovalService:
        qa = _qa_service(scripts, metadata, chapters, links, remotes)
        return ApprovalService(
            qa_service=qa,
            script_store=scripts,
            metadata_store=metadata,
            chapter_store=chapters,
            snapshot_store=snapshots,
            video_store=videos,
        )

    async def test_qa_failure_blocks_approval_with_specific_checks(self) -> None:
        scripts, metadata, chapters = FakeScriptStore(), FakeMetadataStore(), FakeChapterStore()
        links, remotes, snapshots, videos = (
            FakeLinkStore(),
            FakeRemoteSnapshotStore(),
            FakeSnapshotStore(),
            FakeVideoStore(),
        )
        video = await _seed_video(videos, status=VideoStatus.IN_REVIEW)
        # No artifacts seeded - title/hook/description all empty.
        service = self._service(
            scripts=scripts,
            metadata=metadata,
            chapters=chapters,
            links=links,
            remotes=remotes,
            snapshots=snapshots,
            videos=videos,
        )
        with pytest.raises(QaNotPassedError) as exc_info:
            await service.approve(workspace_id=_WORKSPACE, video_id=video.id, actor_user_id=_ACTOR)
        assert "title" in str(exc_info.value)

    async def test_approving_freezes_a_snapshot_immune_to_later_edits(self) -> None:
        scripts, metadata, chapters = FakeScriptStore(), FakeMetadataStore(), FakeChapterStore()
        links, remotes, snapshots, videos = (
            FakeLinkStore(),
            FakeRemoteSnapshotStore(),
            FakeSnapshotStore(),
            FakeVideoStore(),
        )
        video = await _seed_video(videos, status=VideoStatus.IN_REVIEW)
        await _seed_clean_artifacts(
            video_id=video.id, scripts=scripts, metadata=metadata, chapters=chapters
        )
        service = self._service(
            scripts=scripts,
            metadata=metadata,
            chapters=chapters,
            links=links,
            remotes=remotes,
            snapshots=snapshots,
            videos=videos,
        )
        snapshot = await service.approve(
            workspace_id=_WORKSPACE, video_id=video.id, actor_user_id=_ACTOR
        )
        original_metadata_version_id = snapshot.metadata_version_id

        # Edit the video further after approval - a brand new current version.
        await metadata.create(
            NewMetadataVersion(
                workspace_id=_WORKSPACE,
                video_id=video.id,
                title="A Totally Different Title",
                description="Changed.",
                tags=("new",),
                category="22",
                disclosure_altered=False,
                disclosure_synthetic=False,
                rationale="edited after approval",
            )
        )

        # The old snapshot's ids never change.
        refetched = await snapshots.get(workspace_id=_WORKSPACE, snapshot_id=snapshot.id)
        assert refetched is not None
        assert refetched.metadata_version_id == original_metadata_version_id

    async def test_reapproving_an_already_approved_video_is_idempotent(self) -> None:
        scripts, metadata, chapters = FakeScriptStore(), FakeMetadataStore(), FakeChapterStore()
        links, remotes, snapshots, videos = (
            FakeLinkStore(),
            FakeRemoteSnapshotStore(),
            FakeSnapshotStore(),
            FakeVideoStore(),
        )
        video = await _seed_video(videos, status=VideoStatus.IN_REVIEW)
        await _seed_clean_artifacts(
            video_id=video.id, scripts=scripts, metadata=metadata, chapters=chapters
        )
        service = self._service(
            scripts=scripts,
            metadata=metadata,
            chapters=chapters,
            links=links,
            remotes=remotes,
            snapshots=snapshots,
            videos=videos,
        )
        first = await service.approve(
            workspace_id=_WORKSPACE, video_id=video.id, actor_user_id=_ACTOR
        )
        second = await service.approve(
            workspace_id=_WORKSPACE, video_id=video.id, actor_user_id=_ACTOR
        )
        assert first.id == second.id

    async def test_approving_a_missing_video_raises(self) -> None:
        scripts, metadata, chapters = FakeScriptStore(), FakeMetadataStore(), FakeChapterStore()
        links, remotes, snapshots, videos = (
            FakeLinkStore(),
            FakeRemoteSnapshotStore(),
            FakeSnapshotStore(),
            FakeVideoStore(),
        )
        service = self._service(
            scripts=scripts,
            metadata=metadata,
            chapters=chapters,
            links=links,
            remotes=remotes,
            snapshots=snapshots,
            videos=videos,
        )
        with pytest.raises(VideoNotFoundError):
            await service.approve(
                workspace_id=_WORKSPACE, video_id=uuid.uuid4(), actor_user_id=_ACTOR
            )

    async def test_invalidate_if_approved_moves_back_to_in_review(self) -> None:
        videos = FakeVideoStore()
        video = await _seed_video(videos, status=VideoStatus.APPROVED)
        service = ApprovalService(
            qa_service=_qa_service(
                FakeScriptStore(),
                FakeMetadataStore(),
                FakeChapterStore(),
                FakeLinkStore(),
                FakeRemoteSnapshotStore(),
            ),
            script_store=FakeScriptStore(),
            metadata_store=FakeMetadataStore(),
            chapter_store=FakeChapterStore(),
            snapshot_store=FakeSnapshotStore(),
            video_store=videos,
        )
        await service.invalidate_if_approved(
            workspace_id=_WORKSPACE, video_id=video.id, actor_user_id=_ACTOR
        )
        refetched = await videos.get(workspace_id=_WORKSPACE, video_id=video.id)
        assert refetched is not None
        assert refetched.status == VideoStatus.IN_REVIEW

    async def test_invalidate_if_approved_is_a_noop_otherwise(self) -> None:
        videos = FakeVideoStore()
        video = await _seed_video(videos, status=VideoStatus.DRAFTING)
        service = ApprovalService(
            qa_service=_qa_service(
                FakeScriptStore(),
                FakeMetadataStore(),
                FakeChapterStore(),
                FakeLinkStore(),
                FakeRemoteSnapshotStore(),
            ),
            script_store=FakeScriptStore(),
            metadata_store=FakeMetadataStore(),
            chapter_store=FakeChapterStore(),
            snapshot_store=FakeSnapshotStore(),
            video_store=videos,
        )
        await service.invalidate_if_approved(
            workspace_id=_WORKSPACE, video_id=video.id, actor_user_id=_ACTOR
        )
        refetched = await videos.get(workspace_id=_WORKSPACE, video_id=video.id)
        assert refetched is not None
        assert refetched.status == VideoStatus.DRAFTING


class TestCapabilityService:
    async def test_require_available_passes_for_an_available_capability(self) -> None:
        store = FakeCapabilityStore(
            evidence={Capability.METADATA_UPDATE: _available_evidence(Capability.METADATA_UPDATE)}
        )
        service = CapabilityService(store)
        evidence = await service.require_available(Capability.METADATA_UPDATE)
        assert evidence.status == CapabilityStatus.AVAILABLE

    async def test_record_evidence_rejects_available_without_full_evidence(self) -> None:
        store = FakeCapabilityStore()
        service = CapabilityService(store)
        incomplete = CapabilityEvidence(
            capability=Capability.THUMBNAIL_UPDATE,
            status=CapabilityStatus.AVAILABLE,
            verified_on=None,
            source_url=None,
            required_scopes=(),
            verification_notes=None,
            updated_at=_now(),
        )
        from creatoriqx_api.modules.publishing.domain.errors import (
            CapabilityEvidenceIncompleteError,
        )

        with pytest.raises(CapabilityEvidenceIncompleteError):
            await service.record_evidence(incomplete)


class TestYoutubeSyncService:
    def _service(
        self,
        *,
        links: FakeLinkStore,
        snapshots: FakeSnapshotStore,
        sync_ops: FakeSyncOperationStore,
        remotes: FakeRemoteSnapshotStore,
        metadata: FakeMetadataStore,
        capability_store: FakeCapabilityStore,
        connections: FakeConnectionStore,
        data_api: FakeDataApiClient,
        write_client: FakeWriteClient,
    ) -> YoutubeSyncService:
        return YoutubeSyncService(
            link_store=links,
            snapshot_store=snapshots,
            sync_op_store=sync_ops,
            remote_snapshot_store=remotes,
            metadata_store=metadata,
            capabilities=CapabilityService(capability_store),
            connection_store=connections,
            data_api_client=data_api,
            write_client=write_client,
        )

    async def test_linking_a_video_not_in_the_channels_uploads_is_refused(self) -> None:
        links = FakeLinkStore()
        service = self._service(
            links=links,
            snapshots=FakeSnapshotStore(),
            sync_ops=FakeSyncOperationStore(),
            remotes=FakeRemoteSnapshotStore(),
            metadata=FakeMetadataStore(),
            capability_store=FakeCapabilityStore(),
            connections=FakeConnectionStore(),
            data_api=FakeDataApiClient(uploads=["some-other-video"]),
            write_client=FakeWriteClient(),
        )
        with pytest.raises(VideoAlreadyLinkedToAnotherChannelError):
            await service.link_video(
                workspace_id=_WORKSPACE,
                video_id=uuid.uuid4(),
                channel_id=_CHANNEL,
                youtube_video_id="yt-video-1",
            )

    async def test_linking_a_video_already_linked_elsewhere_is_refused(self) -> None:
        links = FakeLinkStore()
        await links.create(
            NewYoutubeVideoLink(
                workspace_id=_WORKSPACE,
                video_id=uuid.uuid4(),
                channel_id=_CHANNEL,
                youtube_video_id="yt-video-1",
            )
        )
        service = self._service(
            links=links,
            snapshots=FakeSnapshotStore(),
            sync_ops=FakeSyncOperationStore(),
            remotes=FakeRemoteSnapshotStore(),
            metadata=FakeMetadataStore(),
            capability_store=FakeCapabilityStore(),
            connections=FakeConnectionStore(),
            data_api=FakeDataApiClient(uploads=["yt-video-1"]),
            write_client=FakeWriteClient(),
        )
        with pytest.raises(VideoAlreadyLinkedToAnotherChannelError):
            await service.link_video(
                workspace_id=_WORKSPACE,
                video_id=uuid.uuid4(),
                channel_id=_CHANNEL,
                youtube_video_id="yt-video-1",
            )

    async def test_restricted_capability_is_skipped_as_manual_fallback(self) -> None:
        links = FakeLinkStore()
        link = await links.create(
            NewYoutubeVideoLink(
                workspace_id=_WORKSPACE,
                video_id=uuid.uuid4(),
                channel_id=_CHANNEL,
                youtube_video_id="yt-video-1",
            )
        )
        snapshots = FakeSnapshotStore()
        metadata = FakeMetadataStore()
        metadata_version = await metadata.create(
            NewMetadataVersion(
                workspace_id=_WORKSPACE,
                video_id=link.video_id,
                title="T",
                description="D",
                tags=(),
                category=None,
                disclosure_altered=False,
                disclosure_synthetic=False,
                rationale="r",
            )
        )
        snapshot = await snapshots.create(
            NewPublishSnapshot(
                workspace_id=_WORKSPACE,
                video_id=link.video_id,
                script_version_id=uuid.uuid4(),
                metadata_version_id=metadata_version.id,
                chapter_version_id=None,
                thumbnail_variant_id=None,
                disclosure_altered=False,
                disclosure_synthetic=False,
                scheduled_at=None,
                approved_by=_ACTOR,
            )
        )
        write_client = FakeWriteClient()
        capability_store = FakeCapabilityStore(
            evidence={Capability.METADATA_UPDATE: _restricted_evidence(Capability.METADATA_UPDATE)}
        )
        service = self._service(
            links=links,
            snapshots=snapshots,
            sync_ops=FakeSyncOperationStore(),
            remotes=FakeRemoteSnapshotStore(),
            metadata=metadata,
            capability_store=capability_store,
            connections=FakeConnectionStore(),
            data_api=FakeDataApiClient(),
            write_client=write_client,
        )
        operations = await service.apply_snapshot(workspace_id=_WORKSPACE, video_id=link.video_id)
        assert len(operations) == 1
        assert operations[0].status == SyncOperationStatus.MANUAL_FALLBACK
        # The write client was never actually called.
        assert write_client.remote_title == "Old Title"
        assert snapshot.id == operations[0].applied_snapshot_id

    async def test_successful_write_is_readback_verified(self) -> None:
        links = FakeLinkStore()
        link = await links.create(
            NewYoutubeVideoLink(
                workspace_id=_WORKSPACE,
                video_id=uuid.uuid4(),
                channel_id=_CHANNEL,
                youtube_video_id="yt-video-1",
            )
        )
        snapshots = FakeSnapshotStore()
        metadata = FakeMetadataStore()
        metadata_version = await metadata.create(
            NewMetadataVersion(
                workspace_id=_WORKSPACE,
                video_id=link.video_id,
                title="New Title",
                description="New description",
                tags=("a",),
                category="22",
                disclosure_altered=False,
                disclosure_synthetic=False,
                rationale="r",
            )
        )
        await snapshots.create(
            NewPublishSnapshot(
                workspace_id=_WORKSPACE,
                video_id=link.video_id,
                script_version_id=uuid.uuid4(),
                metadata_version_id=metadata_version.id,
                chapter_version_id=None,
                thumbnail_variant_id=None,
                disclosure_altered=False,
                disclosure_synthetic=False,
                scheduled_at=None,
                approved_by=_ACTOR,
            )
        )
        capability_store = FakeCapabilityStore(
            evidence={Capability.METADATA_UPDATE: _available_evidence(Capability.METADATA_UPDATE)}
        )
        service = self._service(
            links=links,
            snapshots=snapshots,
            sync_ops=FakeSyncOperationStore(),
            remotes=FakeRemoteSnapshotStore(),
            metadata=metadata,
            capability_store=capability_store,
            connections=FakeConnectionStore(),
            data_api=FakeDataApiClient(),
            write_client=FakeWriteClient(),
        )
        operations = await service.apply_snapshot(workspace_id=_WORKSPACE, video_id=link.video_id)
        assert operations[0].status == SyncOperationStatus.SUCCEEDED
        assert operations[0].readback_verified is True

        refetched = await links.get_for_video(workspace_id=_WORKSPACE, video_id=link.video_id)
        assert refetched is not None
        assert refetched.sync_state == SyncState.SYNCED

    async def test_drift_is_flagged_never_silently_resolved(self) -> None:
        links = FakeLinkStore()
        link = await links.create(
            NewYoutubeVideoLink(
                workspace_id=_WORKSPACE,
                video_id=uuid.uuid4(),
                channel_id=_CHANNEL,
                youtube_video_id="yt-video-1",
            )
        )
        await links.update_sync_state(
            workspace_id=_WORKSPACE, link_id=link.id, sync_state=SyncState.PENDING_SYNC
        )
        await links.update_sync_state(
            workspace_id=_WORKSPACE, link_id=link.id, sync_state=SyncState.SYNCED
        )
        snapshots = FakeSnapshotStore()
        metadata = FakeMetadataStore()
        metadata_version = await metadata.create(
            NewMetadataVersion(
                workspace_id=_WORKSPACE,
                video_id=link.video_id,
                title="Local Title",
                description="D",
                tags=(),
                category=None,
                disclosure_altered=False,
                disclosure_synthetic=False,
                rationale="r",
            )
        )
        await snapshots.create(
            NewPublishSnapshot(
                workspace_id=_WORKSPACE,
                video_id=link.video_id,
                script_version_id=uuid.uuid4(),
                metadata_version_id=metadata_version.id,
                chapter_version_id=None,
                thumbnail_variant_id=None,
                disclosure_altered=False,
                disclosure_synthetic=False,
                scheduled_at=None,
                approved_by=_ACTOR,
            )
        )
        # The fake write client always reports "Old Title" - different from
        # the snapshot's "Local Title", so this must register as drift.
        service = self._service(
            links=links,
            snapshots=snapshots,
            sync_ops=FakeSyncOperationStore(),
            remotes=FakeRemoteSnapshotStore(),
            metadata=metadata,
            capability_store=FakeCapabilityStore(),
            connections=FakeConnectionStore(),
            data_api=FakeDataApiClient(),
            write_client=FakeWriteClient(remote_title="Old Title"),
        )
        drifted = await service.detect_drift(workspace_id=_WORKSPACE, video_id=link.video_id)
        assert drifted is True

        refetched = await links.get_for_video(workspace_id=_WORKSPACE, video_id=link.video_id)
        assert refetched is not None
        assert refetched.sync_state == SyncState.DRIFT_DETECTED

        # Resolving with "ignore" leaves it flagged - never silently cleared.
        await service.resolve_drift(
            workspace_id=_WORKSPACE,
            video_id=link.video_id,
            mode=DriftResolutionMode.IGNORE,
        )
        still_flagged = await links.get_for_video(workspace_id=_WORKSPACE, video_id=link.video_id)
        assert still_flagged is not None
        assert still_flagged.sync_state == SyncState.DRIFT_DETECTED

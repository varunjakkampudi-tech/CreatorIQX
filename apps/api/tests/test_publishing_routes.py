"""HTTP behaviour of the Phase 1D publishing routes: QA, approval, YouTube
link/sync and drift resolution (spec §3, §4 features 12-14, Phase 1D P1D-05).

Same approach as ``test_phase1c_routes.py``: the real app factory, with
in-memory session/access doubles and the same fakes already proven in
``test_publishing_services.py`` standing in for every publishing/youtube
port - no real database needed. Fakes are duplicated here rather than
imported, per that file's own recorded convention (no precedent in this
suite for importing fixtures across test modules).

The YouTube-sync routes are wired only when ``settings.youtube_oauth_client_id``
is set (same gate as every other YouTube route - see ``main.py``'s
``_wire_youtube``), so this suite sets it and a dummy encryption key to get
``create_app`` to include the router, then overrides every service it wired
with fakes afterward, exactly like ``test_cross_tenant.py`` already does for
the session/access services it replaces post-construction.
"""

from __future__ import annotations

import base64
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app
from creatoriqx_api.modules.content.application.ports import (
    NewChapterVersion,
    NewMetadataVersion,
    NewScriptVersion,
)
from creatoriqx_api.modules.content.domain.chapters import Chapter, ChapterVersion
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion
from creatoriqx_api.modules.content.domain.script import ScriptAuthor, ScriptVersion
from creatoriqx_api.modules.identity.api.dependencies import CSRF_HEADER
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore
from creatoriqx_api.modules.planning.application.ports import NewVideo
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
from creatoriqx_api.modules.publishing.domain.remote_snapshot import RemoteSnapshot
from creatoriqx_api.modules.publishing.domain.snapshot import PublishSnapshot
from creatoriqx_api.modules.publishing.domain.sync_operation import SyncOperation
from creatoriqx_api.modules.publishing.domain.sync_state import SyncState
from creatoriqx_api.modules.publishing.domain.video_link import YoutubeVideoLink
from creatoriqx_api.modules.workspaces.application.access_service import WorkspaceAccessService
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.modules.workspaces.infrastructure.memory_access_store import (
    InMemoryWorkspaceAccessStore,
)
from creatoriqx_api.modules.youtube.application.ports import ActiveConnection, VideoStats
from creatoriqx_api.modules.youtube.domain.connection import (
    ChannelInfo,
    ConnectedChannel,
    OAuthTokens,
)
from creatoriqx_api.settings import Settings


def _now() -> datetime:
    return datetime.now(UTC)


# --- fakes (duplicated from test_publishing_services.py) --------------------


@dataclass
class FakeScriptStore:
    versions: dict[uuid.UUID, ScriptVersion] = field(default_factory=dict)

    async def create(self, version: NewScriptVersion) -> ScriptVersion:
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

POLICY = SessionPolicy(idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12))
SESSION_COOKIE = "__Host-creatoriqx_session"
WORKSPACE_ID = uuid.UUID(int=701)
CHANNEL_ID = uuid.UUID(int=702)
EDITOR_ID = uuid.UUID(int=801)
VIEWER_ID = uuid.UUID(int=802)

_DUMMY_KEY = base64.b64encode(b"0" * 32).decode()


@dataclass
class Harness:
    client: TestClient
    videos: FakeVideoStore
    scripts: FakeScriptStore
    metadata: FakeMetadataStore
    chapters: FakeChapterStore
    links: FakeLinkStore
    capability_store: FakeCapabilityStore
    write_client: FakeWriteClient


def _settings() -> Settings:
    return Settings(
        database_app_url=SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        redis_url=SecretStr("redis://localhost:1/0"),
        # Gates _wire_youtube so main.py also includes youtube_sync_router;
        # every service it builds is overridden with fakes just below.
        youtube_oauth_client_id="test-yt-client",
        youtube_oauth_client_secret=SecretStr("test-yt-secret"),
        token_encryption_key=SecretStr(_DUMMY_KEY),
    )


@pytest.fixture
def harness() -> Iterator[Harness]:
    app = create_app(_settings(), checks=[])

    store = InMemoryKeyValueStore()
    app.state.key_value_store = store
    app.state.session_service = SessionService(store, POLICY)
    access = InMemoryWorkspaceAccessStore()
    access.grant(
        WorkspaceAccess(workspace_id=WORKSPACE_ID, name="workspace", role=Role.EDITOR), EDITOR_ID
    )
    access.grant(
        WorkspaceAccess(workspace_id=WORKSPACE_ID, name="workspace", role=Role.VIEWER), VIEWER_ID
    )
    app.state.workspace_access_service = WorkspaceAccessService(access)

    scripts, metadata, chapters = FakeScriptStore(), FakeMetadataStore(), FakeChapterStore()
    videos = FakeVideoStore()
    links, remotes, snapshots, sync_ops = (
        FakeLinkStore(),
        FakeRemoteSnapshotStore(),
        FakeSnapshotStore(),
        FakeSyncOperationStore(),
    )
    capability_store = FakeCapabilityStore()
    connections, data_api, write_client = (
        FakeConnectionStore(),
        FakeDataApiClient(),
        FakeWriteClient(),
    )

    qa_service = QaService(
        script_store=scripts,
        metadata_store=metadata,
        chapter_store=chapters,
        video_link_store=links,
        remote_snapshot_store=remotes,
    )
    app.state.qa_service = qa_service
    app.state.approval_service = ApprovalService(
        qa_service=qa_service,
        script_store=scripts,
        metadata_store=metadata,
        chapter_store=chapters,
        snapshot_store=snapshots,
        video_store=videos,
    )
    capability_service = CapabilityService(capability_store)
    app.state.capability_service = capability_service
    app.state.youtube_sync_service = YoutubeSyncService(
        link_store=links,
        snapshot_store=snapshots,
        sync_op_store=sync_ops,
        remote_snapshot_store=remotes,
        metadata_store=metadata,
        capabilities=capability_service,
        connection_store=connections,
        data_api_client=data_api,
        write_client=write_client,
    )

    with TestClient(app, base_url="https://testserver") as built:
        yield Harness(
            client=built,
            videos=videos,
            scripts=scripts,
            metadata=metadata,
            chapters=chapters,
            links=links,
            capability_store=capability_store,
            write_client=write_client,
        )


async def _sign_in(client: TestClient, *, user_id: uuid.UUID) -> str:
    app: FastAPI = client.app  # type: ignore[assignment]
    service: SessionService = app.state.session_service
    session = await service.create(
        subject=str(user_id),
        email="creator@example.com",
        user_id=user_id,
        workspace_id=WORKSPACE_ID,
    )
    client.cookies.set(SESSION_COOKIE, session.id)
    return session.csrf_token


async def _seed_video(videos: FakeVideoStore, *, status: VideoStatus) -> Video:
    return await videos.create(
        NewVideo(
            workspace_id=WORKSPACE_ID,
            channel_id=CHANNEL_ID,
            plan_id=None,
            title="A Video",
            status=status,
        ),
        actor_user_id=EDITOR_ID,
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
            workspace_id=WORKSPACE_ID,
            video_id=video_id,
            variant_label="A",
            author=ScriptAuthor.HUMAN,
            hook="A hook that is definitely long enough to pass QA.",
            outline="outline",
            body="body",
        )
    )
    await metadata.create(
        NewMetadataVersion(
            workspace_id=WORKSPACE_ID,
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
            workspace_id=WORKSPACE_ID,
            video_id=video_id,
            transcript_id=uuid.uuid4(),
            chapters=(Chapter(0, "Intro"), Chapter(30, "Middle"), Chapter(90, "End")),
        )
    )


# --- QA -----------------------------------------------------------------


async def test_qa_run_on_an_incomplete_video_returns_specific_failures(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=EDITOR_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.DRAFTING)

    response = harness.client.post(
        f"/api/v1/videos/{video.id}/qa/run",
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "qa-run-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    failing_ids = {check["id"] for check in body["checks"] if not check["passed"]}
    assert "title" in failing_ids
    assert "hook" in failing_ids


async def test_qa_run_without_idempotency_key_is_refused(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=EDITOR_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.DRAFTING)

    response = harness.client.post(f"/api/v1/videos/{video.id}/qa/run", headers={CSRF_HEADER: csrf})
    assert response.status_code == 400
    assert response.json()["type"] == "/problems/idempotency-key-required"


async def test_viewer_cannot_run_qa(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=VIEWER_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.DRAFTING)

    response = harness.client.post(
        f"/api/v1/videos/{video.id}/qa/run",
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "qa-run-2"},
    )
    assert response.status_code == 403


# --- approval -------------------------------------------------------------


async def test_approve_before_qa_passes_is_refused(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=EDITOR_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)
    # No artifacts seeded - QA must fail on title/hook/description.

    response = harness.client.post(
        f"/api/v1/videos/{video.id}/approve",
        json={},
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "approve-1"},
    )
    assert response.status_code == 422
    assert response.json()["type"] == "/problems/qa-not-passed"


async def test_approving_twice_without_an_edit_is_idempotent(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=EDITOR_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)
    await _seed_clean_artifacts(
        video_id=video.id,
        scripts=harness.scripts,
        metadata=harness.metadata,
        chapters=harness.chapters,
    )

    first = harness.client.post(
        f"/api/v1/videos/{video.id}/approve",
        json={},
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "approve-2"},
    )
    assert first.status_code == 201
    second = harness.client.post(
        f"/api/v1/videos/{video.id}/approve",
        json={},
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "approve-3"},
    )
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    snapshot = harness.client.get(f"/api/v1/videos/{video.id}/snapshot")
    assert snapshot.status_code == 200
    assert snapshot.json()["id"] == first.json()["id"]


async def test_viewer_cannot_approve(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=VIEWER_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)

    response = harness.client.post(
        f"/api/v1/videos/{video.id}/approve",
        json={},
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "approve-4"},
    )
    assert response.status_code == 403


async def test_snapshot_not_found_before_any_approval(harness: Harness) -> None:
    await _sign_in(harness.client, user_id=VIEWER_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)

    response = harness.client.get(f"/api/v1/videos/{video.id}/snapshot")
    assert response.status_code == 404


# --- YouTube link/sync -----------------------------------------------------


async def test_linking_a_video_already_linked_elsewhere_is_refused(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=EDITOR_ID)
    await harness.links.create(
        NewYoutubeVideoLink(
            workspace_id=WORKSPACE_ID,
            video_id=uuid.uuid4(),
            channel_id=CHANNEL_ID,
            youtube_video_id="yt-video-1",
        )
    )
    video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)

    response = harness.client.post(
        f"/api/v1/videos/{video.id}/youtube/link",
        json={"channel_id": str(CHANNEL_ID), "youtube_video_id": "yt-video-1"},
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "link-1"},
    )
    assert response.status_code == 409
    assert response.json()["type"] == "/problems/youtube-video-link-conflict"


async def test_linking_then_reading_status(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=EDITOR_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)

    linked = harness.client.post(
        f"/api/v1/videos/{video.id}/youtube/link",
        json={"channel_id": str(CHANNEL_ID), "youtube_video_id": "yt-video-1"},
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "link-2"},
    )
    assert linked.status_code == 201
    assert linked.json()["sync_state"] == "linked"

    status = harness.client.get(f"/api/v1/videos/{video.id}/youtube/status")
    assert status.status_code == 200
    assert status.json()["youtube_video_id"] == "yt-video-1"


async def test_viewer_cannot_link_a_video(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=VIEWER_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)

    response = harness.client.post(
        f"/api/v1/videos/{video.id}/youtube/link",
        json={"channel_id": str(CHANNEL_ID), "youtube_video_id": "yt-video-1"},
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "link-3"},
    )
    assert response.status_code == 403


async def test_drift_resolution_rejects_an_invalid_mode(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=EDITOR_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)
    await harness.links.create(
        NewYoutubeVideoLink(
            workspace_id=WORKSPACE_ID,
            video_id=video.id,
            channel_id=CHANNEL_ID,
            youtube_video_id="yt-video-1",
        )
    )

    response = harness.client.post(
        f"/api/v1/videos/{video.id}/youtube/drift/resolve",
        json={"mode": "not_a_real_mode"},
        headers={CSRF_HEADER: csrf, "Idempotency-Key": "drift-1"},
    )
    assert response.status_code == 422


async def test_drift_resolution_accepts_each_explicit_mode(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=EDITOR_ID)

    # A fresh linked video per mode: resolving "adopt_remote"/"overwrite_remote"
    # moves the link's sync state linked -> pending_sync (YoutubeSyncService.
    # resolve_drift), so re-resolving the *same* link a second time would be a
    # pending_sync -> pending_sync transition, which the sync-state machine
    # correctly refuses (spec §3's explicit, one-way drift resolution). Each
    # mode therefore gets its own link, starting from the same "linked" state.
    for i, mode in enumerate(("ignore", "adopt_remote", "overwrite_remote")):
        video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)
        await harness.links.create(
            NewYoutubeVideoLink(
                workspace_id=WORKSPACE_ID,
                video_id=video.id,
                channel_id=CHANNEL_ID,
                youtube_video_id=f"yt-video-drift-{i}",
            )
        )

        response = harness.client.post(
            f"/api/v1/videos/{video.id}/youtube/drift/resolve",
            json={"mode": mode},
            headers={CSRF_HEADER: csrf, "Idempotency-Key": f"drift-resolve-{i}"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["mode"] == mode


async def test_sync_without_idempotency_key_is_refused(harness: Harness) -> None:
    csrf = await _sign_in(harness.client, user_id=EDITOR_ID)
    video = await _seed_video(harness.videos, status=VideoStatus.IN_REVIEW)

    response = harness.client.post(
        f"/api/v1/videos/{video.id}/youtube/sync", headers={CSRF_HEADER: csrf}
    )
    assert response.status_code == 400
    assert response.json()["type"] == "/problems/idempotency-key-required"

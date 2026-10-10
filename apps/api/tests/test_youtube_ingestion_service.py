"""Tests for channel ingestion (spec §3): discovery via the uploads playlist,
never ``search.list``, and quota reservation before each call.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from creatoriqx_api.modules.youtube.application.ingestion_service import ChannelIngestionService
from creatoriqx_api.modules.youtube.application.ports import ActiveConnection, VideoStats
from creatoriqx_api.modules.youtube.domain.connection import ChannelInfo
from creatoriqx_api.modules.youtube.domain.errors import QuotaExhaustedError

_WORKSPACE = uuid.uuid4()
_CHANNEL = uuid.uuid4()

_ACTIVE_CONNECTION = ActiveConnection(
    connection_id=uuid.uuid4(),
    channel_id=_CHANNEL,
    youtube_channel_id="UC123",
    uploads_playlist_id="UU123",
    access_token="fake-access",
    access_token_expires_at=datetime.now(UTC),
    refresh_token="fake-refresh",
)


@dataclass
class FakeConnectionStore:
    active_connection: ActiveConnection = field(default_factory=lambda: _ACTIVE_CONNECTION)
    channel_updates: list[ChannelInfo] = field(default_factory=list)

    async def save_connection(self, **kwargs: object) -> object:
        raise NotImplementedError

    async def list_channels(self, workspace_id: uuid.UUID) -> list[object]:
        raise NotImplementedError

    async def get_active_connection(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> ActiveConnection:
        return self.active_connection

    async def update_access_token(self, **kwargs: object) -> None:
        raise NotImplementedError

    async def disconnect(self, **kwargs: object) -> None:
        raise NotImplementedError

    async def update_channel_stats(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID, channel: ChannelInfo
    ) -> None:
        self.channel_updates.append(channel)


@dataclass
class FakeVideoStore:
    upserted: list[VideoStats] = field(default_factory=list)

    async def upsert_videos(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID, videos: list[VideoStats]
    ) -> None:
        self.upserted.extend(videos)

    async def list_videos(self, **kwargs: object) -> list[object]:
        raise NotImplementedError


@dataclass
class FakeDataApiClient:
    channel_info: ChannelInfo
    video_ids: list[str] = field(default_factory=list)
    stats_by_id: dict[str, VideoStats] = field(default_factory=dict)
    list_uploads_calls: int = 0

    async def get_own_channel(self, access_token: str, *, workspace_id: uuid.UUID) -> ChannelInfo:
        return self.channel_info

    async def list_uploads(
        self,
        access_token: str,
        *,
        workspace_id: uuid.UUID,
        uploads_playlist_id: str,
        limit: int,
    ) -> list[str]:
        self.list_uploads_calls += 1
        return self.video_ids[:limit]

    async def list_video_stats(
        self, access_token: str, *, workspace_id: uuid.UUID, video_ids: list[str]
    ) -> list[VideoStats]:
        return [self.stats_by_id[vid] for vid in video_ids]


@dataclass
class FakeQuotaLedger:
    reservations: list[tuple[str, int]] = field(default_factory=list)
    exhausted_after: int | None = None

    async def reserve(
        self, *, workspace_id: uuid.UUID, provider: str, endpoint: str, units: int
    ) -> None:
        if self.exhausted_after is not None and len(self.reservations) >= self.exhausted_after:
            raise QuotaExhaustedError()
        self.reservations.append((endpoint, units))


def _make_video_stats(video_id: str) -> VideoStats:
    return VideoStats(
        youtube_video_id=video_id,
        title=f"Title {video_id}",
        description="desc",
        published_at=datetime.now(UTC),
        duration_seconds=120,
        view_count=100,
        like_count=10,
        comment_count=1,
    )


_CHANNEL_INFO_WITH_UPLOADS = ChannelInfo(
    youtube_channel_id="UC123",
    title="Test Channel",
    thumbnail_url=None,
    subscriber_count=100,
    view_count=1000,
    video_count=2,
    uploads_playlist_id="UU123",
)

_CHANNEL_INFO_NO_UPLOADS = ChannelInfo(
    youtube_channel_id="UC123",
    title="Brand New Channel",
    thumbnail_url=None,
    subscriber_count=0,
    view_count=0,
    video_count=0,
    uploads_playlist_id=None,
)


class TestIngest:
    async def test_ingests_videos_from_the_uploads_playlist(self) -> None:
        video_ids = ["v1", "v2"]
        client = FakeDataApiClient(
            channel_info=_CHANNEL_INFO_WITH_UPLOADS,
            video_ids=video_ids,
            stats_by_id={vid: _make_video_stats(vid) for vid in video_ids},
        )
        video_store = FakeVideoStore()
        service = ChannelIngestionService(
            connection_store=FakeConnectionStore(),
            video_store=video_store,
            data_api_client=client,
            quota_ledger=FakeQuotaLedger(),
        )
        count = await service.ingest(workspace_id=_WORKSPACE, channel_id=_CHANNEL)
        assert count == 2
        assert {v.youtube_video_id for v in video_store.upserted} == {"v1", "v2"}
        assert client.list_uploads_calls == 1

    async def test_channel_with_no_uploads_playlist_ingests_zero(self) -> None:
        client = FakeDataApiClient(channel_info=_CHANNEL_INFO_NO_UPLOADS)
        service = ChannelIngestionService(
            connection_store=FakeConnectionStore(),
            video_store=FakeVideoStore(),
            data_api_client=client,
            quota_ledger=FakeQuotaLedger(),
        )
        count = await service.ingest(workspace_id=_WORKSPACE, channel_id=_CHANNEL)
        assert count == 0
        assert client.list_uploads_calls == 0

    async def test_always_refreshes_the_channels_own_stats(self) -> None:
        connection_store = FakeConnectionStore()
        client = FakeDataApiClient(channel_info=_CHANNEL_INFO_NO_UPLOADS)
        service = ChannelIngestionService(
            connection_store=connection_store,
            video_store=FakeVideoStore(),
            data_api_client=client,
            quota_ledger=FakeQuotaLedger(),
        )
        await service.ingest(workspace_id=_WORKSPACE, channel_id=_CHANNEL)
        assert len(connection_store.channel_updates) == 1

    async def test_reserves_quota_before_each_api_call(self) -> None:
        video_ids = ["v1"]
        client = FakeDataApiClient(
            channel_info=_CHANNEL_INFO_WITH_UPLOADS,
            video_ids=video_ids,
            stats_by_id={"v1": _make_video_stats("v1")},
        )
        ledger = FakeQuotaLedger()
        service = ChannelIngestionService(
            connection_store=FakeConnectionStore(),
            video_store=FakeVideoStore(),
            data_api_client=client,
            quota_ledger=ledger,
        )
        await service.ingest(workspace_id=_WORKSPACE, channel_id=_CHANNEL)
        endpoints = [endpoint for endpoint, _units in ledger.reservations]
        assert endpoints == ["channels.list", "playlistItems.list", "videos.list"]

    async def test_quota_exhaustion_stops_ingestion(self) -> None:
        client = FakeDataApiClient(channel_info=_CHANNEL_INFO_WITH_UPLOADS, video_ids=["v1"])
        ledger = FakeQuotaLedger(exhausted_after=1)
        service = ChannelIngestionService(
            connection_store=FakeConnectionStore(),
            video_store=FakeVideoStore(),
            data_api_client=client,
            quota_ledger=ledger,
        )
        with pytest.raises(QuotaExhaustedError):
            await service.ingest(workspace_id=_WORKSPACE, channel_id=_CHANNEL)

    async def test_pages_video_stats_in_batches_of_fifty(self) -> None:
        video_ids = [f"v{i}" for i in range(75)]
        client = FakeDataApiClient(
            channel_info=_CHANNEL_INFO_WITH_UPLOADS,
            video_ids=video_ids,
            stats_by_id={vid: _make_video_stats(vid) for vid in video_ids},
        )
        video_store = FakeVideoStore()
        service = ChannelIngestionService(
            connection_store=FakeConnectionStore(),
            video_store=video_store,
            data_api_client=client,
            quota_ledger=FakeQuotaLedger(),
            upload_limit=75,
        )
        count = await service.ingest(workspace_id=_WORKSPACE, channel_id=_CHANNEL)
        assert count == 75
        assert len(video_store.upserted) == 75

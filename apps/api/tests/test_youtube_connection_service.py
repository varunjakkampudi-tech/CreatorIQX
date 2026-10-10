"""Tests for the YouTube connect flow (spec §3, §10), with fake adapters."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore
from creatoriqx_api.modules.youtube.application.connection_service import (
    ChannelConnectionService,
)
from creatoriqx_api.modules.youtube.application.ports import ActiveConnection
from creatoriqx_api.modules.youtube.domain.connection import (
    ChannelInfo,
    ConnectedChannel,
    ConnectionStatus,
    OAuthTokens,
)
from creatoriqx_api.modules.youtube.domain.errors import (
    ChannelNotConnectedError,
    YouTubeOAuthStateMismatchError,
)

_WORKSPACE = uuid.uuid4()
_USER = uuid.uuid4()
_CHANNEL_INFO = ChannelInfo(
    youtube_channel_id="UC123",
    title="Test Channel",
    thumbnail_url="https://example.com/thumb.jpg",
    subscriber_count=1000,
    view_count=50_000,
    video_count=20,
    uploads_playlist_id="UU123",
)


@dataclass
class FakeOAuthProvider:
    exchange_error: Exception | None = None
    last_code: str | None = None

    def build_authorization_url(self, redirect_uri: str, state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}&redirect_uri={redirect_uri}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        self.last_code = code
        if self.exchange_error:
            raise self.exchange_error
        return OAuthTokens(
            access_token="fake-access",
            refresh_token="fake-refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes=("https://www.googleapis.com/auth/youtube.readonly",),
        )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        raise NotImplementedError


@dataclass
class FakeDataApiClient:
    channel: ChannelInfo = field(default_factory=lambda: _CHANNEL_INFO)

    async def get_own_channel(self, access_token: str, *, workspace_id: uuid.UUID) -> ChannelInfo:
        return self.channel

    async def list_uploads(self, *args: object, **kwargs: object) -> list[str]:
        raise NotImplementedError

    async def list_video_stats(self, *args: object, **kwargs: object) -> list[object]:
        raise NotImplementedError


@dataclass
class FakeConnectionStore:
    channels: dict[uuid.UUID, ConnectedChannel] = field(default_factory=dict)
    disconnected: list[uuid.UUID] = field(default_factory=list)

    async def save_connection(
        self,
        *,
        workspace_id: uuid.UUID,
        connected_by_user_id: uuid.UUID,
        tokens: OAuthTokens,
        channel: ChannelInfo,
    ) -> ConnectedChannel:
        channel_id = uuid.uuid4()
        connected = ConnectedChannel(
            id=channel_id,
            youtube_channel_id=channel.youtube_channel_id,
            title=channel.title,
            thumbnail_url=channel.thumbnail_url,
            subscriber_count=channel.subscriber_count,
            video_count=channel.video_count,
            last_synced_at=datetime.now(UTC),
            connection_status=ConnectionStatus.ACTIVE,
        )
        self.channels[channel_id] = connected
        return connected

    async def list_channels(self, workspace_id: uuid.UUID) -> list[ConnectedChannel]:
        return list(self.channels.values())

    async def get_active_connection(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> ActiveConnection:
        raise NotImplementedError

    async def update_access_token(self, *, connection_id: uuid.UUID, tokens: OAuthTokens) -> None:
        raise NotImplementedError

    async def disconnect(self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID) -> None:
        if channel_id not in self.channels:
            raise ChannelNotConnectedError()
        self.disconnected.append(channel_id)
        del self.channels[channel_id]

    async def update_channel_stats(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID, channel: ChannelInfo
    ) -> None:
        raise NotImplementedError


def _service(
    oauth_provider: FakeOAuthProvider | None = None,
    data_api_client: FakeDataApiClient | None = None,
    store: FakeConnectionStore | None = None,
    state_store: InMemoryKeyValueStore | None = None,
) -> tuple[ChannelConnectionService, FakeConnectionStore, InMemoryKeyValueStore]:
    store = store or FakeConnectionStore()
    state_store = state_store or InMemoryKeyValueStore()
    service = ChannelConnectionService(
        oauth_provider=oauth_provider or FakeOAuthProvider(),
        data_api_client=data_api_client or FakeDataApiClient(),
        store=store,
        state_store=state_store,
        flow_ttl_seconds=600,
    )
    return service, store, state_store


class TestStartConnect:
    async def test_returns_authorization_url_with_a_state(self) -> None:
        service, _store, _state_store = _service()
        url = await service.start_connect(
            workspace_id=_WORKSPACE, user_id=_USER, redirect_uri="http://localhost/cb"
        )
        assert "accounts.google.com" in url
        assert "state=" in url

    async def test_each_call_generates_a_unique_state(self) -> None:
        service, _store, _state_store = _service()
        url1 = await service.start_connect(
            workspace_id=_WORKSPACE, user_id=_USER, redirect_uri="http://localhost/cb"
        )
        url2 = await service.start_connect(
            workspace_id=_WORKSPACE, user_id=_USER, redirect_uri="http://localhost/cb"
        )
        assert url1 != url2


class TestCompleteConnect:
    async def test_valid_state_completes_the_connection(self) -> None:
        service, _store, _state_store = _service()
        url = await service.start_connect(
            workspace_id=_WORKSPACE, user_id=_USER, redirect_uri="http://localhost/cb"
        )
        state = url.split("state=")[1].split("&")[0]

        channel = await service.complete_connect(
            state=state, code="auth-code", workspace_id=_WORKSPACE, user_id=_USER
        )
        assert channel.youtube_channel_id == "UC123"
        assert channel.title == "Test Channel"
        assert len(_store.channels) == 1

    async def test_state_is_single_use(self) -> None:
        service, _store, _state_store = _service()
        url = await service.start_connect(
            workspace_id=_WORKSPACE, user_id=_USER, redirect_uri="http://localhost/cb"
        )
        state = url.split("state=")[1].split("&")[0]
        await service.complete_connect(
            state=state, code="auth-code", workspace_id=_WORKSPACE, user_id=_USER
        )
        with pytest.raises(YouTubeOAuthStateMismatchError):
            await service.complete_connect(
                state=state, code="auth-code", workspace_id=_WORKSPACE, user_id=_USER
            )

    async def test_unknown_state_is_rejected(self) -> None:
        service, _store, _state_store = _service()
        with pytest.raises(YouTubeOAuthStateMismatchError):
            await service.complete_connect(
                state="never-issued", code="auth-code", workspace_id=_WORKSPACE, user_id=_USER
            )

    async def test_state_issued_to_another_workspace_is_rejected(self) -> None:
        service, _store, _state_store = _service()
        url = await service.start_connect(
            workspace_id=_WORKSPACE, user_id=_USER, redirect_uri="http://localhost/cb"
        )
        state = url.split("state=")[1].split("&")[0]
        other_workspace = uuid.uuid4()
        with pytest.raises(YouTubeOAuthStateMismatchError):
            await service.complete_connect(
                state=state, code="auth-code", workspace_id=other_workspace, user_id=_USER
            )

    async def test_oauth_exchange_failure_propagates(self) -> None:
        from creatoriqx_api.modules.youtube.domain.errors import YouTubeOAuthError

        provider = FakeOAuthProvider(exchange_error=YouTubeOAuthError(detail="boom"))
        service, _store, _state_store = _service(oauth_provider=provider)
        url = await service.start_connect(
            workspace_id=_WORKSPACE, user_id=_USER, redirect_uri="http://localhost/cb"
        )
        state = url.split("state=")[1].split("&")[0]
        with pytest.raises(YouTubeOAuthError):
            await service.complete_connect(
                state=state, code="auth-code", workspace_id=_WORKSPACE, user_id=_USER
            )


class TestListAndDisconnect:
    async def test_list_channels_returns_connected_channels(self) -> None:
        service, _store, _state_store = _service()
        url = await service.start_connect(
            workspace_id=_WORKSPACE, user_id=_USER, redirect_uri="http://localhost/cb"
        )
        state = url.split("state=")[1].split("&")[0]
        await service.complete_connect(
            state=state, code="auth-code", workspace_id=_WORKSPACE, user_id=_USER
        )
        channels = await service.list_channels(_WORKSPACE)
        assert len(channels) == 1

    async def test_disconnect_removes_the_channel(self) -> None:
        service, store, _state_store = _service()
        url = await service.start_connect(
            workspace_id=_WORKSPACE, user_id=_USER, redirect_uri="http://localhost/cb"
        )
        state = url.split("state=")[1].split("&")[0]
        channel = await service.complete_connect(
            state=state, code="auth-code", workspace_id=_WORKSPACE, user_id=_USER
        )
        await service.disconnect(workspace_id=_WORKSPACE, channel_id=channel.id)
        assert channel.id in store.disconnected

    async def test_disconnecting_an_unknown_channel_raises(self) -> None:
        service, _store, _state_store = _service()
        with pytest.raises(ChannelNotConnectedError):
            await service.disconnect(workspace_id=_WORKSPACE, channel_id=uuid.uuid4())

"""Orchestrates the YouTube connect flow (spec §3, §10).

A separate OAuth 2.0 flow from login: a short-lived ``state`` ties the
callback back to the workspace and user who started it (mirrors
``identity.application`` login-flow handling, stored in the same kind of
key-value store), never a cookie shared with the login session.
"""

from __future__ import annotations

import secrets
import uuid

from creatoriqx_api.modules.identity.application.ports import KeyValueStore
from creatoriqx_api.modules.youtube.application.ports import (
    ChannelConnectionStore,
    YouTubeDataApiClient,
    YouTubeOAuthProvider,
)
from creatoriqx_api.modules.youtube.domain.connection import ConnectedChannel
from creatoriqx_api.modules.youtube.domain.errors import YouTubeOAuthStateMismatchError

_STATE_KEY_PREFIX = "youtube:connect:state:"


class ChannelConnectionService:
    """Starts and completes a workspace's YouTube connection."""

    def __init__(
        self,
        *,
        oauth_provider: YouTubeOAuthProvider,
        data_api_client: YouTubeDataApiClient,
        store: ChannelConnectionStore,
        state_store: KeyValueStore,
        flow_ttl_seconds: int,
    ) -> None:
        self._oauth_provider = oauth_provider
        self._data_api_client = data_api_client
        self._store = store
        self._state_store = state_store
        self._flow_ttl_seconds = flow_ttl_seconds

    async def start_connect(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, redirect_uri: str
    ) -> str:
        """Record a connect attempt and return the URL to send the browser to."""
        state = secrets.token_urlsafe(32)
        await self._state_store.put(
            f"{_STATE_KEY_PREFIX}{state}",
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "redirect_uri": redirect_uri,
            },
            ttl_seconds=self._flow_ttl_seconds,
        )
        return self._oauth_provider.build_authorization_url(redirect_uri, state)

    async def complete_connect(
        self, *, state: str, code: str, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> ConnectedChannel:
        """Exchange the code, fetch the channel, and persist the connection."""
        # take(): a connect-state record is single-use, same as a login flow.
        record = await self._state_store.take(f"{_STATE_KEY_PREFIX}{state}")
        if record is None:
            raise YouTubeOAuthStateMismatchError()

        redirect_uri = record["redirect_uri"]
        if record["workspace_id"] != str(workspace_id):
            # The state was issued to a different workspace than the one
            # completing it - treat exactly like an unknown/expired state
            # rather than leaking which workspace it belonged to.
            raise YouTubeOAuthStateMismatchError()

        tokens = await self._oauth_provider.exchange_code(code, redirect_uri)
        channel = await self._data_api_client.get_own_channel(
            tokens.access_token, workspace_id=workspace_id
        )
        return await self._store.save_connection(
            workspace_id=workspace_id,
            connected_by_user_id=user_id,
            tokens=tokens,
            channel=channel,
        )

    async def list_channels(self, workspace_id: uuid.UUID) -> list[ConnectedChannel]:
        return await self._store.list_channels(workspace_id)

    async def disconnect(self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID) -> None:
        await self._store.disconnect(workspace_id=workspace_id, channel_id=channel_id)

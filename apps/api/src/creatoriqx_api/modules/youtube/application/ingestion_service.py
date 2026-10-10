"""Ingests a connected channel's own data from the YouTube Data API (spec §3).

Discovers videos through the channel's uploads playlist
(``channels.contentDetails.relatedPlaylists.uploads`` + ``playlistItems.list``),
never ``search.list`` (spec §3 explicit requirement). Every API call reserves
quota units first (spec §6 Quota management) so a workspace that is out of
quota fails fast with ``QuotaExhaustedError`` rather than partially ingesting.
"""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.youtube.application.ports import (
    ChannelConnectionStore,
    ChannelVideoStore,
    QuotaLedger,
    YouTubeDataApiClient,
)
from creatoriqx_api.modules.youtube.domain.connection import PROVIDER_GOOGLE_YOUTUBE

# Quota costs per the YouTube Data API v3 quota calculator (verify current
# units in docs/YOUTUBE_CAPABILITIES.md): channels.list=1, playlistItems.list=1
# per page, videos.list=1 per call (up to 50 ids). Charged per call made, not
# estimated up front, since playlist page count isn't known until fetched.
_PLAYLIST_ITEMS_ENDPOINT = "playlistItems.list"
_VIDEOS_LIST_ENDPOINT = "videos.list"
_VIDEOS_LIST_PAGE_SIZE = 50

# Phase 1A ingests enough recent uploads for a meaningful audit without
# unbounded quota use; the audit's "best/worst/gaps" findings (spec §4
# feature #2) don't need a channel's entire history on the first sync.
_DEFAULT_UPLOAD_LIMIT = 50


class ChannelIngestionService:
    """Refreshes one connected channel's stats and recent video stats."""

    def __init__(
        self,
        *,
        connection_store: ChannelConnectionStore,
        video_store: ChannelVideoStore,
        data_api_client: YouTubeDataApiClient,
        quota_ledger: QuotaLedger,
        upload_limit: int = _DEFAULT_UPLOAD_LIMIT,
    ) -> None:
        self._connection_store = connection_store
        self._video_store = video_store
        self._data_api_client = data_api_client
        self._quota_ledger = quota_ledger
        self._upload_limit = upload_limit

    async def ingest(self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID) -> int:
        """Refresh the channel's own stats and its recent videos. Returns the
        number of videos ingested.
        """
        connection = await self._connection_store.get_active_connection(
            workspace_id=workspace_id, channel_id=channel_id
        )

        await self._quota_ledger.reserve(
            workspace_id=workspace_id,
            provider=PROVIDER_GOOGLE_YOUTUBE,
            endpoint="channels.list",
            units=1,
        )
        channel_info = await self._data_api_client.get_own_channel(
            connection.access_token, workspace_id=workspace_id
        )
        await self._connection_store.update_channel_stats(
            workspace_id=workspace_id, channel_id=channel_id, channel=channel_info
        )

        if channel_info.uploads_playlist_id is None:
            # A channel with no uploads playlist has no uploads yet - a
            # legitimate state for a brand-new channel, not an error.
            return 0

        await self._quota_ledger.reserve(
            workspace_id=workspace_id,
            provider=PROVIDER_GOOGLE_YOUTUBE,
            endpoint=_PLAYLIST_ITEMS_ENDPOINT,
            units=1,
        )
        video_ids = await self._data_api_client.list_uploads(
            connection.access_token,
            workspace_id=workspace_id,
            uploads_playlist_id=channel_info.uploads_playlist_id,
            limit=self._upload_limit,
        )
        if not video_ids:
            return 0

        ingested = 0
        for page_start in range(0, len(video_ids), _VIDEOS_LIST_PAGE_SIZE):
            page = video_ids[page_start : page_start + _VIDEOS_LIST_PAGE_SIZE]
            await self._quota_ledger.reserve(
                workspace_id=workspace_id,
                provider=PROVIDER_GOOGLE_YOUTUBE,
                endpoint=_VIDEOS_LIST_ENDPOINT,
                units=1,
            )
            stats = await self._data_api_client.list_video_stats(
                connection.access_token, workspace_id=workspace_id, video_ids=page
            )
            await self._video_store.upsert_videos(
                workspace_id=workspace_id, channel_id=channel_id, videos=stats
            )
            ingested += len(stats)

        return ingested

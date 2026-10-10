"""HTTP adapter for the subset of the YouTube Data API v3 this module calls.

Verified against the current YouTube Data API v3 reference
(https://developers.google.com/youtube/v3/docs) at build time:

* ``channels.list(mine=true, part=snippet,statistics,contentDetails)`` for a
  connected channel's own identity, stats and uploads playlist id.
* ``playlistItems.list(playlistId=<uploads>, part=contentDetails)`` to
  discover videos - spec §3 explicitly requires the uploads playlist, never
  ``search.list``, which costs far more quota and is for public search.
* ``videos.list(id=<comma-joined ids>, part=snippet,contentDetails,statistics)``,
  up to 50 ids per call, for per-video metadata and stats.

Every call records its quota cost in ``docs/YOUTUBE_CAPABILITIES.md``; the
cost itself is reserved by the caller (``ChannelIngestionService``) before
the request is made, not by this client.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import httpx

from creatoriqx_api.modules.youtube.application.ports import VideoStats
from creatoriqx_api.modules.youtube.domain.connection import ChannelInfo
from creatoriqx_api.modules.youtube.domain.errors import YouTubeApiError
from creatoriqx_api.platform.logging import get_logger

_API_BASE = "https://www.googleapis.com/youtube/v3"
_PLAYLIST_ITEMS_PAGE_SIZE = 50
_logger = get_logger("creatoriqx.youtube.data_api")


class HttpYouTubeDataApiClient:
    """Calls the real YouTube Data API v3 over HTTPS."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def get_own_channel(self, access_token: str, *, workspace_id: uuid.UUID) -> ChannelInfo:
        data = await self._get(
            access_token,
            workspace_id=workspace_id,
            path="channels",
            params={"part": "snippet,statistics,contentDetails", "mine": "true"},
        )
        items = _list_of_dicts(data, "items")
        if not items:
            raise YouTubeApiError(detail="channels.list(mine=true) returned no channel")
        return _channel_info_from_item(items[0])

    async def list_uploads(
        self,
        access_token: str,
        *,
        workspace_id: uuid.UUID,
        uploads_playlist_id: str,
        limit: int,
    ) -> list[str]:
        video_ids: list[str] = []
        page_token: str | None = None
        while len(video_ids) < limit:
            params = {
                "part": "contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": str(min(_PLAYLIST_ITEMS_PAGE_SIZE, limit - len(video_ids))),
            }
            if page_token:
                params["pageToken"] = page_token
            data = await self._get(
                access_token, workspace_id=workspace_id, path="playlistItems", params=params
            )
            for item in _list_of_dicts(data, "items"):
                video_id = _str_or_none(_dict_get(item, "contentDetails").get("videoId"))
                if video_id:
                    video_ids.append(video_id)
            page_token = _str_or_none(data.get("nextPageToken"))
            if not page_token:
                break
        return video_ids[:limit]

    async def list_video_stats(
        self, access_token: str, *, workspace_id: uuid.UUID, video_ids: list[str]
    ) -> list[VideoStats]:
        if not video_ids:
            return []
        data = await self._get(
            access_token,
            workspace_id=workspace_id,
            path="videos",
            params={
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(video_ids),
            },
        )
        return [_video_stats_from_item(item) for item in _list_of_dicts(data, "items")]

    async def _get(
        self, access_token: str, *, workspace_id: uuid.UUID, path: str, params: dict[str, str]
    ) -> dict[str, object]:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{_API_BASE}/{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=self._timeout_seconds,
                )
            except httpx.HTTPError as exc:
                raise YouTubeApiError(detail=f"HTTP error calling {path}: {exc}") from exc
        if resp.status_code != 200:
            _logger.warning(
                "youtube_api_error",
                workspace_id=str(workspace_id),
                path=path,
                status_code=resp.status_code,
            )
            raise YouTubeApiError(
                detail=f"YouTube API {path} returned {resp.status_code}: {resp.text[:200]}"
            )
        body = resp.json()
        return body if isinstance(body, dict) else {}


def _list_of_dicts(container: dict[str, object], key: str) -> list[dict[str, object]]:
    """``container.get(key, [])`` narrowed to a list of dicts, for untyped JSON."""
    value = container.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_get(container: dict[str, object], key: str) -> dict[str, object]:
    """``container.get(key, {})`` narrowed back to a dict, for untyped JSON."""
    value = container.get(key, {})
    return value if isinstance(value, dict) else {}


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _channel_info_from_item(item: dict[str, object]) -> ChannelInfo:
    snippet = _dict_get(item, "snippet")
    statistics = _dict_get(item, "statistics")
    content_details = _dict_get(item, "contentDetails")
    related_playlists = _dict_get(content_details, "relatedPlaylists")
    thumbnails = _dict_get(snippet, "thumbnails")
    default_thumbnail = _dict_get(thumbnails, "default")
    return ChannelInfo(
        youtube_channel_id=str(item["id"]),
        title=str(snippet.get("title", "")),
        thumbnail_url=_str_or_none(default_thumbnail.get("url")),
        subscriber_count=_maybe_int(statistics.get("subscriberCount")),
        view_count=_maybe_int(statistics.get("viewCount")),
        video_count=_maybe_int(statistics.get("videoCount")),
        uploads_playlist_id=_str_or_none(related_playlists.get("uploads")),
    )


def _video_stats_from_item(item: dict[str, object]) -> VideoStats:
    snippet = _dict_get(item, "snippet")
    statistics = _dict_get(item, "statistics")
    content_details = _dict_get(item, "contentDetails")
    published_at_raw = snippet.get("publishedAt")
    return VideoStats(
        youtube_video_id=str(item["id"]),
        title=str(snippet.get("title", "")),
        description=str(snippet.get("description", "")),
        published_at=_parse_timestamp(published_at_raw),
        duration_seconds=_parse_iso8601_duration(content_details.get("duration")),
        view_count=_maybe_int(statistics.get("viewCount")),
        like_count=_maybe_int(statistics.get("likeCount")),
        comment_count=_maybe_int(statistics.get("commentCount")),
    )


def _maybe_int(value: object) -> int | None:
    # YouTube's statistics fields arrive as JSON strings (e.g. "12345"), never
    # as numbers - narrow explicitly rather than calling int() on `object`.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _parse_timestamp(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise YouTubeApiError(detail="video item missing snippet.publishedAt")
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _parse_iso8601_duration(raw: object) -> int | None:
    """Parse an ISO 8601 duration like ``PT4M13S`` into whole seconds."""
    if not isinstance(raw, str) or not raw.startswith("P"):
        return None
    # Only the time portion (hours/minutes/seconds) matters for a YouTube
    # video; days/weeks/months/years never appear in this field.
    time_part = raw.split("T", 1)[1] if "T" in raw else ""
    hours = minutes = seconds = 0
    number = ""
    for char in time_part:
        if char.isdigit():
            number += char
            continue
        value = int(number) if number else 0
        number = ""
        if char == "H":
            hours = value
        elif char == "M":
            minutes = value
        elif char == "S":
            seconds = value
    return hours * 3600 + minutes * 60 + seconds

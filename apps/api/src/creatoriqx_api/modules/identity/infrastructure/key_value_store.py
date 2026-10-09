"""KeyValueStore adapters (ADR 0010).

``RedisKeyValueStore`` is the runtime adapter: sessions must be shared by
every API worker and survive a restart. ``InMemoryKeyValueStore`` implements
the same contract for unit tests; it is not shared across processes and must
not be used in production.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from creatoriqx_api.modules.identity.application.ports import Clock, utc_now

if TYPE_CHECKING:
    from redis.asyncio import Redis


def _decode(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    return cast(dict[str, Any], json.loads(cast("str | bytes", raw)))


class RedisKeyValueStore:
    """JSON records in Redis, with Redis-enforced expiry."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def put(self, key: str, value: Mapping[str, Any], ttl_seconds: int) -> None:
        payload = json.dumps(dict(value), separators=(",", ":"), sort_keys=True)
        await self._client.set(key, payload, ex=ttl_seconds)

    async def get(self, key: str) -> dict[str, Any] | None:
        return _decode(await self._client.get(key))

    async def take(self, key: str) -> dict[str, Any] | None:
        # GETDEL is atomic: two concurrent callbacks cannot both use one flow.
        return _decode(await self._client.getdel(key))

    async def delete(self, key: str) -> None:
        await self._client.delete(key)


class InMemoryKeyValueStore:
    """Process-local store with the same semantics, for tests only."""

    def __init__(self, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._items: dict[str, tuple[datetime, dict[str, Any]]] = {}

    async def put(self, key: str, value: Mapping[str, Any], ttl_seconds: int) -> None:
        expires_at = self._clock() + timedelta(seconds=ttl_seconds)
        self._items[key] = (expires_at, dict(value))

    async def get(self, key: str) -> dict[str, Any] | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self._clock() >= expires_at:
            del self._items[key]
            return None
        return dict(value)

    async def take(self, key: str) -> dict[str, Any] | None:
        value = await self.get(key)
        self._items.pop(key, None)
        return value

    async def delete(self, key: str) -> None:
        self._items.pop(key, None)

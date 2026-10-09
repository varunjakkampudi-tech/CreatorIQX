"""RedisTokenBucketLimiter's Lua script against the real local Redis (P0-055).

Needs ``py scripts/dev.py up``. Proves the atomic EVAL actually enforces the
bucket in Redis (not just the in-memory equivalent used by the route-level
unit tests in apps/api/tests/test_rate_limit.py), and that it refills.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from dotenv import dotenv_values
from redis.asyncio import Redis

from creatoriqx_api.platform.rate_limit import RedisTokenBucketLimiter

pytestmark = pytest.mark.integration

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    url = dotenv_values(ENV_FILE).get("REDIS_URL")
    if not url:
        pytest.fail(".env is missing REDIS_URL. Run: py scripts/dev.py setup")
    client = Redis.from_url(url)
    yield client
    await client.aclose()


async def test_lua_script_allows_then_blocks_then_refills(redis_client: Redis) -> None:
    limiter = RedisTokenBucketLimiter(redis_client)
    key = f"test:p0-055:{uuid.uuid4()}"

    first = await limiter.check(key, capacity=1, refill_per_second=50.0)
    assert first.allowed is True

    second = await limiter.check(key, capacity=1, refill_per_second=50.0)
    assert second.allowed is False
    assert second.retry_after_seconds >= 0

    await asyncio.sleep(0.05)  # 50 tokens/sec: well over one token refilled
    third = await limiter.check(key, capacity=1, refill_per_second=50.0)
    assert third.allowed is True

    await redis_client.delete(f"ratelimit:{key}")


async def test_key_expires_rather_than_growing_forever(redis_client: Redis) -> None:
    limiter = RedisTokenBucketLimiter(redis_client)
    key = f"test:p0-055:ttl:{uuid.uuid4()}"

    await limiter.check(key, capacity=5, refill_per_second=1.0)
    ttl = await redis_client.ttl(f"ratelimit:{key}")
    assert 0 < ttl <= 6  # ceil(capacity / refill_per_second) + 1

    await redis_client.delete(f"ratelimit:{key}")

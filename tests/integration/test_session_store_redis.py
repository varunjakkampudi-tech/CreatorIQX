"""Redis session store against the real local Redis (P0-051). Needs ``py scripts/dev.py up``."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from dotenv import dotenv_values
from redis.asyncio import Redis

from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.errors import SessionRequiredError
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import RedisKeyValueStore

pytestmark = pytest.mark.integration

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
POLICY = SessionPolicy(idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12))
USER_ID = uuid.UUID(int=1)
WORKSPACE_ID = uuid.UUID(int=2)


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    url = dotenv_values(ENV_FILE).get("REDIS_URL")
    if not url:
        pytest.fail(".env is missing REDIS_URL. Run: py scripts/dev.py setup")
    client = Redis.from_url(url)
    yield client
    await client.aclose()


async def test_session_survives_across_service_instances(redis_client: Redis) -> None:
    # Two service instances stand in for two API workers sharing one Redis.
    worker_a = SessionService(RedisKeyValueStore(redis_client), POLICY)
    worker_b = SessionService(RedisKeyValueStore(redis_client), POLICY)
    created = await worker_a.create(
        subject=f"sub-{uuid.uuid4()}",
        email="creator@example.com",
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
    )
    assert (await worker_b.authenticate(created.id)).email == "creator@example.com"
    await worker_b.end(created.id)
    with pytest.raises(SessionRequiredError):
        await worker_a.authenticate(created.id)


async def test_redis_enforces_the_absolute_expiry(redis_client: Redis) -> None:
    service = SessionService(RedisKeyValueStore(redis_client), POLICY)
    created = await service.create(
        subject="sub",
        email="creator@example.com",
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
    )
    ttl = await redis_client.ttl(f"session:{created.id}")
    assert 0 < ttl <= int(POLICY.absolute_timeout.total_seconds())
    await service.end(created.id)


async def test_flow_records_are_single_use(redis_client: Redis) -> None:
    store = RedisKeyValueStore(redis_client)
    key = f"oidc_flow:{uuid.uuid4()}"
    await store.put(key, {"state": "s", "nonce": "n"}, ttl_seconds=60)
    assert await store.take(key) == {"state": "s", "nonce": "n"}
    assert await store.take(key) is None

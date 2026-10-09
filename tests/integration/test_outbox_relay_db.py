"""SqlOutboxGateway against real PostgreSQL (P0-061).

Needs ``py scripts/dev.py up``. Proves the three things a fake gateway
can't: ``FOR UPDATE SKIP LOCKED`` actually prevents two concurrent relays
from double-processing the same row, a dispatch failure rolls back the
*whole* batch (simulating a crash) so the event is redelivered, and a normal
run dispatches each event exactly once and marks it published.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from creatoriqx_api.modules.jobs.application.outbox_relay import HandlerRegistry
from creatoriqx_api.modules.jobs.application.ports import OutboxEventRecord
from creatoriqx_api.modules.jobs.infrastructure.outbox_gateway import SqlOutboxGateway
from creatoriqx_api.modules.jobs.infrastructure.tables import OutboxEvent
from creatoriqx_api.platform.database import session_scope

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"


def _test_url(key: str) -> str:
    value = dotenv_values(REPO_ROOT / ".env").get(key)
    if not value:
        pytest.fail(f"{key} missing from .env. Run: py scripts/dev.py setup")
    base, _ = value.rsplit("/", 1)
    return f"{base}/creatoriqx_test"


@pytest.fixture(scope="module", autouse=True)
def _schema_at_head() -> None:
    os.environ["ALEMBIC_DATABASE_URL"] = _test_url("DATABASE_OWNER_URL")
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    built = create_async_engine(_test_url("DATABASE_APP_URL"), pool_pre_ping=True)
    yield built
    await built.dispose()


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def _insert_event(
    factory: async_sessionmaker[AsyncSession], *, event_type: str = "test.event"
) -> uuid.UUID:
    event_id = uuid.uuid4()
    async with session_scope(factory) as session:
        session.add(
            OutboxEvent(id=event_id, event_type=event_type, payload={"marker": str(event_id)})
        )
    return event_id


async def _published_at(
    factory: async_sessionmaker[AsyncSession], event_id: uuid.UUID
) -> object | None:
    async with factory() as session:
        row = await session.get(OutboxEvent, event_id)
        assert row is not None
        return row.published_at


async def test_a_normal_run_dispatches_once_and_marks_published(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = await _insert_event(factory)
    gateway = SqlOutboxGateway(factory)
    seen: list[uuid.UUID] = []

    registry = HandlerRegistry()

    async def record(event: OutboxEventRecord) -> None:
        seen.append(event.id)

    registry.on("test.event", record)

    relayed = await gateway.relay_batch(registry, limit=50)

    assert relayed >= 1
    assert seen.count(event_id) == 1
    assert await _published_at(factory, event_id) is not None


async def test_a_dispatch_failure_rolls_back_the_batch_for_redelivery(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = await _insert_event(factory, event_type="test.crash")
    gateway = SqlOutboxGateway(factory)

    crashing_registry = HandlerRegistry()
    attempts: list[uuid.UUID] = []

    async def crash_once(event: OutboxEventRecord) -> None:
        attempts.append(event.id)
        raise RuntimeError("simulated crash mid-dispatch")

    crashing_registry.on("test.crash", crash_once)

    with pytest.raises(RuntimeError, match="simulated crash"):
        await gateway.relay_batch(crashing_registry, limit=50)

    # Rolled back: still unpublished, never actually delivered to the caller.
    assert await _published_at(factory, event_id) is None

    # A second, healthy run picks the same event back up (redelivery).
    healthy_registry = HandlerRegistry()
    delivered: list[uuid.UUID] = []

    async def succeed(event: OutboxEventRecord) -> None:
        delivered.append(event.id)

    healthy_registry.on("test.crash", succeed)

    relayed = await gateway.relay_batch(healthy_registry, limit=50)

    assert relayed >= 1
    assert event_id in delivered
    assert await _published_at(factory, event_id) is not None


async def test_concurrent_relays_skip_locked_rows_instead_of_double_processing(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    event_ids = {await _insert_event(factory, event_type="test.concurrent") for _ in range(4)}

    seen_by: dict[int, list[uuid.UUID]] = {0: [], 1: []}

    def _make_registry(worker: int) -> HandlerRegistry:
        registry = HandlerRegistry()

        async def record(event: OutboxEventRecord) -> None:
            # Give the other worker a chance to race for the same rows before
            # this transaction commits and releases its locks.
            await asyncio.sleep(0.05)
            seen_by[worker].append(event.id)

        registry.on("test.concurrent", record)
        return registry

    gateway_a = SqlOutboxGateway(factory)
    gateway_b = SqlOutboxGateway(factory)

    await asyncio.gather(
        gateway_a.relay_batch(_make_registry(0), limit=2),
        gateway_b.relay_batch(_make_registry(1), limit=2),
    )

    all_seen = seen_by[0] + seen_by[1]
    # Every one of our events was processed exactly once, by exactly one worker.
    relevant = [e for e in all_seen if e in event_ids]
    assert sorted(relevant) == sorted(event_ids)
    assert len(relevant) == len(set(relevant))

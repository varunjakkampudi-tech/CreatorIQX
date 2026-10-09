"""SqlTelemetrySink against real PostgreSQL under forced RLS (P0-062).

Needs ``py scripts/dev.py up``. Proves: an event persists with its
non-allow-listed property already dropped (``UsageEventRecorder`` sanitizes
before the sink ever sees it); a workspace cannot read another workspace's
usage events (forced RLS, same as every other tenant table).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from creatoriqx_api.modules.telemetry.application.usage_event_recorder import UsageEventRecorder
from creatoriqx_api.modules.telemetry.infrastructure.sql_sink import SqlTelemetrySink
from creatoriqx_api.platform.database import set_tenant_context

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


async def _read_as(
    factory: async_sessionmaker[AsyncSession], *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> list[tuple[str, dict[str, object] | None]]:
    async with factory() as session, session.begin():
        await set_tenant_context(session, workspace_id=workspace_id, user_id=user_id)
        result = await session.execute(
            text("SELECT name, properties FROM usage_events WHERE workspace_id = :w"),
            {"w": workspace_id},
        )
        return [(row[0], row[1]) for row in result.all()]


async def test_a_recorded_event_persists_with_the_disallowed_property_dropped(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    recorder = UsageEventRecorder(SqlTelemetrySink(factory))

    await recorder.record(
        "auth.login_succeeded",
        workspace_id=workspace_id,
        user_id=user_id,
        properties={"method": "google_oidc", "secret_token": "should-never-be-stored"},
    )

    rows = await _read_as(factory, workspace_id=workspace_id, user_id=user_id)
    assert rows == [("auth.login_succeeded", {"method": "google_oidc"})]


async def test_a_workspace_cannot_read_another_workspaces_usage_events(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    recorder = UsageEventRecorder(SqlTelemetrySink(factory))
    workspace_a, workspace_b = uuid.uuid4(), uuid.uuid4()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    await recorder.record("auth.login_succeeded", workspace_id=workspace_a, user_id=user_a)
    await recorder.record("auth.login_succeeded", workspace_id=workspace_b, user_id=user_b)

    # Reading under workspace_b's own tenant context must see exactly its own
    # one event - never workspace_a's, even though both rows exist in the
    # same physical table.
    seen_by_b = await _read_as(factory, workspace_id=workspace_b, user_id=user_b)
    assert len(seen_by_b) == 1

    seen_by_a = await _read_as(factory, workspace_id=workspace_a, user_id=user_a)
    assert len(seen_by_a) == 1

"""Regression test for the P1A-03 production bug: ``SqlChannelConnectionStore``
(and ``SqlChannelVideoStore``) must set the RLS tenant context before every
query, same as every other tenant-scoped SQL store (spec §6 multi-tenancy).

Without ``set_tenant_context``, ``current_setting('app.workspace_id', true)``
returns ``''`` and the RLS policy's own ``::uuid`` cast fails with
``invalid input syntax for type uuid: ""`` - which is exactly what happened
against a real Google OAuth connection on 2026-10-10 (``channels.workspace_id
= $1::UUID``, bound workspace_id looked fine, but the RLS policy's cast of
the *unset* ``app.workspace_id`` setting is what actually raised). This test
exercises the real store against real Postgres so this class of gap - "no
real-Postgres run of this store" - cannot silently recur.

Runs against creatoriqx_test. Needs ``py scripts/dev.py up``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from creatoriqx_api.modules.youtube.domain.connection import ChannelInfo, OAuthTokens
from creatoriqx_api.modules.youtube.infrastructure.sql_connection_store import (
    SqlChannelConnectionStore,
)
from creatoriqx_api.platform.crypto import TokenCipher, generate_key, load_key

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"


# Duplicated from test_rls.py rather than imported: this test suite's own
# convention (set when test_planning_routes.py was written, P1B-05) avoids
# importing fixtures/fakes across test modules, since the top-level
# tests/integration directory has no __init__.py and collides under some
# import modes.
def _test_url(key: str) -> str:
    value = dotenv_values(REPO_ROOT / ".env").get(key)
    if not value:
        pytest.fail(f"{key} missing from .env. Run: py scripts/dev.py setup")
    base, _ = value.rsplit("/", 1)
    return f"{base}/creatoriqx_test"


async def _add_user(session: AsyncSession, user_id: uuid.UUID, email: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, email) VALUES (:i, :e)"), {"i": user_id, "e": email}
    )


async def _add_workspace(session: AsyncSession, workspace_id: uuid.UUID, name: str) -> None:
    await session.execute(
        text("INSERT INTO workspaces (id, name) VALUES (:i, :n)"), {"i": workspace_id, "n": name}
    )


@pytest.fixture(scope="module", autouse=True)
def _schema_at_head() -> None:
    os.environ["ALEMBIC_DATABASE_URL"] = _test_url("DATABASE_OWNER_URL")
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


def test_save_connection_succeeds_under_rls() -> None:
    """The exact call path the real connect callback takes must not raise."""
    engine = create_async_engine(_test_url("DATABASE_APP_URL"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    cipher = TokenCipher("test-key", load_key(generate_key()))
    store = SqlChannelConnectionStore(factory, cipher)
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    async def body() -> None:
        try:
            async with factory() as session:
                await _add_user(session, user_id, "owner@example.com")
                await _add_workspace(session, workspace_id, "W")
                await session.commit()

            tokens = OAuthTokens(
                access_token="at",
                refresh_token="rt",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                scopes=("https://www.googleapis.com/auth/youtube.readonly",),
            )
            channel = ChannelInfo(
                youtube_channel_id="UC_test_channel",
                title="Test Channel",
                thumbnail_url=None,
                subscriber_count=10,
                view_count=100,
                video_count=5,
                uploads_playlist_id="UU_test_channel",
            )

            connected = await store.save_connection(
                workspace_id=workspace_id,
                connected_by_user_id=user_id,
                tokens=tokens,
                channel=channel,
            )
            assert connected.youtube_channel_id == "UC_test_channel"

            channels = await store.list_channels(workspace_id)
            assert [c.youtube_channel_id for c in channels] == ["UC_test_channel"]

            active = await store.get_active_connection(
                workspace_id=workspace_id, channel_id=connected.id
            )
            assert active.access_token == "at"

            await store.update_access_token(
                workspace_id=workspace_id,
                connection_id=active.connection_id,
                tokens=OAuthTokens(
                    access_token="at2",
                    refresh_token=None,
                    expires_at=datetime.now(UTC) + timedelta(hours=2),
                    scopes=tokens.scopes,
                ),
            )
            refreshed = await store.get_active_connection(
                workspace_id=workspace_id, channel_id=connected.id
            )
            assert refreshed.access_token == "at2"

            await store.disconnect(workspace_id=workspace_id, channel_id=connected.id)

            async with factory() as cleanup:
                await cleanup.execute(
                    text("DELETE FROM memberships WHERE user_id = :u"), {"u": user_id}
                )
                await cleanup.execute(
                    text("DELETE FROM oauth_connections WHERE workspace_id = :w"),
                    {"w": workspace_id},
                )
                await cleanup.execute(
                    text("DELETE FROM channels WHERE workspace_id = :w"), {"w": workspace_id}
                )
                await cleanup.execute(
                    text("DELETE FROM workspaces WHERE id = :w"), {"w": workspace_id}
                )
                await cleanup.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
                await cleanup.commit()
        finally:
            await engine.dispose()

    asyncio.run(body())

"""Migration round-trip and model/migration drift check (P0-040, P0-041).

Runs against the real creatoriqx_test database. Needs ``py scripts/dev.py up``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from dotenv import dotenv_values
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import creatoriqx_api.tables  # noqa: F401  # registers models on Base.metadata
from creatoriqx_api.platform.db import Base

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"


def _owner_test_url() -> str:
    values = dotenv_values(REPO_ROOT / ".env")
    owner = values.get("DATABASE_OWNER_URL")
    if not owner:
        pytest.fail("DATABASE_OWNER_URL missing from .env. Run: py scripts/dev.py setup")
    base, _ = owner.rsplit("/", 1)
    return f"{base}/creatoriqx_test"


def _head_revision() -> str:
    return cast("str", ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head())


async def _current_revision(url: str) -> str | None:
    dsn = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn)
    try:
        result = await connection.fetchval("SELECT version_num FROM alembic_version")
        return cast("str | None", result)
    finally:
        await connection.close()


async def _schema_diffs(url: str) -> list[Any]:
    engine = create_async_engine(url)

    def _compare(sync_connection: Connection) -> list[Any]:
        context = MigrationContext.configure(sync_connection)
        return list(compare_metadata(context, Base.metadata))

    async with engine.connect() as connection:
        diffs = await connection.run_sync(_compare)
    await engine.dispose()
    return diffs


def test_migration_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _owner_test_url()
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)
    config = Config(str(ALEMBIC_INI))
    head = _head_revision()

    command.upgrade(config, "head")
    assert asyncio.run(_current_revision(url)) == head

    command.downgrade(config, "base")
    assert asyncio.run(_current_revision(url)) is None

    command.upgrade(config, "head")
    assert asyncio.run(_current_revision(url)) == head


def test_migrations_match_the_models(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _owner_test_url()
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    assert asyncio.run(_schema_diffs(url)) == []  # models and migrations agree

"""Migration round-trip against the real creatoriqx_test database (P0-040).

Proves ``upgrade -> downgrade -> upgrade`` works. Needs ``py scripts/dev.py up``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values

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


async def _current_revision(url: str) -> str | None:
    dsn = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn)
    try:
        result = await connection.fetchval("SELECT version_num FROM alembic_version")
        return cast("str | None", result)
    finally:
        await connection.close()


def test_migration_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _owner_test_url()
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)
    config = Config(str(ALEMBIC_INI))

    command.upgrade(config, "head")
    assert asyncio.run(_current_revision(url)) == "0001"

    command.downgrade(config, "base")
    assert asyncio.run(_current_revision(url)) is None

    command.upgrade(config, "head")
    assert asyncio.run(_current_revision(url)) == "0001"

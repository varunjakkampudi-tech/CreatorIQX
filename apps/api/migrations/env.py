"""Alembic migration environment (async, owner role).

The URL comes from ``ALEMBIC_DATABASE_URL`` when set (tests point it at the
``creatoriqx_test`` database), otherwise from ``DATABASE_OWNER_URL``.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import creatoriqx_api.tables  # noqa: F401  # registers every model on Base.metadata
from creatoriqx_api.platform.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_OWNER_URL")
    if not url:
        raise RuntimeError("Set DATABASE_OWNER_URL (or ALEMBIC_DATABASE_URL) to run migrations.")
    return url


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async())

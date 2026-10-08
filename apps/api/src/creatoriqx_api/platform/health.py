"""Dependency health checks for the readiness endpoint (spec §14 Health).

Each check proves one dependency answers a trivial request. Failures are
reported only as "unavailable": error text can contain connection strings, so
it never leaves the process.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Literal, Protocol

import asyncpg
from redis.asyncio import Redis

CheckStatus = Literal["ok", "unavailable"]


class HealthCheck(Protocol):
    """A named probe of one dependency. ``check`` raises on failure."""

    name: str

    async def check(self) -> None: ...


class PostgresCheck:
    """Connects with the runtime role and runs ``SELECT 1``."""

    name = "postgres"

    def __init__(self, dsn: str, timeout_seconds: float) -> None:
        # asyncpg expects a plain postgresql:// DSN, not SQLAlchemy's driver suffix.
        self._dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._timeout = timeout_seconds

    async def check(self) -> None:
        connection = await asyncpg.connect(self._dsn, timeout=self._timeout)
        try:
            if await connection.fetchval("SELECT 1") != 1:
                raise RuntimeError("unexpected result from SELECT 1")
        finally:
            await connection.close()


class RedisCheck:
    """Sends ``PING``."""

    name = "redis"

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self._url = url
        self._timeout = timeout_seconds

    async def check(self) -> None:
        client: Redis = Redis.from_url(
            self._url, socket_connect_timeout=self._timeout, socket_timeout=self._timeout
        )
        try:
            if not await client.ping():
                raise RuntimeError("PING was not acknowledged")
        finally:
            await client.aclose()


async def _run_one(check: HealthCheck, timeout_seconds: float) -> CheckStatus:
    try:
        await asyncio.wait_for(check.check(), timeout=timeout_seconds)
    except Exception:  # noqa: BLE001  # any failure means unavailable; details stay private
        return "unavailable"
    return "ok"


async def run_checks(
    checks: Sequence[HealthCheck], timeout_seconds: float
) -> dict[str, CheckStatus]:
    """Run all checks concurrently; each is bounded by ``timeout_seconds``."""
    results = await asyncio.gather(*(_run_one(c, timeout_seconds) for c in checks))
    return {check.name: status for check, status in zip(checks, results, strict=True)}

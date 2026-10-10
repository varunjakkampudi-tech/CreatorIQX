"""Quota ledger adapter: live atomic reservation in Redis, durable history in
Postgres (spec §6 Quota management, §7 ``quota_ledger``).

Redis holds the per-workspace-per-day counter and does the atomic
check-and-increment (a Lua script, so a race between two concurrent calls
cannot both reserve the last unit). Every successful reservation also writes
one append-only row to the ``quota_ledger`` table, so the day's usage survives
a Redis flush and a historical report can be rebuilt from Postgres alone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.youtube.domain.errors import QuotaExhaustedError
from creatoriqx_api.modules.youtube.infrastructure.tables import QuotaLedgerEntry
from creatoriqx_api.platform.database import session_scope, set_tenant_context

if TYPE_CHECKING:
    from redis.asyncio import Redis

# Atomic check-and-increment: fails closed (refuses the reservation) if the
# counter would exceed the daily cap, rather than incrementing past it and
# hoping a later caller notices.
_RESERVE_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local units = tonumber(ARGV[1])
local cap = tonumber(ARGV[2])
if current + units > cap then
    return 0
end
redis.call('INCRBY', KEYS[1], units)
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""
_DAY_SECONDS = 26 * 60 * 60  # a little over a day, so the key outlives the UTC day it tracks

# quota_ledger's RLS policy (see the 0006 migration) only checks workspace_id,
# never user_id; set_tenant_context always requires one, and reserve() isn't
# given an acting user, so a nil UUID stands in (same convention as
# telemetry.infrastructure.sql_sink._NO_ACTOR).
_NO_ACTOR = uuid.UUID(int=0)


def _counter_key(workspace_id: uuid.UUID, provider: str, day: date) -> str:
    return f"quota:{provider}:{workspace_id}:{day.isoformat()}"


class RedisPostgresQuotaLedger:
    """Reserves quota in Redis, appends the durable record in Postgres."""

    def __init__(
        self,
        *,
        redis_client: Redis,
        session_factory: async_sessionmaker[AsyncSession],
        daily_cap: int,
    ) -> None:
        self._redis = redis_client
        self._factory = session_factory
        self._daily_cap = daily_cap
        self._script = self._redis.register_script(_RESERVE_SCRIPT)

    async def reserve(
        self, *, workspace_id: uuid.UUID, provider: str, endpoint: str, units: int
    ) -> None:
        today = datetime.now(UTC).date()
        key = _counter_key(workspace_id, provider, today)
        allowed = await self._script(keys=[key], args=[units, self._daily_cap, _DAY_SECONDS])
        if not allowed:
            raise QuotaExhaustedError(
                detail=f"Daily quota of {self._daily_cap} units exhausted for {provider}"
            )

        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            session.add(
                QuotaLedgerEntry(
                    workspace_id=workspace_id,
                    provider=provider,
                    endpoint=endpoint,
                    units=units,
                    usage_date=today,
                )
            )
            await session.flush()

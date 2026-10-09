"""Redis token-bucket rate limiting (spec §6, §10; ticket P0-055).

A cross-cutting platform primitive, not identity-specific: any route can ask
``RateLimiter.check(key, capacity=..., refill_per_second=...)`` for its own
bucket. P0-055 is the first caller (login and callback, per IP and per
session), exercising the one working example the Phase 0 depth rule asks for.

The Redis adapter does the read-refill-decide-write sequence in a single Lua
script so concurrent requests against the same key cannot race each other
into a false "allowed".
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from redis.asyncio import Redis

MonotonicClock = Callable[[], float]

# KEYS[1] = bucket key
# ARGV[1] = capacity (max tokens)
# ARGV[2] = refill_per_second (tokens added per second)
# ARGV[3] = now (seconds, float, caller's clock)
# ARGV[4] = cost (tokens this check consumes)
#
# Stored as a hash {tokens, ts}; refilled by elapsed time since ts, capped at
# capacity, before deciding whether cost can be spent. The key's TTL is set to
# just past a full refill, so an idle bucket cleans itself up in Redis rather
# than accumulating forever.
_RATE_LIMIT_SCRIPT = """
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local data = redis.call("HMGET", KEYS[1], "tokens", "ts")
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

local elapsed = now - ts
if elapsed < 0 then
  elapsed = 0
end
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
local retry_after = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_after = (cost - tokens) / refill_rate
end

redis.call("HSET", KEYS[1], "tokens", tostring(tokens), "ts", tostring(now))
local ttl = math.ceil(capacity / refill_rate) + 1
redis.call("EXPIRE", KEYS[1], ttl)

return {allowed, tostring(retry_after)}
"""


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """The outcome of one ``RateLimiter.check`` call."""

    allowed: bool
    retry_after_seconds: int


class RateLimiter(Protocol):
    """A keyed token bucket. One instance can serve many independent buckets."""

    async def check(
        self, key: str, *, capacity: int, refill_per_second: float, cost: float = 1.0
    ) -> RateLimitResult:
        """Spend ``cost`` tokens from ``key``'s bucket, refilled over time.

        ``capacity`` is the burst size; ``refill_per_second`` sets the
        sustained rate (for "N per window seconds", pass
        ``capacity / window_seconds``).
        """


class RedisTokenBucketLimiter:
    """Production adapter: one Lua EVAL per check, atomic against concurrent callers."""

    def __init__(self, client: Redis, clock: MonotonicClock = time.time) -> None:
        self._client = client
        self._clock = clock

    async def check(
        self, key: str, *, capacity: int, refill_per_second: float, cost: float = 1.0
    ) -> RateLimitResult:
        allowed, retry_after = await self._client.eval(
            _RATE_LIMIT_SCRIPT,
            1,
            f"ratelimit:{key}",
            capacity,
            refill_per_second,
            self._clock(),
            cost,
        )
        return RateLimitResult(
            allowed=bool(int(allowed)), retry_after_seconds=max(0, round(float(retry_after)))
        )


class InMemoryTokenBucketLimiter:
    """Process-local equivalent for unit tests; same semantics, no Redis."""

    def __init__(self, clock: MonotonicClock = time.monotonic) -> None:
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, ts)

    async def check(
        self, key: str, *, capacity: int, refill_per_second: float, cost: float = 1.0
    ) -> RateLimitResult:
        now = self._clock()
        tokens, ts = self._buckets.get(key, (float(capacity), now))
        tokens = min(capacity, tokens + max(0.0, now - ts) * refill_per_second)

        if tokens >= cost:
            tokens -= cost
            self._buckets[key] = (tokens, now)
            return RateLimitResult(allowed=True, retry_after_seconds=0)

        retry_after = (cost - tokens) / refill_per_second
        self._buckets[key] = (tokens, now)
        return RateLimitResult(allowed=False, retry_after_seconds=max(0, round(retry_after)))

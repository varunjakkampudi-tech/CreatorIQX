"""Ports the identity application layer depends on.

Infrastructure implements these; the application never imports Redis or
FastAPI. Keeping the seam here lets the session logic run under unit tests
with an in-memory store and a controllable clock.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """The production clock. Always timezone-aware UTC."""
    return datetime.now(UTC)


class KeyValueStore(Protocol):
    """Short-lived JSON records with a server-side expiry (sessions, login flows)."""

    async def put(self, key: str, value: Mapping[str, Any], ttl_seconds: int) -> None:
        """Store ``value`` under ``key``; it expires after ``ttl_seconds``."""

    async def get(self, key: str) -> dict[str, Any] | None:
        """Return the record, or None if it is missing or expired."""

    async def take(self, key: str) -> dict[str, Any] | None:
        """Return the record and delete it in one step, so it can be used once."""

    async def delete(self, key: str) -> None:
        """Remove the record if it exists."""

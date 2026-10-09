"""Server-side session model (P0-051, ADR 0010).

The browser holds only an opaque random identifier. The session record lives
in the key-value store, so logout and expiry take effect immediately, and the
cookie reveals nothing about the user.

Two clocks govern a session:

* idle timeout: the session ends after this long without a request;
* absolute timeout: the session ends this long after login, however active
  it is. This bounds the damage of a stolen session.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import uuid
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    """How long a session may live. Validated once, when the app starts."""

    idle_timeout: timedelta
    absolute_timeout: timedelta

    def __post_init__(self) -> None:
        if self.idle_timeout <= timedelta(0):
            raise ValueError("idle_timeout must be positive")
        if self.absolute_timeout < self.idle_timeout:
            raise ValueError("absolute_timeout must be at least idle_timeout")


@dataclass(frozen=True, slots=True)
class Session:
    """An authenticated browser session bound to one user.

    ``subject`` is the Google OIDC subject (stable per user). ``user_id`` and
    ``workspace_id`` are the tenant context bound at login (ADR 0011): every
    later request sets them as the row-level security context. ``csrf_token``
    is the synchroniser token that unsafe requests must echo back.
    All datetimes are timezone-aware UTC.
    """

    id: str
    subject: str
    email: str
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    csrf_token: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime

    def is_alive(self, now: datetime, idle_timeout: timedelta) -> bool:
        """True while both the absolute and the idle deadline are still ahead."""
        return now < self.expires_at and now - self.last_seen_at < idle_timeout

    def touched(self, now: datetime) -> Session:
        """A copy that records activity at ``now``, restarting the idle timer."""
        return replace(self, last_seen_at=now)

    def to_record(self) -> dict[str, str]:
        """Serialise for the key-value store."""
        return {
            "id": self.id,
            "subject": self.subject,
            "email": self.email,
            "user_id": str(self.user_id),
            "workspace_id": str(self.workspace_id),
            "csrf_token": self.csrf_token,
            "created_at": self.created_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Session:
        """Rebuild a session from the key-value store."""
        return cls(
            id=str(record["id"]),
            subject=str(record["subject"]),
            email=str(record["email"]),
            user_id=uuid.UUID(str(record["user_id"])),
            workspace_id=uuid.UUID(str(record["workspace_id"])),
            csrf_token=str(record["csrf_token"]),
            created_at=datetime.fromisoformat(str(record["created_at"])),
            last_seen_at=datetime.fromisoformat(str(record["last_seen_at"])),
            expires_at=datetime.fromisoformat(str(record["expires_at"])),
        )

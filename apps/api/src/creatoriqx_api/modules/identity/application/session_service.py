"""Session lifecycle: create, authenticate, rotate, end, CSRF check (P0-051, ADR 0010).

Rules enforced here, not in the routes:

* a session id is 256 bits from ``secrets``, never derived from user data;
* every successful request restarts the idle timer, never the absolute one;
* login always issues a fresh id and discards any previous one (no session
  fixation);
* unsafe requests must echo the session's CSRF token, compared in constant time.
"""

from __future__ import annotations

import secrets
from datetime import datetime

from creatoriqx_api.modules.identity.application.ports import Clock, KeyValueStore, utc_now
from creatoriqx_api.modules.identity.domain.errors import (
    CSRFTokenError,
    SessionExpiredError,
    SessionRequiredError,
)
from creatoriqx_api.modules.identity.domain.session import Session, SessionPolicy

_TOKEN_BYTES = 32
_KEY_PREFIX = "session:"


def _key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}"


class SessionService:
    """Creates, validates, rotates and ends server-side sessions."""

    def __init__(
        self,
        store: KeyValueStore,
        policy: SessionPolicy,
        clock: Clock = utc_now,
    ) -> None:
        self._store = store
        self._policy = policy
        self._clock = clock

    @property
    def policy(self) -> SessionPolicy:
        return self._policy

    async def create(self, subject: str, email: str) -> Session:
        """Open a new session for an authenticated user."""
        now = self._clock()
        session = Session(
            id=secrets.token_urlsafe(_TOKEN_BYTES),
            subject=subject,
            email=email,
            csrf_token=secrets.token_urlsafe(_TOKEN_BYTES),
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._policy.absolute_timeout,
        )
        await self._save(session, now)
        return session

    async def authenticate(self, session_id: str) -> Session:
        """Return the live session for ``session_id`` and record the activity.

        Raises ``SessionRequiredError`` when there is no such session and
        ``SessionExpiredError`` when it has timed out (the record is then removed).
        """
        now = self._clock()
        record = await self._store.get(_key(session_id))
        if record is None:
            raise SessionRequiredError()
        session = Session.from_record(record)
        if not session.is_alive(now, self._policy.idle_timeout):
            await self._store.delete(_key(session_id))
            raise SessionExpiredError()
        touched = session.touched(now)
        await self._save(touched, now)
        return touched

    async def rotate(self, previous_session_id: str | None, subject: str, email: str) -> Session:
        """Replace any previous session with a fresh one (run at every login)."""
        if previous_session_id:
            await self._store.delete(_key(previous_session_id))
        return await self.create(subject, email)

    async def end(self, session_id: str) -> None:
        """Sign out: the session stops working immediately."""
        await self._store.delete(_key(session_id))

    def verify_csrf(self, session: Session, presented: str | None) -> None:
        """Raise ``CSRFTokenError`` unless ``presented`` matches the session's token."""
        if presented is None or not secrets.compare_digest(
            presented.encode("utf-8"), session.csrf_token.encode("utf-8")
        ):
            raise CSRFTokenError()

    async def _save(self, session: Session, now: datetime) -> None:
        # Redis expires the record at the absolute deadline; the idle deadline
        # is enforced in ``authenticate``, which is the only read path.
        ttl = max(1, int((session.expires_at - now).total_seconds()))
        await self._store.put(_key(session.id), session.to_record(), ttl)

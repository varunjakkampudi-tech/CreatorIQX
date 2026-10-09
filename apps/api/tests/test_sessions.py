"""Server-side session rules (P0-051, ADR 0010): lifecycle, timeouts, rotation, CSRF.

The clock is injected so the timeout rules are tested without sleeping.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.errors import (
    CSRFTokenError,
    SessionExpiredError,
    SessionRequiredError,
)
from creatoriqx_api.modules.identity.domain.session import Session, SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore

START = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
POLICY = SessionPolicy(idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12))
USER_ID = uuid.UUID(int=1)
WORKSPACE_ID = uuid.UUID(int=2)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def service(clock: FakeClock) -> SessionService:
    return SessionService(InMemoryKeyValueStore(clock), POLICY, clock)


async def _open(service: SessionService, subject: str = "s", email: str = "e@x.com") -> Session:
    """Open a session for the fixture tenant (user and personal workspace ids)."""
    return await service.create(
        subject=subject, email=email, user_id=USER_ID, workspace_id=WORKSPACE_ID
    )


# --- policy and model ---------------------------------------------------------


def test_policy_rejects_absolute_shorter_than_idle() -> None:
    with pytest.raises(ValueError, match="absolute_timeout"):
        SessionPolicy(idle_timeout=timedelta(hours=2), absolute_timeout=timedelta(hours=1))


def test_policy_rejects_non_positive_idle() -> None:
    with pytest.raises(ValueError, match="idle_timeout"):
        SessionPolicy(idle_timeout=timedelta(0), absolute_timeout=timedelta(hours=1))


def test_session_record_round_trips() -> None:
    session = Session(
        id="id",
        subject="sub",
        email="a@b.com",
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        csrf_token="csrf",
        created_at=START,
        last_seen_at=START,
        expires_at=START + timedelta(hours=12),
    )
    assert Session.from_record(session.to_record()) == session


# --- lifecycle ----------------------------------------------------------------


async def test_created_session_authenticates_to_the_same_user(service: SessionService) -> None:
    created = await _open(service, "google-sub-1", "creator@example.com")
    found = await service.authenticate(created.id)
    assert found.subject == "google-sub-1"
    assert found.email == "creator@example.com"
    assert found.csrf_token == created.csrf_token


async def test_session_keeps_the_tenant_context_bound_at_login(service: SessionService) -> None:
    created = await _open(service)
    found = await service.authenticate(created.id)
    assert found.user_id == USER_ID
    assert found.workspace_id == WORKSPACE_ID


async def test_session_ids_are_unguessable(service: SessionService) -> None:
    first = await _open(service)
    second = await _open(service)
    assert first.id != second.id
    assert len(first.id) >= 43  # 32 random bytes, URL-safe base64
    assert len(first.csrf_token) >= 43


async def test_unknown_session_is_required(service: SessionService) -> None:
    with pytest.raises(SessionRequiredError):
        await service.authenticate("never-issued")


async def test_end_invalidates_the_session(service: SessionService) -> None:
    created = await _open(service)
    await service.end(created.id)
    with pytest.raises(SessionRequiredError):
        await service.authenticate(created.id)


# --- timeouts -----------------------------------------------------------------


async def test_idle_timeout_ends_an_inactive_session(
    service: SessionService, clock: FakeClock
) -> None:
    created = await _open(service)
    clock.advance(timedelta(minutes=31))
    with pytest.raises(SessionExpiredError):
        await service.authenticate(created.id)


async def test_activity_restarts_the_idle_timer(service: SessionService, clock: FakeClock) -> None:
    created = await _open(service)
    for _ in range(5):
        clock.advance(timedelta(minutes=25))
        await service.authenticate(created.id)  # 125 minutes in total, all within idle limits


async def test_activity_never_extends_the_absolute_lifetime(
    service: SessionService, clock: FakeClock
) -> None:
    created = await _open(service)
    for _ in range(35):  # 35 x 20 minutes = 11h40m, always active
        clock.advance(timedelta(minutes=20))
        await service.authenticate(created.id)
    clock.advance(timedelta(minutes=20))  # reaches the 12h absolute deadline
    # The store drops the record at the absolute deadline (its TTL), so the
    # session simply no longer exists: 401 either way, and no stale copy survives.
    with pytest.raises(SessionRequiredError):
        await service.authenticate(created.id)


async def test_expired_session_is_removed(service: SessionService, clock: FakeClock) -> None:
    created = await _open(service)
    clock.advance(timedelta(hours=13))
    with pytest.raises(SessionRequiredError):
        await service.authenticate(created.id)
    with pytest.raises(SessionRequiredError):
        await service.authenticate(created.id)


# --- rotation (no session fixation) -------------------------------------------


async def test_rotation_replaces_the_previous_session(service: SessionService) -> None:
    previous = await _open(service)
    fresh = await service.rotate(
        previous_session_id=previous.id,
        subject="s",
        email="e@x.com",
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
    )
    assert fresh.id != previous.id
    with pytest.raises(SessionRequiredError):
        await service.authenticate(previous.id)
    assert (await service.authenticate(fresh.id)).subject == "s"


async def test_rotation_without_previous_session_still_creates_one(
    service: SessionService,
) -> None:
    fresh = await service.rotate(
        previous_session_id=None,
        subject="s",
        email="e@x.com",
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
    )
    assert (await service.authenticate(fresh.id)).email == "e@x.com"


# --- CSRF ---------------------------------------------------------------------


async def test_matching_csrf_token_passes(service: SessionService) -> None:
    session = await _open(service)
    service.verify_csrf(session, session.csrf_token)


@pytest.mark.parametrize("presented", [None, "", "wrong-token", "ünïcode-token"])
async def test_missing_or_wrong_csrf_token_is_rejected(
    service: SessionService, presented: str | None
) -> None:
    session = await _open(service)
    with pytest.raises(CSRFTokenError):
        service.verify_csrf(session, presented)

"""First-login workspace bootstrap rules (P0-053, ADR 0011), unit level.

Runs the application service against the in-memory store. The SQL store is
proven against real Postgres in ``tests/integration/test_workspace_bootstrap_db.py``.

Acceptance (P0-053): two logins create exactly one workspace; the audit actions
and the outbox event are written; the service is idempotent on repeat login.
"""

from __future__ import annotations

import uuid

import pytest

from creatoriqx_api.modules.workspaces.application.bootstrap_service import (
    WorkspaceBootstrapService,
)
from creatoriqx_api.modules.workspaces.domain.bootstrap import (
    NO_WORKSPACE,
    IdentityConflictError,
    personal_workspace_name,
)
from creatoriqx_api.modules.workspaces.infrastructure.memory_store import (
    InMemoryPersonalWorkspaceStore,
)
from creatoriqx_api.platform.errors import DomainError
from creatoriqx_api.platform.ids import new_id


def _sequential_ids() -> object:
    counter = iter(range(1, 1000))

    def next_id() -> uuid.UUID:
        return uuid.UUID(int=next(counter))

    return next_id


@pytest.fixture
def store() -> InMemoryPersonalWorkspaceStore:
    return InMemoryPersonalWorkspaceStore()


@pytest.fixture
def service(store: InMemoryPersonalWorkspaceStore) -> WorkspaceBootstrapService:
    return WorkspaceBootstrapService(store, id_factory=_sequential_ids())  # type: ignore[arg-type]


# --- domain rules -------------------------------------------------------------


def test_no_workspace_sentinel_is_the_zero_uuid() -> None:
    assert uuid.UUID(int=0) == NO_WORKSPACE


def test_generated_ids_never_equal_the_sentinel() -> None:
    assert all(new_id() != NO_WORKSPACE for _ in range(50))


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("ada@example.com", "ada's workspace"),
        ("  Ada.Lovelace@example.com ", "  Ada.Lovelace's workspace"),
        ("@example.com", "Personal workspace"),
        ("   @example.com", "Personal workspace"),
    ],
)
def test_personal_workspace_name_is_derived_from_the_email(email: str, expected: str) -> None:
    assert personal_workspace_name(email) == expected


def test_personal_workspace_name_is_capped_at_the_column_length() -> None:
    assert len(personal_workspace_name("x" * 400 + "@example.com")) == 255


def test_identity_conflict_is_a_409_domain_error() -> None:
    error = IdentityConflictError()
    assert isinstance(error, DomainError)
    assert error.status == 409
    assert error.code == "identity-conflict"


# --- application service ------------------------------------------------------


async def test_first_login_creates_user_workspace_and_owner_membership(
    service: WorkspaceBootstrapService, store: InMemoryPersonalWorkspaceStore
) -> None:
    result = await service.ensure_personal_workspace(subject="sub-1", email="ada@example.com")
    assert result.user_created is True
    assert result.workspace_created is True
    assert result.user_id != result.workspace_id
    assert result.workspace_id != NO_WORKSPACE
    assert store.users["sub-1"].workspace_id == result.workspace_id


async def test_repeat_login_is_idempotent(
    service: WorkspaceBootstrapService, store: InMemoryPersonalWorkspaceStore
) -> None:
    first = await service.ensure_personal_workspace(subject="sub-1", email="ada@example.com")
    second = await service.ensure_personal_workspace(subject="sub-1", email="ada@example.com")
    assert second.user_id == first.user_id
    assert second.workspace_id == first.workspace_id
    assert second.user_created is False
    assert second.workspace_created is False
    assert len(store.users) == 1


async def test_two_logins_create_exactly_one_workspace_and_one_outbox_event(
    service: WorkspaceBootstrapService, store: InMemoryPersonalWorkspaceStore
) -> None:
    for _ in range(2):
        await service.ensure_personal_workspace(subject="sub-1", email="ada@example.com")
    assert store.outbox_events == ["workspace.created"]


async def test_audit_actions_are_written_on_creation_and_on_every_login(
    service: WorkspaceBootstrapService, store: InMemoryPersonalWorkspaceStore
) -> None:
    await service.ensure_personal_workspace(subject="sub-1", email="ada@example.com")
    assert store.audit_actions == ["user.created", "workspace.created", "auth.login_succeeded"]
    await service.ensure_personal_workspace(subject="sub-1", email="ada@example.com")
    assert store.audit_actions[-1] == "auth.login_succeeded"
    assert store.audit_actions.count("workspace.created") == 1


async def test_email_is_normalised_before_it_is_stored(
    service: WorkspaceBootstrapService, store: InMemoryPersonalWorkspaceStore
) -> None:
    await service.ensure_personal_workspace(subject="  sub-1 ", email="  Ada@Example.COM ")
    assert "sub-1" in store.users
    assert store.users["sub-1"].email == "ada@example.com"


async def test_distinct_subjects_get_distinct_workspaces(
    service: WorkspaceBootstrapService,
) -> None:
    first = await service.ensure_personal_workspace(subject="sub-1", email="a@example.com")
    second = await service.ensure_personal_workspace(subject="sub-2", email="b@example.com")
    assert first.workspace_id != second.workspace_id
    assert first.user_id != second.user_id


async def test_email_bound_to_another_subject_is_refused(
    service: WorkspaceBootstrapService,
) -> None:
    await service.ensure_personal_workspace(subject="sub-1", email="ada@example.com")
    with pytest.raises(IdentityConflictError):
        await service.ensure_personal_workspace(subject="sub-2", email="ada@example.com")


@pytest.mark.parametrize(("subject", "email"), [("", "a@example.com"), ("   ", "a@example.com")])
async def test_empty_subject_is_rejected(
    service: WorkspaceBootstrapService, subject: str, email: str
) -> None:
    with pytest.raises(ValueError, match="subject"):
        await service.ensure_personal_workspace(subject=subject, email=email)


async def test_empty_email_is_rejected(service: WorkspaceBootstrapService) -> None:
    with pytest.raises(ValueError, match="email"):
        await service.ensure_personal_workspace(subject="sub-1", email="  ")


async def test_default_id_factory_produces_v7_identifiers() -> None:
    service = WorkspaceBootstrapService(InMemoryPersonalWorkspaceStore())
    result = await service.ensure_personal_workspace(subject="sub-1", email="a@example.com")
    assert result.user_id.version == 7
    assert result.workspace_id.version == 7

"""SQLAlchemy adapter for the first-login bootstrap (P0-053, ADR 0011).

One transaction per login, under an advisory lock keyed by the Google subject,
so two concurrent first logins for the same person cannot both create a
workspace. Every row is written under the tenant context that owns it:

* ``users`` is global, written under ``NO_WORKSPACE``;
* the workspace, its owner membership and ``workspace.created`` are written
  under the new workspace id, so ``INSERT ... RETURNING`` passes the SELECT
  policy (ADR 0002);
* each audit row is flushed under its own workspace context (or
  ``NO_WORKSPACE`` when it has none), for the same RETURNING reason.

No privileged or bypass path is used: the runtime role does all of it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.audit.infrastructure.tables import AuditLog
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.identity.infrastructure.tables import User
from creatoriqx_api.modules.jobs.infrastructure.tables import OutboxEvent
from creatoriqx_api.modules.workspaces.application.ports import BootstrapCommand
from creatoriqx_api.modules.workspaces.domain.bootstrap import (
    NO_WORKSPACE,
    BootstrapResult,
    IdentityConflictError,
)
from creatoriqx_api.modules.workspaces.infrastructure.tables import Membership, Workspace
from creatoriqx_api.platform.database import session_scope, set_tenant_context

_LOCK_SQL = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")
_LOCK_NAMESPACE = "identity.google-sub:"


class SqlPersonalWorkspaceStore:
    """Persists the first-login bootstrap with the runtime role under forced RLS."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def ensure(self, command: BootstrapCommand) -> BootstrapResult:
        async with session_scope(self._factory) as session:
            await session.execute(_LOCK_SQL, {"key": f"{_LOCK_NAMESPACE}{command.subject}"})
            return await _ensure(session, command)


async def _ensure(session: AsyncSession, command: BootstrapCommand) -> BootstrapResult:
    user = await _find_user_by_subject(session, command.subject)
    user_created = user is None
    if user is None:
        user_id = await _create_user(session, command)
    else:
        user_id = user.id
        await set_tenant_context(session, workspace_id=NO_WORKSPACE, user_id=user_id)

    membership = await _first_owner_membership(session, user_id)
    if membership is None:
        workspace_id = await _create_personal_workspace(session, command, user_id)
        workspace_created = True
    else:
        workspace_id = membership.workspace_id
        workspace_created = False

    await _audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        action="auth.login_succeeded",
        resource_type="user",
        resource_id=user_id,
        correlation_id=command.correlation_id,
    )
    return BootstrapResult(
        user_id=user_id,
        workspace_id=workspace_id,
        user_created=user_created,
        workspace_created=workspace_created,
    )


async def _find_user_by_subject(session: AsyncSession, subject: str) -> User | None:
    result = await session.execute(select(User).where(User.google_sub == subject))
    return result.scalar_one_or_none()


async def _create_user(session: AsyncSession, command: BootstrapCommand) -> uuid.UUID:
    existing = await session.execute(select(User.id).where(User.email == command.email))
    if existing.first() is not None:
        # The email belongs to a different Google subject: refuse rather than merge accounts.
        raise IdentityConflictError("This email is already linked to another sign-in")

    await set_tenant_context(session, workspace_id=NO_WORKSPACE, user_id=command.user_id)
    session.add(User(id=command.user_id, email=command.email, google_sub=command.subject))
    try:
        await session.flush()
    except IntegrityError as exc:
        raise IdentityConflictError("This email is already linked to another sign-in") from exc
    await _audit(
        session,
        workspace_id=None,
        actor_user_id=command.user_id,
        action="user.created",
        resource_type="user",
        resource_id=command.user_id,
        correlation_id=command.correlation_id,
    )
    return command.user_id


async def _first_owner_membership(session: AsyncSession, user_id: uuid.UUID) -> Membership | None:
    # memberships_read lets a user see their own rows, so this works before a workspace is set.
    result = await session.execute(
        select(Membership)
        .where(Membership.user_id == user_id, Membership.role == Role.OWNER)
        .order_by(Membership.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _create_personal_workspace(
    session: AsyncSession, command: BootstrapCommand, user_id: uuid.UUID
) -> uuid.UUID:
    workspace_id = command.workspace_id
    await set_tenant_context(session, workspace_id=workspace_id, user_id=user_id)

    # The workspace row must reach the database before the membership that
    # references it. Nothing here declares a ``relationship()``, and without one
    # SQLAlchemy orders a flush by mapper sort key (module and class name), not
    # by foreign key: ``...workspaces.Membership`` sorts before
    # ``...workspaces.Workspace``, so a single flush would insert the membership
    # first and violate ``fk_memberships_workspace_id_workspaces``. Two flushes
    # make the order explicit instead of depending on class names.
    session.add(Workspace(id=workspace_id, name=command.workspace_name))
    await session.flush()

    session.add(
        Membership(
            id=command.membership_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role=Role.OWNER,
        )
    )
    session.add(
        OutboxEvent(
            event_type="workspace.created",
            payload={"workspace_id": str(workspace_id), "owner_user_id": str(user_id)},
        )
    )
    await session.flush()
    await _audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        action="workspace.created",
        resource_type="workspace",
        resource_id=workspace_id,
        correlation_id=command.correlation_id,
    )
    return workspace_id


async def _audit(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    correlation_id: str | None,
) -> None:
    """Append one audit row under its own tenant context. Never updated or deleted (STRIDE T-T2)."""
    await set_tenant_context(
        session,
        workspace_id=workspace_id or NO_WORKSPACE,
        user_id=actor_user_id,
    )
    session.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=correlation_id,
        )
    )
    await session.flush()

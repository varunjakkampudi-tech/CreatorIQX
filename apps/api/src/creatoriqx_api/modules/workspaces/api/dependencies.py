"""The ``require_role`` dependency: the one gate in front of tenant data (P0-054).

Every route that reads or writes workspace data declares the role it needs:

    @router.get("/thing")
    async def read_thing(access: Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]):

The dependency resolves the workspace and user from the session (never from the
request body or a query parameter, which a caller controls), checks the
membership, and hands the route a verified ``WorkspaceAccess``. A caller who is
not a member of the workspace their session names is refused with 403, so a
stale session cannot keep acting in a workspace the user has left.

The cross-tenant harness in ``apps/api/tests/test_cross_tenant.py`` walks every
route in the OpenAPI document and fails if one of them answers a non-member.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from creatoriqx_api.modules.identity.api.dependencies import SessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.identity.domain.session import Session
from creatoriqx_api.modules.workspaces.application.access_service import WorkspaceAccessService
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess


def get_access_service(request: Request) -> WorkspaceAccessService:
    service: WorkspaceAccessService = request.app.state.workspace_access_service
    return service


AccessServiceDep = Annotated[WorkspaceAccessService, Depends(get_access_service)]


def require_role(
    required: Role,
) -> Callable[[Session, WorkspaceAccessService], Awaitable[WorkspaceAccess]]:
    """Build a dependency that admits only members holding at least ``required``."""

    async def dependency(session: SessionDep, service: AccessServiceDep) -> WorkspaceAccess:
        return await service.authorize(
            workspace_id=session.workspace_id,
            user_id=session.user_id,
            required=required,
        )

    return dependency


ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]

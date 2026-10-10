"""Pre-publish QA routes (spec feature 12).

  POST /videos/{video_id}/qa/run   run the checklist against current artifacts
  GET  /videos/{video_id}/qa       the same checklist, as a read

``run`` has no persisted side effect (see ``QaService``'s own docstring: QA
is never a standing record a later approval trusts), so both routes call the
same method - POST is the action a creator takes from the UI, GET is the
read a page can poll without implying a retry of anything. Both still
require the ``Idempotency-Key``/role shape ticket P1D-05 asks for on every
route it lists, POST included.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.publishing.application.qa_service import QaService
from creatoriqx_api.modules.publishing.domain.qa import QaCheck, QaResult
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.platform.idempotency import require_idempotency_key

router = APIRouter(prefix="/videos/{video_id}/qa", tags=["qa"])

EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]
IdempotencyKeyDep = Annotated[str, Depends(require_idempotency_key)]


def get_qa_service(request: Request) -> QaService:
    service: QaService = request.app.state.qa_service
    return service


QaServiceDep = Annotated[QaService, Depends(get_qa_service)]


class QaCheckOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    passed: bool
    reasons: list[str]


class QaResultOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    video_id: uuid.UUID
    passed: bool
    checks: list[QaCheckOut]


@router.post("/run", response_model=QaResultOut, summary="Run the pre-publish QA checklist")
async def run_qa(
    video_id: uuid.UUID,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: QaServiceDep,
    _idempotency_key: IdempotencyKeyDep,
) -> QaResultOut:
    # wants_scheduling defaults to False here: the schedule check only ever
    # matters once a video is linked and approval requests a schedule, which
    # ApprovalService.approve already re-runs QA for with the real value
    # (spec §3's schedule-eligibility check). This read/run pair is for
    # Creation-time feedback before that point.
    result = await service.run(workspace_id=session.workspace_id, video_id=video_id)
    return _out(result)


@router.get("", response_model=QaResultOut, summary="Read the current QA checklist outcome")
async def get_qa(
    video_id: uuid.UUID, access: ViewerAccessDep, service: QaServiceDep
) -> QaResultOut:
    result = await service.run(workspace_id=access.workspace_id, video_id=video_id)
    return _out(result)


def _check_out(check: QaCheck) -> QaCheckOut:
    return QaCheckOut(id=check.id.value, passed=check.passed, reasons=list(check.reasons))


def _out(result: QaResult) -> QaResultOut:
    return QaResultOut(
        video_id=result.video_id,
        passed=result.passed,
        checks=[_check_out(check) for check in result.checks],
    )

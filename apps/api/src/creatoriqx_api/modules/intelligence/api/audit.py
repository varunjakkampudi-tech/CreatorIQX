"""Channel audit routes (spec §4 feature #2).

POST /intelligence/channels/{channel_id}/audit   run an audit now
GET  /intelligence/channels/{channel_id}/recommendations  list its findings
POST /intelligence/recommendations/{id}/accept   mark accepted
POST /intelligence/recommendations/{id}/dismiss  mark dismissed
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep, SessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.intelligence.application.audit_service import ChannelAuditService
from creatoriqx_api.modules.intelligence.application.ports import RecommendationStore
from creatoriqx_api.modules.intelligence.domain.recommendation import (
    EvidenceStrength,
    Recommendation,
    RecommendationStatus,
    RecommendationType,
)
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def get_audit_service(request: Request) -> ChannelAuditService:
    service: ChannelAuditService = request.app.state.channel_audit_service
    return service


def get_recommendation_store(request: Request) -> RecommendationStore:
    store: RecommendationStore = request.app.state.recommendation_store
    return store


AuditServiceDep = Annotated[ChannelAuditService, Depends(get_audit_service)]
RecommendationStoreDep = Annotated[RecommendationStore, Depends(get_recommendation_store)]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]


class RecommendationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    channel_id: uuid.UUID | None
    type: RecommendationType
    source: str
    recommendation: str
    evidence: str
    confidence: float
    evidence_strength: EvidenceStrength
    sample_size: int
    status: RecommendationStatus

    @classmethod
    def from_domain(cls, rec: Recommendation) -> RecommendationOut:
        return cls(
            id=rec.id,
            channel_id=rec.channel_id,
            type=rec.type,
            source=rec.source,
            recommendation=rec.recommendation,
            evidence=rec.evidence,
            confidence=rec.confidence,
            evidence_strength=rec.evidence_strength,
            sample_size=rec.sample_size,
            status=rec.status,
        )


@router.post(
    "/channels/{channel_id}/audit",
    response_model=list[RecommendationOut],
    summary="Run a channel audit now",
)
async def run_audit(
    channel_id: uuid.UUID,
    session: CsrfSessionDep,
    _access: ViewerAccessDep,
    service: AuditServiceDep,
) -> list[RecommendationOut]:
    recommendations = await service.run(workspace_id=session.workspace_id, channel_id=channel_id)
    return [RecommendationOut.from_domain(rec) for rec in recommendations]


@router.get(
    "/channels/{channel_id}/recommendations",
    response_model=list[RecommendationOut],
    summary="A channel's recommendations",
)
async def list_recommendations(
    channel_id: uuid.UUID,
    response: Response,
    session: SessionDep,
    _access: ViewerAccessDep,
    store: RecommendationStoreDep,
) -> list[RecommendationOut]:
    response.headers["Cache-Control"] = "no-store"
    recommendations = await store.list_for_channel(
        workspace_id=session.workspace_id, channel_id=channel_id
    )
    return [RecommendationOut.from_domain(rec) for rec in recommendations]


@router.post(
    "/recommendations/{recommendation_id}/accept",
    response_model=RecommendationOut,
    summary="Accept a recommendation",
)
async def accept_recommendation(
    recommendation_id: uuid.UUID,
    session: CsrfSessionDep,
    _access: ViewerAccessDep,
    store: RecommendationStoreDep,
) -> RecommendationOut:
    rec = await store.set_status(
        workspace_id=session.workspace_id,
        recommendation_id=recommendation_id,
        status=RecommendationStatus.ACCEPTED.value,
    )
    return RecommendationOut.from_domain(rec)


@router.post(
    "/recommendations/{recommendation_id}/dismiss",
    response_model=RecommendationOut,
    summary="Dismiss a recommendation",
)
async def dismiss_recommendation(
    recommendation_id: uuid.UUID,
    session: CsrfSessionDep,
    _access: ViewerAccessDep,
    store: RecommendationStoreDep,
) -> RecommendationOut:
    rec = await store.set_status(
        workspace_id=session.workspace_id,
        recommendation_id=recommendation_id,
        status=RecommendationStatus.DISMISSED.value,
    )
    return RecommendationOut.from_domain(rec)

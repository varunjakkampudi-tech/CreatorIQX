"""Transcript routes (spec feature 22).

POST /videos/{video_id}/transcripts/paste    paste plain text
POST /videos/{video_id}/transcripts/upload   upload a transcript file (.srt/.vtt/.txt)
GET  /videos/{video_id}/transcripts          list this video's transcript versions
GET  /videos/{video_id}/transcripts/{id}     one transcript, with its segments

``youtube_captions`` and ``local_whisper`` have no route here: both raise
``TranscriptSourceUnavailableError`` from the service (see its docstring),
and exposing a route that always 501s would be noise, not a capability.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.transcripts.application.transcript_service import TranscriptService
from creatoriqx_api.modules.transcripts.domain.errors import TranscriptNotFoundError
from creatoriqx_api.modules.transcripts.domain.transcript import Transcript
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess

router = APIRouter(prefix="/videos/{video_id}/transcripts", tags=["transcripts"])

EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]


def get_transcript_service(request: Request) -> TranscriptService:
    service: TranscriptService = request.app.state.transcript_service
    return service


TranscriptServiceDep = Annotated[TranscriptService, Depends(get_transcript_service)]


class PasteTranscriptIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    language: str = "en"


class UploadTranscriptIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    content: str
    language: str = "en"


class SegmentOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_seconds: float
    end_seconds: float | None
    text: str
    confidence: float | None


class TranscriptOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    video_id: uuid.UUID | None
    source: str
    language: str
    version: int
    parent_transcript_id: uuid.UUID | None
    is_fully_timed: bool
    segments: list[SegmentOut]


@router.post("/paste", response_model=TranscriptOut, status_code=201, summary="Paste a transcript")
async def paste_transcript(
    video_id: uuid.UUID,
    body: PasteTranscriptIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: TranscriptServiceDep,
) -> TranscriptOut:
    transcript = await service.import_pasted_text(
        workspace_id=session.workspace_id,
        video_id=video_id,
        text=body.text,
        language=body.language,
    )
    return _out(transcript)


@router.post(
    "/upload", response_model=TranscriptOut, status_code=201, summary="Upload a transcript file"
)
async def upload_transcript(
    video_id: uuid.UUID,
    body: UploadTranscriptIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: TranscriptServiceDep,
) -> TranscriptOut:
    transcript = await service.import_uploaded_file(
        workspace_id=session.workspace_id,
        video_id=video_id,
        filename=body.filename,
        content=body.content,
        language=body.language,
    )
    return _out(transcript)


@router.get("", response_model=list[TranscriptOut], summary="This video's transcript versions")
async def list_transcripts(
    video_id: uuid.UUID, access: ViewerAccessDep, service: TranscriptServiceDep
) -> list[TranscriptOut]:
    transcripts = await service.list_for_video(workspace_id=access.workspace_id, video_id=video_id)
    return [_out(t) for t in transcripts]


@router.get("/{transcript_id}", response_model=TranscriptOut, summary="One transcript")
async def get_transcript(
    video_id: uuid.UUID,
    transcript_id: uuid.UUID,
    access: ViewerAccessDep,
    service: TranscriptServiceDep,
) -> TranscriptOut:
    transcript = await service.get(workspace_id=access.workspace_id, transcript_id=transcript_id)
    if transcript is None or transcript.video_id != video_id:
        raise TranscriptNotFoundError()
    return _out(transcript)


def _out(transcript: Transcript) -> TranscriptOut:
    return TranscriptOut(
        id=transcript.id,
        video_id=transcript.video_id,
        source=transcript.source.value,
        language=transcript.language,
        version=transcript.version,
        parent_transcript_id=transcript.parent_transcript_id,
        is_fully_timed=transcript.is_fully_timed,
        segments=[
            SegmentOut(
                start_seconds=s.start_seconds,
                end_seconds=s.end_seconds,
                text=s.text,
                confidence=s.confidence,
            )
            for s in transcript.segments
        ],
    )

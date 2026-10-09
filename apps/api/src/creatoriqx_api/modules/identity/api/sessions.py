"""Session routes: who am I, and sign out (P0-051, ADR 0010).

  GET  /auth/session   the current session's user and CSRF token
  POST /auth/logout    end the session (needs the X-CSRF-Token header)

These are mounted whether or not Google login is configured, because a
session can outlive the login route that created it.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import (
    CsrfSessionDep,
    SessionDep,
    SessionServiceDep,
    clear_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class SessionOut(BaseModel):
    """The signed-in user and the token the client must send on unsafe requests."""

    model_config = ConfigDict(frozen=True)

    subject: str
    email: str
    csrf_token: str
    expires_at: datetime


@router.get("/session", response_model=SessionOut, summary="Current session")
async def read_session(response: Response, session: SessionDep) -> SessionOut:
    response.headers["Cache-Control"] = "no-store"
    return SessionOut(
        subject=session.subject,
        email=session.email,
        csrf_token=session.csrf_token,
        expires_at=session.expires_at,
    )


@router.post("/logout", status_code=204, summary="End the current session")
async def logout(session: CsrfSessionDep, service: SessionServiceDep) -> Response:
    await service.end(session.id)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    clear_session_cookie(response)
    return response

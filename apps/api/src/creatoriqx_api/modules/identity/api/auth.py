"""Google OIDC login routes (spec A10, ADR 0004, ADR 0010).

  GET  /auth/login      start the flow; store it server-side behind a single-use cookie
  GET  /auth/callback   finish the flow; rotate to a fresh session; redirect to the app

The flow record is single-use (``take``): a replayed callback finds nothing and fails.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from creatoriqx_api.modules.identity.api.dependencies import (
    FLOW_COOKIE,
    SESSION_COOKIE,
    SessionServiceDep,
    clear_flow_cookie,
    set_flow_cookie,
    set_session_cookie,
)
from creatoriqx_api.modules.identity.application.auth_service import AuthService, LoginFlowState
from creatoriqx_api.modules.identity.application.ports import KeyValueStore
from creatoriqx_api.modules.identity.domain.errors import (
    AuthenticationError,
    OIDCStateMismatchError,
)
from creatoriqx_api.platform.logging import get_logger

router = APIRouter(prefix="/auth", tags=["auth"])
_logger = get_logger("creatoriqx.auth")
_FLOW_KEY_PREFIX = "oidc_flow:"


def get_auth_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth_service
    return service


def get_key_value_store(request: Request) -> KeyValueStore:
    store: KeyValueStore = request.app.state.key_value_store
    return store


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
KeyValueStoreDep = Annotated[KeyValueStore, Depends(get_key_value_store)]


def _flow_record(flow: LoginFlowState) -> dict[str, str]:
    return {
        "state": flow.state,
        "nonce": flow.nonce,
        "code_verifier": flow.code_verifier,
        "redirect_uri": flow.redirect_uri,
    }


def _flow_from_record(record: dict[str, str]) -> LoginFlowState:
    return LoginFlowState(
        state=record["state"],
        nonce=record["nonce"],
        code_verifier=record["code_verifier"],
        redirect_uri=record["redirect_uri"],
    )


@router.get("/login", summary="Start the Google OIDC login flow")
async def login(
    request: Request,
    auth_service: AuthServiceDep,
    store: KeyValueStoreDep,
) -> RedirectResponse:
    callback_url = str(request.url_for("auth_callback"))
    authorization_url, flow = auth_service.start_login(callback_url)

    flow_id = secrets.token_urlsafe(32)
    ttl = request.app.state.settings.oidc_flow_ttl_seconds
    await store.put(f"{_FLOW_KEY_PREFIX}{flow_id}", _flow_record(flow), ttl)

    response = RedirectResponse(url=authorization_url, status_code=302)
    set_flow_cookie(response, flow_id, ttl)
    _logger.info("oidc_login_started")
    return response


@router.get("/callback", name="auth_callback", summary="Finish the Google OIDC login flow")
async def callback(
    request: Request,
    auth_service: AuthServiceDep,
    store: KeyValueStoreDep,
    sessions: SessionServiceDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    if error:
        _logger.warning("oidc_callback_error", error=error)
        raise AuthenticationError(f"Google returned error: {error}")
    if not code or not state:
        raise AuthenticationError("Missing code or state parameter")

    flow_id = request.cookies.get(FLOW_COOKIE)
    record = await store.take(f"{_FLOW_KEY_PREFIX}{flow_id}") if flow_id else None
    if record is None:
        raise OIDCStateMismatchError("No login in progress, or it has expired")

    user = await auth_service.complete_login(
        code=code,
        callback_state=state,
        flow_state=_flow_from_record(record),
    )

    session = await sessions.rotate(
        previous_session_id=request.cookies.get(SESSION_COOKIE),
        subject=user.subject,
        email=user.email,
    )

    settings = request.app.state.settings
    response = RedirectResponse(url=f"{settings.app_base_url.rstrip('/')}/", status_code=303)
    set_session_cookie(response, session)
    clear_flow_cookie(response)
    _logger.info("oidc_login_succeeded", subject=user.subject)
    return response

"""Authentication API routes (spec §10, ADR 0004).

These routes handle the OIDC login flow:
  GET  /auth/login     -> redirect to Google
  GET  /auth/callback  -> handle the callback, validate the token
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from creatoriqx_api.modules.identity.application.auth_service import AuthService, LoginFlowState
from creatoriqx_api.modules.identity.domain.auth import OIDCUserInfo
from creatoriqx_api.modules.identity.domain.errors import (
    AuthenticationError,
    OIDCStateMismatchError,
)
from creatoriqx_api.platform.logging import get_logger

router = APIRouter(prefix="/auth", tags=["auth"])
_logger = get_logger("creatoriqx.auth")

# The session key where we store the OIDC flow state.
_SESSION_OIDC_KEY = "oidc_flow"


def _get_auth_service(request: Request) -> AuthService:
    """Resolve the AuthService from app state (set during app startup)."""
    service: AuthService = request.app.state.auth_service
    return service


@router.get("/login", summary="Start the Google OIDC login flow")
async def login(
    request: Request,
    auth_service: Annotated[AuthService, Depends(_get_auth_service)],
) -> RedirectResponse:
    """Generate the authorization URL and redirect the user to Google."""
    callback_url = str(request.url_for("auth_callback"))
    authorization_url, flow_state = auth_service.start_login(callback_url)

    # Store flow state in the session (P0-051 will add proper sessions;
    # for now we use a simple dict on the request state).
    request.session["oidc_flow"] = {
        "state": flow_state.state,
        "nonce": flow_state.nonce,
        "code_verifier": flow_state.code_verifier,
        "redirect_uri": flow_state.redirect_uri,
    }

    _logger.info("oidc_login_started")
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/callback", name="auth_callback", summary="Handle Google OIDC callback")
async def callback(
    request: Request,
    auth_service: Annotated[AuthService, Depends(_get_auth_service)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    """Exchange the authorization code, validate the token, return user info.

    In Phase 0 this returns JSON with the validated user info.
    P0-051 will add session creation and a redirect to the app.
    """
    if error:
        _logger.warning("oidc_callback_error", error=error)
        raise AuthenticationError(f"Google returned error: {error}")

    if not code or not state:
        raise AuthenticationError("Missing code or state parameter")

    # Retrieve flow state from session.
    raw_flow = request.session.pop(_SESSION_OIDC_KEY, None)
    if not raw_flow:
        raise OIDCStateMismatchError("No OIDC flow in progress")

    flow_state = LoginFlowState(
        state=raw_flow["state"],
        nonce=raw_flow["nonce"],
        code_verifier=raw_flow["code_verifier"],
        redirect_uri=raw_flow["redirect_uri"],
    )

    user_info: OIDCUserInfo = await auth_service.complete_login(
        code=code,
        callback_state=state,
        flow_state=flow_state,
    )

    _logger.info("oidc_login_succeeded", email=user_info.email)

    # P0-053 will create user + workspace here.
    # For now, return the validated user info.
    return JSONResponse(
        {
            "status": "authenticated",
            "user": {
                "subject": user_info.subject,
                "email": user_info.email,
                "name": user_info.name,
                "picture": user_info.picture,
            },
        }
    )

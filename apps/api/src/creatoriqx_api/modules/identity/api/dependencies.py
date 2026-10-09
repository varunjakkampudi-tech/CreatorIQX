"""Request-scoped session dependencies: who is calling, and did they prove it (ADR 0010).

Cookie attributes, always:

* ``Secure``: sent only over HTTPS. Browsers treat ``http://localhost`` as a
  secure context, so local development works with the same attributes;
* ``__Host-`` prefix on the session cookie: the browser refuses it unless it
  is Secure, has ``Path=/`` and no ``Domain``, so a sibling host cannot plant one;
* ``HttpOnly``: scripts cannot read the session id;
* ``SameSite=Lax``: cross-site subrequests do not carry the session.

Only a session cookie plus a valid CSRF header passes ``csrf_protected_session``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Response

from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.errors import (
    RateLimitExceededError,
    SessionRequiredError,
)
from creatoriqx_api.modules.identity.domain.session import Session
from creatoriqx_api.platform.rate_limit import RateLimiter

SESSION_COOKIE = "__Host-creatoriqx_session"
FLOW_COOKIE = "creatoriqx_oidc_flow"
FLOW_COOKIE_PATH = "/api/v1/auth"
CSRF_HEADER = "X-CSRF-Token"


def get_session_service(request: Request) -> SessionService:
    service: SessionService = request.app.state.session_service
    return service


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


async def current_session(request: Request, service: SessionServiceDep) -> Session:
    """The live session behind the request's cookie, or a 401 problem."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise SessionRequiredError()
    return await service.authenticate(raw)


SessionDep = Annotated[Session, Depends(current_session)]


async def csrf_protected_session(
    request: Request, session: SessionDep, service: SessionServiceDep
) -> Session:
    """Use on every state-changing route: the session plus a matching CSRF header."""
    service.verify_csrf(session, request.headers.get(CSRF_HEADER))
    return session


CsrfSessionDep = Annotated[Session, Depends(csrf_protected_session)]


def set_session_cookie(response: Response, session: Session) -> None:
    max_age = max(1, int((session.expires_at - session.created_at).total_seconds()))
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session.id,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def set_flow_cookie(response: Response, flow_id: str, ttl_seconds: int) -> None:
    response.set_cookie(
        key=FLOW_COOKIE,
        value=flow_id,
        max_age=ttl_seconds,
        path=FLOW_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_flow_cookie(response: Response) -> None:
    response.delete_cookie(
        key=FLOW_COOKIE,
        path=FLOW_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


async def enforce_auth_rate_limit(request: Request, limiter: RateLimiterDep) -> None:
    """Token-bucket limit on /auth/login and /auth/callback (P0-055).

    Two independent buckets: always by client IP (the only identity known
    before login succeeds), and additionally by session id when a session
    cookie is present (an already-signed-in browser hammering the endpoint).
    Either bucket running out raises a 429 problem+json with Retry-After.
    """
    settings = request.app.state.settings
    capacity = settings.auth_rate_limit_capacity
    refill_per_second = capacity / settings.auth_rate_limit_window_seconds

    client_ip = request.client.host if request.client else "unknown"
    ip_result = await limiter.check(
        f"auth:ip:{client_ip}", capacity=capacity, refill_per_second=refill_per_second
    )
    if not ip_result.allowed:
        raise RateLimitExceededError(ip_result.retry_after_seconds)

    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        session_result = await limiter.check(
            f"auth:session:{session_id}", capacity=capacity, refill_per_second=refill_per_second
        )
        if not session_result.allowed:
            raise RateLimitExceededError(session_result.retry_after_seconds)

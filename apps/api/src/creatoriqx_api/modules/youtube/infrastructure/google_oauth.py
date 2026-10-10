"""Google OAuth 2.0 adapter for the YouTube connection (spec §3, §10).

A separate OAuth 2.0 client from login (``GoogleOIDCProvider``): different
client id/secret, different scopes, and ``access_type=offline`` so a refresh
token comes back - the connection must keep working long after the browser
tab that approved it is gone, unlike a login session.

Endpoints verified against Google's current OAuth 2.0 documentation
(https://developers.google.com/identity/protocols/oauth2/web-server), same
family of endpoints already used by ``identity.infrastructure.google_oidc``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from creatoriqx_api.modules.youtube.application.ports import YouTubeOAuthProvider as _Protocol
from creatoriqx_api.modules.youtube.domain.connection import CONNECT_SCOPES, OAuthTokens
from creatoriqx_api.modules.youtube.domain.errors import YouTubeOAuthError

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105


class GoogleYouTubeOAuthProvider:
    """Google implementation of the ``YouTubeOAuthProvider`` port."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def build_authorization_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(CONNECT_SCOPES),
            "state": state,
            "access_type": "offline",  # required to receive a refresh token
            "prompt": "consent",  # ensures a refresh token even on re-consent
            "include_granted_scopes": "true",  # incremental authorization (spec §10)
        }
        return f"{GOOGLE_AUTH_ENDPOINT}?{httpx.QueryParams(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await _post_token(
                client,
                {
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        data = resp.json()
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            # Google omits refresh_token on a repeat consent for the same
            # client+scopes+user without prompt=consent forcing it; treat a
            # missing one as a hard error rather than silently storing a
            # connection that cannot be refreshed past its access token's life.
            raise YouTubeOAuthError(
                detail="Google did not return a refresh token for this connection"
            )
        return _tokens_from_response(data, refresh_token=refresh_token)

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await _post_token(
                client,
                {
                    "refresh_token": refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                },
            )
        data = resp.json()
        # Google does not re-send the refresh token on a refresh grant: the
        # original one keeps working, so the caller should keep storing it.
        return _tokens_from_response(data, refresh_token=refresh_token)


async def _post_token(client: httpx.AsyncClient, data: dict[str, str]) -> httpx.Response:
    try:
        resp = await client.post(
            GOOGLE_TOKEN_ENDPOINT, data=data, headers={"Accept": "application/json"}, timeout=10.0
        )
    except httpx.HTTPError as exc:
        raise YouTubeOAuthError(detail=f"HTTP error contacting Google: {exc}") from exc
    if resp.status_code != 200:
        raise YouTubeOAuthError(
            detail=f"Google token endpoint returned {resp.status_code}: {resp.text[:200]}"
        )
    return resp


def _tokens_from_response(data: dict[str, object], *, refresh_token: str) -> OAuthTokens:
    access_token = data.get("access_token")
    expires_in = data.get("expires_in")
    scope = data.get("scope", "")
    if not isinstance(access_token, str) or not isinstance(expires_in, int | float):
        raise YouTubeOAuthError(detail="Google token response missing access_token/expires_in")
    return OAuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.now(UTC) + timedelta(seconds=float(expires_in)),
        scopes=tuple(str(scope).split()) if scope else CONNECT_SCOPES,
    )


# Confirms this module satisfies the port at import time (mypy structural
# check); never instantiated.
def _typecheck_only(provider: GoogleYouTubeOAuthProvider) -> _Protocol:
    return provider

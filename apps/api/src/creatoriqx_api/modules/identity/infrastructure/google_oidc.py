"""Google OIDC provider adapter (ADR 0004, spec §10).

Implements the ``OIDCProvider`` port using httpx for HTTP calls and
manual JWT validation (PyJWT + Google JWKS). Authlib was evaluated but
httpx + PyJWT is lighter and avoids pulling in Authlib's large surface
for one simple flow.

Google's OpenID Connect endpoints (verified 2026-01):
    Discovery:     https://accounts.google.com/.well-known/openid-configuration
    Authorization: https://accounts.google.com/o/oauth2/v2/auth
    Token:         https://oauth2.googleapis.com/token
    JWKS:          https://www.googleapis.com/oauth2/v3/certs
    Issuer:        https://accounts.google.com
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from creatoriqx_api.modules.identity.application.auth_service import AuthService
from creatoriqx_api.modules.identity.domain.auth import (
    OIDCProviderError,
    OIDCTokenValidationError,
    OIDCUserInfo,
)

# Google OIDC constants.
GOOGLE_ISSUER = "https://accounts.google.com"
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105
GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"

# Only identity scopes (ADR 0004: login client never requests YouTube scopes).
LOGIN_SCOPES = "openid email profile"


class GoogleOIDCProvider:
    """Google implementation of the ``OIDCProvider`` protocol."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._jwks_client = PyJWKClient(GOOGLE_JWKS_URI, cache_keys=True)

    def build_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_verifier: str,
    ) -> str:
        """Build the Google authorization URL with PKCE (S256)."""
        code_challenge = AuthService.generate_code_challenge(code_verifier)
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": LOGIN_SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "online",  # No refresh token for login
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_ENDPOINT}?{httpx.QueryParams(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, object]:
        """Exchange the authorization code for tokens at Google's token endpoint."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    GOOGLE_TOKEN_ENDPOINT,
                    data={
                        "code": code,
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                        "code_verifier": code_verifier,
                    },
                    headers={"Accept": "application/json"},
                    timeout=10.0,
                )
            except httpx.HTTPError as exc:
                raise OIDCProviderError(f"HTTP error during token exchange: {exc}") from exc

        if resp.status_code != 200:
            raise OIDCProviderError(
                f"Token endpoint returned {resp.status_code}: {resp.text[:200]}"
            )

        data: dict[str, object] = resp.json()
        if "id_token" not in data:
            raise OIDCProviderError("Token response missing id_token")
        return data

    async def validate_id_token(
        self,
        token_response: dict[str, object],
        nonce: str,
    ) -> OIDCUserInfo:
        """Validate the ID token from Google's token response.

        Checks: signature (via JWKS), issuer, audience, expiry, nonce,
        email_verified. Returns ``OIDCUserInfo`` on success.
        """
        raw_token = token_response.get("id_token")
        if not isinstance(raw_token, str):
            raise OIDCTokenValidationError("id_token is not a string")

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(raw_token)
        except (jwt.exceptions.PyJWKClientError, jwt.exceptions.DecodeError) as exc:
            raise OIDCTokenValidationError(f"JWKS key lookup failed: {exc}") from exc

        claims = self._decode_jwt(raw_token, signing_key)
        return self._extract_user_from_claims(claims, nonce)

    def _decode_jwt(self, raw_token: str, signing_key: jwt.PyJWK) -> dict[str, Any]:
        """Decode and verify the JWT signature, audience, issuer and expiry."""
        try:
            claims: dict[str, Any] = jwt.decode(
                raw_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=GOOGLE_ISSUER,
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
                leeway=30,  # clock skew tolerance
            )
            return claims
        except jwt.ExpiredSignatureError as exc:
            raise OIDCTokenValidationError("ID token has expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise OIDCTokenValidationError("ID token audience mismatch") from exc
        except jwt.InvalidIssuerError as exc:
            raise OIDCTokenValidationError("ID token issuer mismatch") from exc
        except jwt.InvalidTokenError as exc:
            raise OIDCTokenValidationError(f"ID token validation failed: {exc}") from exc

    @staticmethod
    def _extract_user_from_claims(claims: dict[str, Any], nonce: str) -> OIDCUserInfo:
        """Validate business-level claims and build ``OIDCUserInfo``."""
        # Nonce check (not done by PyJWT automatically).
        if claims.get("nonce") != nonce:
            raise OIDCTokenValidationError("Nonce mismatch")

        # iat freshness: reject tokens issued more than 10 minutes ago.
        iat = claims.get("iat")
        if isinstance(iat, int | float) and time.time() - iat > 600:
            raise OIDCTokenValidationError("ID token issued too long ago")

        # email_verified required (ADR 0004).
        if not claims.get("email_verified"):
            raise OIDCTokenValidationError("Email not verified by Google")

        email = claims.get("email")
        if not isinstance(email, str) or not email:
            raise OIDCTokenValidationError("ID token missing email claim")

        return OIDCUserInfo(
            subject=str(claims["sub"]),
            email=email,
            name=claims.get("name"),
            picture=claims.get("picture"),
        )

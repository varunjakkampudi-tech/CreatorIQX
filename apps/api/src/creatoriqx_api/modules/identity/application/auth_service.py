"""OIDC login application service (spec §10, ADR 0004).

Orchestrates the authorization code flow with PKCE, state and nonce.
Delegates token exchange and validation to the ``OIDCProvider`` port.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from creatoriqx_api.modules.identity.domain.auth import (
    OIDCProviderError,
    OIDCTokenValidationError,
    OIDCUserInfo,
)
from creatoriqx_api.modules.identity.domain.errors import (
    AuthenticationError,
    EmailNotAllowedError,
    OIDCStateMismatchError,
)

if TYPE_CHECKING:
    from creatoriqx_api.modules.identity.domain.auth import OIDCProvider


@dataclass(frozen=True, slots=True)
class LoginFlowState:
    """Values stored in the server-side session during the OIDC dance."""

    state: str
    nonce: str
    code_verifier: str
    redirect_uri: str


class AuthService:
    """Application-layer orchestrator for OIDC login.

    Stateless: the caller (API route) stores ``LoginFlowState`` in the
    session and retrieves it in the callback.
    """

    def __init__(
        self,
        provider: OIDCProvider,
        allowed_emails: frozenset[str],
    ) -> None:
        self._provider = provider
        self._allowed_emails = allowed_emails

    def start_login(self, redirect_uri: str) -> tuple[str, LoginFlowState]:
        """Generate the authorization URL and the state to store in the session.

        Returns ``(authorization_url, flow_state)``.
        """
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)

        authorization_url = self._provider.build_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
        )
        flow_state = LoginFlowState(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )
        return authorization_url, flow_state

    async def complete_login(
        self,
        code: str,
        callback_state: str,
        flow_state: LoginFlowState,
    ) -> OIDCUserInfo:
        """Exchange the code and validate the ID token.

        Raises:
            OIDCStateMismatchError: callback state does not match session.
            AuthenticationError: token exchange or validation failed.
            EmailNotAllowedError: email not on the allow-list.
        """
        if not secrets.compare_digest(callback_state, flow_state.state):
            raise OIDCStateMismatchError("State parameter mismatch")

        try:
            token_response = await self._provider.exchange_code(
                code=code,
                redirect_uri=flow_state.redirect_uri,
                code_verifier=flow_state.code_verifier,
            )
        except OIDCProviderError as exc:
            raise AuthenticationError(f"Token exchange failed: {exc}") from exc

        try:
            user_info = await self._provider.validate_id_token(
                token_response=token_response,
                nonce=flow_state.nonce,
            )
        except OIDCTokenValidationError as exc:
            raise AuthenticationError(f"ID token validation failed: {exc.reason}") from exc

        if not self._is_email_allowed(user_info.email):
            raise EmailNotAllowedError(f"Email {user_info.email} is not on the allow-list")

        return user_info

    def _is_email_allowed(self, email: str) -> bool:
        """Check the email against the allow-list (case-insensitive)."""
        if not self._allowed_emails:
            return True  # empty list means no restriction
        return email.lower() in {e.lower() for e in self._allowed_emails}

    @staticmethod
    def generate_code_challenge(code_verifier: str) -> str:
        """S256 code challenge from the verifier (RFC 7636)."""
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        # Base64url-encode without padding
        import base64

        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

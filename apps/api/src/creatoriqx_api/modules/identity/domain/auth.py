"""OIDC authentication domain types (spec §10, ADR 0004).

Pure domain: no framework, no infrastructure imports. Defines the
contracts (protocols) that infrastructure adapters implement and the
value objects that flow through the application layer.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol


@dataclasses.dataclass(frozen=True, slots=True)
class OIDCUserInfo:
    """Validated claims from the ID token.

    ``email_verified`` is always True by the time this object exists:
    the validator rejects unverified emails before constructing it.
    """

    subject: str  # Google 'sub' claim
    email: str
    name: str | None = None
    picture: str | None = None


class OIDCProviderError(Exception):
    """Raised when the OIDC provider rejects the flow."""


class OIDCTokenValidationError(Exception):
    """Raised when the ID token fails validation (any check)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class OIDCProvider(Protocol):
    """Port for an external OIDC identity provider (ADR 0004)."""

    def build_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_verifier: str,
    ) -> str:
        """Return the full authorization URL to redirect the user to."""
        ...

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, object]:
        """Exchange the authorization code for tokens. Returns the token response dict."""
        ...

    async def validate_id_token(
        self,
        token_response: dict[str, object],
        nonce: str,
    ) -> OIDCUserInfo:
        """Validate the ID token and return verified user info.

        Raises ``OIDCTokenValidationError`` on any validation failure:
        bad issuer, wrong audience, expired, nonce mismatch, unverified
        email, or bad signature.
        """
        ...

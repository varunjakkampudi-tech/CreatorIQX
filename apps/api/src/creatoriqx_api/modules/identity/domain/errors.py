"""Identity module domain errors (spec §12)."""

from __future__ import annotations

from creatoriqx_api.platform.errors import DomainError


class AuthenticationError(DomainError):
    """The login flow failed for a security-relevant reason."""

    status = 401
    title = "Authentication failed"
    code = "authentication-failed"


class EmailNotAllowedError(DomainError):
    """The authenticated email is not on the allow-list."""

    status = 403
    title = "Email not permitted"
    code = "email-not-allowed"


class OIDCStateMismatchError(DomainError):
    """The state parameter from the callback does not match the session."""

    status = 400
    title = "Invalid login state"
    code = "oidc-state-mismatch"

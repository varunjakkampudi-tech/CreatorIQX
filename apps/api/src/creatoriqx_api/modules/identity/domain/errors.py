"""Identity module domain errors (spec A12)."""

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
    """The state parameter from the callback does not match the login flow."""

    status = 400
    title = "Invalid login state"
    code = "oidc-state-mismatch"


class SessionRequiredError(DomainError):
    """The request carries no valid session cookie."""

    status = 401
    title = "Sign in required"
    code = "session-required"


class SessionExpiredError(DomainError):
    """The session timed out (idle or absolute). Sign in again."""

    status = 401
    title = "Session expired"
    code = "session-expired"


class CSRFTokenError(DomainError):
    """An unsafe request did not carry the session's CSRF token."""

    status = 403
    title = "Invalid CSRF token"
    code = "csrf-token-invalid"


class RateLimitExceededError(DomainError):
    """A rate-limit bucket (spec §6, §10; P0-055) ran out of tokens."""

    status = 429
    title = "Too many requests"
    code = "rate-limited"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            detail=f"Retry after {retry_after_seconds} seconds",
            headers={"Retry-After": str(retry_after_seconds)},
        )
        self.retry_after_seconds = retry_after_seconds

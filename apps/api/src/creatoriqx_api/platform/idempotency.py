"""The ``Idempotency-Key`` header requirement for mutating routes (spec §6, §8:
"Idempotency-Key header on mutating endpoints").

This is deliberately the minimum the spec requires today: presence
validation only. The durable ``idempotency_keys`` table (jobs module,
``apps/api/src/creatoriqx_api/modules/jobs/infrastructure/tables.py``)
already exists for a later ticket to build real at-most-once response
caching on top of; nothing in this codebase does that yet, on any route, so
there was no existing enforcement pattern to match here. Routes that need
true dedup today (re-approving a video, for example) enforce it at the
domain level instead (``ApprovalService.approve`` returning the same
snapshot on a second call) rather than through this header.
"""

from __future__ import annotations

from fastapi import Header

from creatoriqx_api.platform.errors import DomainError


class IdempotencyKeyMissingError(DomainError):
    """A mutating route was called with no (or a blank) ``Idempotency-Key`` header."""

    status = 400
    title = "Idempotency-Key header is required"
    code = "idempotency-key-required"


async def require_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    """Use on every mutating route: ``_: Annotated[str, Depends(require_idempotency_key)]``."""
    if idempotency_key is None or not idempotency_key.strip():
        raise IdempotencyKeyMissingError()
    return idempotency_key

"""The usage event contract (spec §6 observability, §9 cost/usage; ticket P0-062).

``ALLOWED_PROPERTIES`` is the one place that decides which property keys an
event name may carry. Anything else is dropped before the event ever reaches
a sink, so a caller can never widen what gets persisted just by passing more
kwargs - the allow-list, not the caller, decides.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: event name -> the only property keys that may be stored for it.
#: A name with no entry here allows no properties at all.
ALLOWED_PROPERTIES: Mapping[str, frozenset[str]] = {
    "auth.login_succeeded": frozenset({"method", "is_first_login"}),
}


def sanitize_properties(name: str, properties: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Drop every property key not on ``name``'s allow-list.

    Returns ``None`` (not ``{}``) when nothing survives, so a sink can store
    JSON null rather than an empty object for "no properties".
    """
    if not properties:
        return None
    allowed = ALLOWED_PROPERTIES.get(name, frozenset())
    filtered = {key: value for key, value in properties.items() if key in allowed}
    return filtered or None


@dataclass(frozen=True, slots=True)
class UsageEventRecord:
    """One product usage event (schema_version lets a name's shape evolve)."""

    name: str
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    schema_version: int = 1
    properties: dict[str, Any] | None = None

    def sanitized(self) -> UsageEventRecord:
        """This record with ``properties`` reduced to ``name``'s allow-list."""
        return UsageEventRecord(
            name=self.name,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            schema_version=self.schema_version,
            properties=sanitize_properties(self.name, self.properties),
        )

"""The usage-event recording use case (ticket P0-062).

The one place a caller actually asks for an event to be recorded. It applies
the domain allow-list before the sink ever sees the event, so every sink
implementation (SQL today, anything else later) can trust what it's handed
and never has to re-implement the drop logic itself.
"""

from __future__ import annotations

import uuid
from typing import Any

from creatoriqx_api.modules.telemetry.application.ports import TelemetrySink
from creatoriqx_api.modules.telemetry.domain.usage_event import UsageEventRecord


class UsageEventRecorder:
    """Sanitizes then emits usage events through a ``TelemetrySink``."""

    def __init__(self, sink: TelemetrySink) -> None:
        self._sink = sink

    async def record(
        self,
        name: str,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        schema_version: int = 1,
        properties: dict[str, Any] | None = None,
    ) -> None:
        event = UsageEventRecord(
            name=name,
            workspace_id=workspace_id,
            user_id=user_id,
            schema_version=schema_version,
            properties=properties,
        ).sanitized()
        await self._sink.emit(event)

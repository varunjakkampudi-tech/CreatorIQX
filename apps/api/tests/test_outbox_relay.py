"""Unit tests for the outbox relay's dispatch logic (P0-061, ADR 0003/§6).

No database: ``OutboxGateway`` is faked here, so this exercises
``HandlerRegistry`` and ``OutboxRelay`` in isolation. The real
``SqlOutboxGateway`` behavior (``FOR UPDATE SKIP LOCKED``, crash-redelivery)
is proven against a real Postgres in
``tests/integration/test_outbox_relay_db.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from creatoriqx_api.modules.jobs.application.outbox_relay import HandlerRegistry, OutboxRelay
from creatoriqx_api.modules.jobs.application.ports import EventDispatcher, OutboxEventRecord


def _event(event_type: str = "workspace.created") -> OutboxEventRecord:
    return OutboxEventRecord(
        id=uuid.uuid4(),
        event_type=event_type,
        payload={"k": "v"},
        created_at=datetime.now(UTC),
    )


class TestHandlerRegistry:
    async def test_dispatches_to_every_registered_handler_for_the_event_type(self) -> None:
        registry = HandlerRegistry()
        calls: list[str] = []

        async def first(_event: OutboxEventRecord) -> None:
            calls.append("first")

        async def second(_event: OutboxEventRecord) -> None:
            calls.append("second")

        registry.on("workspace.created", first)
        registry.on("workspace.created", second)

        await registry.dispatch(_event("workspace.created"))

        assert calls == ["first", "second"]

    async def test_an_unregistered_event_type_is_skipped_without_raising(self) -> None:
        registry = HandlerRegistry()
        # No handlers registered at all - must not raise.
        await registry.dispatch(_event("something.unknown"))

    async def test_only_the_matching_event_types_handler_runs(self) -> None:
        registry = HandlerRegistry()
        calls: list[str] = []

        async def workspace_handler(_event: OutboxEventRecord) -> None:
            calls.append("workspace")

        async def other_handler(_event: OutboxEventRecord) -> None:
            calls.append("other")

        registry.on("workspace.created", workspace_handler)
        registry.on("video.published", other_handler)

        await registry.dispatch(_event("workspace.created"))

        assert calls == ["workspace"]

    async def test_a_raising_handler_propagates(self) -> None:
        registry = HandlerRegistry()

        async def boom(_event: OutboxEventRecord) -> None:
            raise RuntimeError("handler failed")

        registry.on("workspace.created", boom)

        with pytest.raises(RuntimeError, match="handler failed"):
            await registry.dispatch(_event("workspace.created"))


class _FakeGateway:
    """Records the limit it was called with and returns a fixed count."""

    def __init__(self, relayed: int) -> None:
        self.relayed = relayed
        self.calls: list[int] = []

    async def relay_batch(self, dispatcher: EventDispatcher, *, limit: int) -> int:
        self.calls.append(limit)
        return self.relayed


class TestOutboxRelay:
    async def test_run_once_delegates_to_the_gateway_with_the_given_limit(self) -> None:
        gateway = _FakeGateway(relayed=3)
        relay = OutboxRelay(gateway, HandlerRegistry())

        count = await relay.run_once(limit=25)

        assert count == 3
        assert gateway.calls == [25]

    async def test_run_once_defaults_to_a_limit_of_fifty(self) -> None:
        gateway = _FakeGateway(relayed=0)
        relay = OutboxRelay(gateway, HandlerRegistry())

        await relay.run_once()

        assert gateway.calls == [50]

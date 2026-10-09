"""Unit tests for the usage-event allow-list and recorder (P0-062).

No database: ``TelemetrySink`` is faked here, so this exercises the domain
allow-list and ``UsageEventRecorder`` in isolation. The real
``SqlTelemetrySink`` behavior (forced RLS, persistence) is proven against a
real Postgres in ``tests/integration/test_usage_events_db.py``.
"""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.telemetry.application.usage_event_recorder import UsageEventRecorder
from creatoriqx_api.modules.telemetry.domain.usage_event import (
    UsageEventRecord,
    sanitize_properties,
)


class TestSanitizeProperties:
    def test_a_known_property_survives(self) -> None:
        result = sanitize_properties("auth.login_succeeded", {"method": "google_oidc"})
        assert result == {"method": "google_oidc"}

    def test_an_unlisted_property_is_dropped(self) -> None:
        result = sanitize_properties(
            "auth.login_succeeded", {"method": "google_oidc", "secret_token": "abc123"}
        )
        assert result == {"method": "google_oidc"}
        assert result is not None
        assert "secret_token" not in result

    def test_an_event_name_with_no_allow_list_entry_keeps_nothing(self) -> None:
        result = sanitize_properties("some.unlisted_event", {"anything": "goes"})
        assert result is None

    def test_none_properties_stay_none(self) -> None:
        assert sanitize_properties("auth.login_succeeded", None) is None

    def test_a_fully_dropped_result_is_none_not_an_empty_dict(self) -> None:
        result = sanitize_properties("auth.login_succeeded", {"secret_token": "abc123"})
        assert result is None


class TestUsageEventRecordSanitized:
    def test_sanitized_returns_an_equivalent_record_with_properties_filtered(self) -> None:
        workspace_id = uuid.uuid4()
        record = UsageEventRecord(
            name="auth.login_succeeded",
            workspace_id=workspace_id,
            properties={"method": "google_oidc", "secret_token": "abc123"},
        )

        sanitized = record.sanitized()

        assert sanitized.name == record.name
        assert sanitized.workspace_id == workspace_id
        assert sanitized.properties == {"method": "google_oidc"}


class _FakeSink:
    def __init__(self) -> None:
        self.emitted: list[UsageEventRecord] = []

    async def emit(self, event: UsageEventRecord) -> None:
        self.emitted.append(event)


class TestUsageEventRecorder:
    async def test_record_sanitizes_before_emitting(self) -> None:
        sink = _FakeSink()
        recorder = UsageEventRecorder(sink)
        workspace_id = uuid.uuid4()
        user_id = uuid.uuid4()

        await recorder.record(
            "auth.login_succeeded",
            workspace_id=workspace_id,
            user_id=user_id,
            properties={"method": "google_oidc", "secret_token": "abc123"},
        )

        assert len(sink.emitted) == 1
        emitted = sink.emitted[0]
        assert emitted.name == "auth.login_succeeded"
        assert emitted.workspace_id == workspace_id
        assert emitted.user_id == user_id
        assert emitted.properties == {"method": "google_oidc"}

    async def test_record_defaults_to_schema_version_one(self) -> None:
        sink = _FakeSink()
        recorder = UsageEventRecorder(sink)

        await recorder.record("auth.login_succeeded", workspace_id=uuid.uuid4())

        assert sink.emitted[0].schema_version == 1

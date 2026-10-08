"""Tests for UUIDv7 primary-key generation."""

from __future__ import annotations

import time

from creatoriqx_api.platform.ids import _uuid7_fallback, new_id


def test_new_id_is_uuid_version_7() -> None:
    assert new_id().version == 7


def test_ids_are_unique() -> None:
    assert len({new_id() for _ in range(1000)}) == 1000


def test_ids_are_time_ordered() -> None:
    first = new_id()
    time.sleep(0.005)
    second = new_id()
    assert second > first  # UUIDv7 sorts by creation time


def test_fallback_is_also_valid_version_7() -> None:
    value = _uuid7_fallback()
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"

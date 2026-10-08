"""Primary-key id generation.

UUIDv7 ids are time-ordered, so rows insert in roughly chronological order
(good for index locality) without exposing a sequential counter. ``uuid.uuid7``
is used where available (Python 3.14+) with a spec-compliant fallback for the
project's 3.12/3.13 floor.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable

# mypy targets 3.12, whose typeshed lacks uuid7; resolve it dynamically.
_STDLIB_UUID7: Callable[[], uuid.UUID] | None = getattr(uuid, "uuid7", None)


def _uuid7_fallback() -> uuid.UUID:
    """RFC 9562 UUIDv7: 48-bit millisecond timestamp, then random bits."""
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits
    value = (unix_ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76  # version 7
    value |= ((rand >> 4) & 0x0FFF) << 64  # rand_a (12 bits)
    value |= 0b10 << 62  # RFC 4122 variant
    value |= rand & 0x3FFFFFFFFFFFFFFF  # rand_b (62 bits)
    return uuid.UUID(int=value)


def new_id() -> uuid.UUID:
    """Return a fresh time-ordered UUIDv7 primary key."""
    return _STDLIB_UUID7() if _STDLIB_UUID7 is not None else _uuid7_fallback()

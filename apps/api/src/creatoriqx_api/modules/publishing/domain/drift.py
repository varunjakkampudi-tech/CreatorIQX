"""Drift detection (spec §3: "compare normalized managed fields (whitespace, tag
casing, entities) to avoid false positives").

YouTube's API round-trips HTML entities in descriptions, and tag casing is
not meaningfully significant to a creator, so a byte-for-byte comparison
between the approved snapshot and the last-read remote state would flag
drift on cosmetic differences that are not drift at all. This module
normalizes both sides the same way before anything is compared; the
resolution decision (adopt/overwrite/ignore) lives in
``YoutubeSyncService``, not here.
"""

from __future__ import annotations

import enum
import html
import re
from dataclasses import dataclass

_WHITESPACE_RE = re.compile(r"\s+")


class DriftResolutionMode(enum.StrEnum):
    """The three explicit resolutions spec §3 requires - never implicit."""

    ADOPT_REMOTE = "adopt_remote"
    OVERWRITE_REMOTE = "overwrite_remote"
    IGNORE = "ignore"


@dataclass(frozen=True, slots=True)
class NormalizedMetadata:
    """The managed fields, normalized for comparison only - never persisted or
    sent to YouTube; the originals are what get written or stored.
    """

    title: str
    description: str
    tags: frozenset[str]
    category: str | None


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", html.unescape(value)).strip()


def normalize_metadata_for_drift(
    *, title: str, description: str, tags: tuple[str, ...], category: str | None
) -> NormalizedMetadata:
    """Collapse whitespace, decode HTML entities, and case-fold tags so cosmetic
    differences never register as drift.
    """
    return NormalizedMetadata(
        title=_normalize_text(title),
        description=_normalize_text(description),
        tags=frozenset(_normalize_text(tag).casefold() for tag in tags),
        category=category,
    )


def has_drift(local: NormalizedMetadata, remote: NormalizedMetadata) -> bool:
    """Whether the two normalized payloads differ in any way that matters."""
    return local != remote

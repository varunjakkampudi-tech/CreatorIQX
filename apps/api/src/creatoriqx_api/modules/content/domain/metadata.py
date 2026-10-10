"""Metadata/SEO versions (spec feature 9): title, description, tags, category.

Each version is one option; a creator comparing titles asks for several
versions (the SEO acceptance criterion - "multiple options, each with
rationale" - is satisfied by ``rationale`` on every version, not by a
separate "options" concept). Character limits are current, verifiable
YouTube UI limits as of this build; both are pure data here, so the API
layer can also surface them without creating a version first.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

TITLE_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 5000


@dataclass(frozen=True, slots=True)
class MetadataVersion:
    """One version of a video's title/description/tags/category/disclosures."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    title: str
    description: str
    tags: tuple[str, ...]
    category: str | None
    disclosure_altered: bool
    disclosure_synthetic: bool
    rationale: str
    parent_version_id: uuid.UUID | None
    is_current: bool
    created_at: datetime


def character_limit_warnings(*, title: str, description: str) -> list[str]:
    """Truncation-preview warnings (spec feature 9: "character limits and
    truncation preview"). Never blocks creation - these are advisory.
    """
    warnings: list[str] = []
    if len(title) > TITLE_MAX_LENGTH:
        warnings.append(
            f"Title is {len(title)} characters; YouTube truncates past {TITLE_MAX_LENGTH}."
        )
    if len(description) > DESCRIPTION_MAX_LENGTH:
        warnings.append(
            f"Description is {len(description)} characters; "
            f"YouTube truncates past {DESCRIPTION_MAX_LENGTH}."
        )
    return warnings

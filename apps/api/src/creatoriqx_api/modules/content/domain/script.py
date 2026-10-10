"""Script versions (spec feature 5): hook, outline, full script, variants."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime


class ScriptAuthor(enum.StrEnum):
    """Who wrote this version (spec §7 ``script_versions``: "author (human or AI)")."""

    HUMAN = "human"
    AI = "ai"


@dataclass(frozen=True, slots=True)
class ScriptVersion:
    """One version of a video's script. Immutable once created; see the module README."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    variant_label: str
    author: ScriptAuthor
    hook: str
    outline: str
    body: str
    parent_version_id: uuid.UUID | None
    is_current: bool
    created_at: datetime

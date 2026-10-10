"""Ports for the content use cases (scripts, metadata/SEO, chapters).

Every store follows the same versioning contract: ``create`` always inserts
a new row and marks it ``is_current=True``, atomically clearing that flag on
whichever row previously held it for the same video - the store's job, not
the application layer's, so "exactly one current version per video" can
never be left half-applied. "Restore" has no separate store method: the
service re-reads an old version's fields and calls ``create`` again, which
is itself a new, current version with the restored content (spec feature 5:
"restore any version" - non-destructive, history is never deleted).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from creatoriqx_api.modules.content.domain.chapters import Chapter, ChapterVersion
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion
from creatoriqx_api.modules.content.domain.script import ScriptAuthor, ScriptVersion


@dataclass(frozen=True, slots=True)
class NewScriptVersion:
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    variant_label: str
    author: ScriptAuthor
    hook: str
    outline: str
    body: str
    parent_version_id: uuid.UUID | None = None


class ScriptVersionStore(Protocol):
    async def create(self, version: NewScriptVersion) -> ScriptVersion: ...

    async def get(
        self, *, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> ScriptVersion | None: ...

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[ScriptVersion]: ...


@dataclass(frozen=True, slots=True)
class NewMetadataVersion:
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    title: str
    description: str
    tags: tuple[str, ...]
    category: str | None
    disclosure_altered: bool
    disclosure_synthetic: bool
    rationale: str
    parent_version_id: uuid.UUID | None = None


class MetadataVersionStore(Protocol):
    async def create(self, version: NewMetadataVersion) -> MetadataVersion: ...

    async def get(
        self, *, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> MetadataVersion | None: ...

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[MetadataVersion]: ...


@dataclass(frozen=True, slots=True)
class NewChapterVersion:
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    transcript_id: uuid.UUID
    chapters: tuple[Chapter, ...]
    parent_version_id: uuid.UUID | None = None


class ChapterVersionStore(Protocol):
    async def create(self, version: NewChapterVersion) -> ChapterVersion: ...

    async def get(
        self, *, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> ChapterVersion | None: ...

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[ChapterVersion]: ...

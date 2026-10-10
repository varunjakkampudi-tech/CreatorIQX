"""The chapters use case (spec feature 10): manual create, auto-generate, restore.

Depends on ``transcripts.application.ports.TranscriptStore`` - another
module's public port, not its infrastructure - to read the transcript a
chapter version was generated from (spec §3: "other modules may consume it
only through the owner's public interface"). This is the one place the
``content`` module reaches outside itself.
"""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.content.application.chapter_generator import generate_draft_chapters
from creatoriqx_api.modules.content.application.ports import ChapterVersionStore, NewChapterVersion
from creatoriqx_api.modules.content.domain.chapters import (
    Chapter,
    ChapterVersion,
    validate_chapters,
)
from creatoriqx_api.modules.content.domain.errors import (
    ChapterValidationError,
    ChapterVersionNotFoundError,
    TranscriptNotFoundForChaptersError,
    TranscriptRequiredForChaptersError,
)
from creatoriqx_api.modules.transcripts.application.ports import TranscriptStore


class ChapterService:
    def __init__(self, store: ChapterVersionStore, transcripts: TranscriptStore) -> None:
        self._store = store
        self._transcripts = transcripts

    async def create_version(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        transcript_id: uuid.UUID,
        chapters: tuple[Chapter, ...],
    ) -> ChapterVersion:
        reasons = validate_chapters(chapters)
        if reasons:
            raise ChapterValidationError(reasons)
        return await self._store.create(
            NewChapterVersion(
                workspace_id=workspace_id,
                video_id=video_id,
                transcript_id=transcript_id,
                chapters=chapters,
            )
        )

    async def generate_from_transcript(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID, transcript_id: uuid.UUID
    ) -> ChapterVersion:
        transcript = await self._transcripts.get(
            workspace_id=workspace_id, transcript_id=transcript_id
        )
        if transcript is None:
            raise TranscriptNotFoundForChaptersError()
        if not transcript.is_fully_timed:
            raise TranscriptRequiredForChaptersError()
        try:
            draft = generate_draft_chapters(transcript)
        except ValueError as exc:
            raise TranscriptRequiredForChaptersError() from exc
        return await self.create_version(
            workspace_id=workspace_id,
            video_id=video_id,
            transcript_id=transcript_id,
            chapters=draft,
        )

    async def list_versions(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[ChapterVersion]:
        return await self._store.list_for_video(workspace_id=workspace_id, video_id=video_id)

    async def restore_version(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID, version_id: uuid.UUID
    ) -> ChapterVersion:
        target = await self._store.get(workspace_id=workspace_id, version_id=version_id)
        if target is None or target.video_id != video_id:
            raise ChapterVersionNotFoundError()
        return await self._store.create(
            NewChapterVersion(
                workspace_id=workspace_id,
                video_id=video_id,
                transcript_id=target.transcript_id,
                chapters=target.chapters,
                parent_version_id=target.id,
            )
        )

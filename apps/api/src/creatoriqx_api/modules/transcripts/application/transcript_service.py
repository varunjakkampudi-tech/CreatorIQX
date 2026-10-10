"""The transcript use case: four sources, one abstraction (spec feature 22).

Each ``import_*``/``transcribe_*`` method differs only in how it derives
``TranscriptSegment``s before handing them to the same
``TranscriptStore.create`` call - the one place a transcript is actually
persisted. ``youtube_captions`` and ``local_whisper`` are real methods on
this service (not missing), but both currently raise
:class:`TranscriptSourceUnavailableError` rather than silently succeeding,
since neither has a working adapter in this build (see the module's
``errors.py`` docstring for why).
"""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.transcripts.application.ports import NewTranscript, TranscriptStore
from creatoriqx_api.modules.transcripts.domain.errors import (
    EmptyTranscriptError,
    TranscriptSourceUnavailableError,
)
from creatoriqx_api.modules.transcripts.domain.parsing import (
    parse_plain_text,
    parse_subtitle_blocks,
)
from creatoriqx_api.modules.transcripts.domain.transcript import (
    Transcript,
    TranscriptSegment,
    TranscriptSource,
)


class TranscriptService:
    """Create and read transcripts, regardless of their source."""

    def __init__(self, store: TranscriptStore) -> None:
        self._store = store

    async def import_pasted_text(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID | None,
        text: str,
        language: str = "en",
    ) -> Transcript:
        segments = parse_plain_text(text)
        if not segments[0].text:
            raise EmptyTranscriptError()
        return await self._store.create(
            NewTranscript(
                workspace_id=workspace_id,
                video_id=video_id,
                source=TranscriptSource.PASTED,
                language=language,
                segments=segments,
            )
        )

    async def import_uploaded_file(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID | None,
        filename: str,
        content: str,
        language: str = "en",
    ) -> Transcript:
        segments: tuple[TranscriptSegment, ...] = ()
        if filename.lower().endswith((".srt", ".vtt")):
            segments = parse_subtitle_blocks(content)
        if not segments:
            segments = parse_plain_text(content)
        if not any(s.text for s in segments):
            raise EmptyTranscriptError()
        return await self._store.create(
            NewTranscript(
                workspace_id=workspace_id,
                video_id=video_id,
                source=TranscriptSource.UPLOADED_FILE,
                language=language,
                segments=segments,
            )
        )

    async def import_youtube_captions(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID, language: str = "en"
    ) -> Transcript:
        """Not wired up in this build - see ``TranscriptSourceUnavailableError``."""
        raise TranscriptSourceUnavailableError(TranscriptSource.YOUTUBE_CAPTIONS.value)

    async def transcribe_locally(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID, language: str = "en"
    ) -> Transcript:
        """Not wired up in this build - see ``TranscriptSourceUnavailableError``."""
        raise TranscriptSourceUnavailableError(TranscriptSource.LOCAL_WHISPER.value)

    async def get(self, *, workspace_id: uuid.UUID, transcript_id: uuid.UUID) -> Transcript | None:
        return await self._store.get(workspace_id=workspace_id, transcript_id=transcript_id)

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[Transcript]:
        return await self._store.list_for_video(workspace_id=workspace_id, video_id=video_id)

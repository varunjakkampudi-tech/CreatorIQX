"""Transcript parsing and the shared-abstraction service (spec feature 22)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from creatoriqx_api.modules.transcripts.application.ports import NewTranscript, TranscriptStore
from creatoriqx_api.modules.transcripts.application.transcript_service import TranscriptService
from creatoriqx_api.modules.transcripts.domain.errors import (
    EmptyTranscriptError,
    TranscriptSourceUnavailableError,
)
from creatoriqx_api.modules.transcripts.domain.parsing import (
    parse_plain_text,
    parse_subtitle_blocks,
)
from creatoriqx_api.modules.transcripts.domain.transcript import Transcript, TranscriptSource

WORKSPACE_ID = uuid.uuid4()
VIDEO_ID = uuid.uuid4()


def test_parse_plain_text_is_one_untimed_segment() -> None:
    segments = parse_plain_text("Hello there.\nThis is a script.")
    assert len(segments) == 1
    assert segments[0].start_seconds == 0.0
    assert segments[0].end_seconds is None
    assert "Hello there." in segments[0].text


def test_parse_srt_blocks_produces_timed_segments() -> None:
    srt = (
        "1\n00:00:00,000 --> 00:00:02,500\nWelcome back.\n\n"
        "2\n00:00:02,500 --> 00:00:05,000\nLet's get started.\n\n"
    )
    segments = parse_subtitle_blocks(srt)
    assert len(segments) == 2
    assert segments[0].start_seconds == 0.0
    assert segments[0].end_seconds == 2.5
    assert segments[1].text == "Let's get started."


def test_parse_subtitle_blocks_returns_nothing_for_plain_text() -> None:
    assert parse_subtitle_blocks("just a paragraph, no timestamps here") == ()


@dataclass
class FakeTranscriptStore:
    transcripts: dict[uuid.UUID, Transcript] = field(default_factory=dict)

    async def create(self, transcript: NewTranscript) -> Transcript:
        record = Transcript(
            id=uuid.uuid4(),
            workspace_id=transcript.workspace_id,
            video_id=transcript.video_id,
            source=transcript.source,
            language=transcript.language,
            version=1,
            parent_transcript_id=transcript.parent_transcript_id,
            segments=transcript.segments,
            created_at=datetime.now(UTC),
        )
        self.transcripts[record.id] = record
        return record

    async def get(self, *, workspace_id: uuid.UUID, transcript_id: uuid.UUID) -> Transcript | None:
        t = self.transcripts.get(transcript_id)
        return t if t is not None and t.workspace_id == workspace_id else None

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[Transcript]:
        return [
            t
            for t in self.transcripts.values()
            if t.workspace_id == workspace_id and t.video_id == video_id
        ]


def _service() -> TranscriptService:
    store: TranscriptStore = FakeTranscriptStore()
    return TranscriptService(store)


async def test_import_pasted_text_creates_a_transcript() -> None:
    service = _service()
    transcript = await service.import_pasted_text(
        workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, text="A pasted script."
    )
    assert transcript.source is TranscriptSource.PASTED
    assert transcript.segments[0].text == "A pasted script."
    assert transcript.is_fully_timed is False


async def test_import_pasted_empty_text_is_rejected() -> None:
    service = _service()
    with pytest.raises(EmptyTranscriptError):
        await service.import_pasted_text(workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, text="   ")


async def test_import_uploaded_srt_file_is_fully_timed() -> None:
    service = _service()
    srt = (
        "1\n00:00:00,000 --> 00:00:10,000\nIntro line.\n\n"
        "2\n00:00:10,000 --> 00:00:20,000\nSecond line.\n\n"
    )
    transcript = await service.import_uploaded_file(
        workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, filename="clip.srt", content=srt
    )
    assert transcript.source is TranscriptSource.UPLOADED_FILE
    assert transcript.is_fully_timed is True
    assert transcript.duration_seconds == 20.0


async def test_import_uploaded_plain_txt_file_falls_back_to_one_segment() -> None:
    service = _service()
    transcript = await service.import_uploaded_file(
        workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, filename="notes.txt", content="plain notes"
    )
    assert len(transcript.segments) == 1
    assert transcript.is_fully_timed is False


async def test_youtube_captions_source_is_a_named_unavailable_gap() -> None:
    service = _service()
    with pytest.raises(TranscriptSourceUnavailableError):
        await service.import_youtube_captions(workspace_id=WORKSPACE_ID, video_id=VIDEO_ID)


async def test_local_whisper_source_is_a_named_unavailable_gap() -> None:
    service = _service()
    with pytest.raises(TranscriptSourceUnavailableError):
        await service.transcribe_locally(workspace_id=WORKSPACE_ID, video_id=VIDEO_ID)


async def test_list_for_video_scopes_to_workspace_and_video() -> None:
    service = _service()
    await service.import_pasted_text(workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, text="one")
    other_workspace = uuid.uuid4()
    await service.import_pasted_text(workspace_id=other_workspace, video_id=VIDEO_ID, text="two")

    listed = await service.list_for_video(workspace_id=WORKSPACE_ID, video_id=VIDEO_ID)
    assert len(listed) == 1
    assert listed[0].segments[0].text == "one"

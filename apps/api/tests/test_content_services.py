"""ScriptService/MetadataService/ChapterService: create, compare, restore
(spec features 5, 9, 10). Fakes implement the real version-pointer contract
("exactly one is_current per video") so these tests exercise the same
semantics the SQL stores are reviewed against.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import pytest

from creatoriqx_api.modules.content.application.chapter_service import ChapterService
from creatoriqx_api.modules.content.application.metadata_service import MetadataService
from creatoriqx_api.modules.content.application.ports import (
    NewChapterVersion,
    NewMetadataVersion,
    NewScriptVersion,
)
from creatoriqx_api.modules.content.application.script_service import ScriptService
from creatoriqx_api.modules.content.domain.chapters import Chapter, ChapterVersion
from creatoriqx_api.modules.content.domain.errors import (
    ChapterValidationError,
    MetadataVersionNotFoundError,
    ScriptVersionNotFoundError,
    TranscriptNotFoundForChaptersError,
    TranscriptRequiredForChaptersError,
)
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion
from creatoriqx_api.modules.content.domain.script import ScriptAuthor, ScriptVersion
from creatoriqx_api.modules.transcripts.application.ports import NewTranscript
from creatoriqx_api.modules.transcripts.domain.transcript import (
    Transcript,
    TranscriptSegment,
    TranscriptSource,
)

WORKSPACE_ID = uuid.uuid4()
VIDEO_ID = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(UTC)


class _VersionLike(Protocol):
    """Structural shape every version dataclass below shares."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    is_current: bool


def _with_current[V: _VersionLike](record: V, is_current: bool) -> V:
    return dataclasses.replace(record, is_current=is_current)  # type: ignore[type-var]


@dataclass
class FakeVersionStore[V: _VersionLike]:
    """Generic "exactly one current per video" fake, shared by all three tests below."""

    rows: dict[uuid.UUID, V] = field(default_factory=dict)

    async def _create(self, *, video_id: uuid.UUID, record: V) -> V:
        for existing_id, existing in list(self.rows.items()):
            if existing.video_id == video_id:
                self.rows[existing_id] = _with_current(existing, False)
        self.rows[record.id] = record
        return record

    async def get(self, *, workspace_id: uuid.UUID, version_id: uuid.UUID) -> V | None:
        row = self.rows.get(version_id)
        if row is None or row.workspace_id != workspace_id:
            return None
        return row

    async def list_for_video(self, *, workspace_id: uuid.UUID, video_id: uuid.UUID) -> list[V]:
        return [
            r
            for r in self.rows.values()
            if r.workspace_id == workspace_id and r.video_id == video_id
        ]


@dataclass
class FakeScriptStore(FakeVersionStore[ScriptVersion]):
    async def create(self, version: NewScriptVersion) -> ScriptVersion:
        record = ScriptVersion(
            id=uuid.uuid4(),
            workspace_id=version.workspace_id,
            video_id=version.video_id,
            variant_label=version.variant_label,
            author=version.author,
            hook=version.hook,
            outline=version.outline,
            body=version.body,
            parent_version_id=version.parent_version_id,
            is_current=True,
            created_at=_now(),
        )
        return await self._create(video_id=version.video_id, record=record)


@dataclass
class FakeMetadataStore(FakeVersionStore[MetadataVersion]):
    async def create(self, version: NewMetadataVersion) -> MetadataVersion:
        record = MetadataVersion(
            id=uuid.uuid4(),
            workspace_id=version.workspace_id,
            video_id=version.video_id,
            title=version.title,
            description=version.description,
            tags=version.tags,
            category=version.category,
            disclosure_altered=version.disclosure_altered,
            disclosure_synthetic=version.disclosure_synthetic,
            rationale=version.rationale,
            parent_version_id=version.parent_version_id,
            is_current=True,
            created_at=_now(),
        )
        return await self._create(video_id=version.video_id, record=record)


@dataclass
class FakeChapterStore(FakeVersionStore[ChapterVersion]):
    async def create(self, version: NewChapterVersion) -> ChapterVersion:
        record = ChapterVersion(
            id=uuid.uuid4(),
            workspace_id=version.workspace_id,
            video_id=version.video_id,
            transcript_id=version.transcript_id,
            chapters=version.chapters,
            parent_version_id=version.parent_version_id,
            is_current=True,
            created_at=_now(),
        )
        return await self._create(video_id=version.video_id, record=record)


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
            created_at=_now(),
        )
        self.transcripts[record.id] = record
        return record

    async def get(self, *, workspace_id: uuid.UUID, transcript_id: uuid.UUID) -> Transcript | None:
        t = self.transcripts.get(transcript_id)
        return t if t is not None and t.workspace_id == workspace_id else None

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[Transcript]:
        return [t for t in self.transcripts.values() if t.video_id == video_id]


# --- ScriptService -------------------------------------------------------


async def test_create_script_version_becomes_current() -> None:
    service = ScriptService(FakeScriptStore())
    version = await service.create_version(
        workspace_id=WORKSPACE_ID,
        video_id=VIDEO_ID,
        variant_label="v1",
        author=ScriptAuthor.HUMAN,
        hook="Hook",
        outline="Outline",
        body="Body",
    )
    assert version.is_current is True


async def test_second_script_version_demotes_the_first() -> None:
    service = ScriptService(FakeScriptStore())
    first = await service.create_version(
        workspace_id=WORKSPACE_ID,
        video_id=VIDEO_ID,
        variant_label="v1",
        author=ScriptAuthor.HUMAN,
        hook="",
        outline="",
        body="first",
    )
    await service.create_version(
        workspace_id=WORKSPACE_ID,
        video_id=VIDEO_ID,
        variant_label="v2",
        author=ScriptAuthor.AI,
        hook="",
        outline="",
        body="second",
    )
    versions = await service.list_versions(workspace_id=WORKSPACE_ID, video_id=VIDEO_ID)
    by_id = {v.id: v for v in versions}
    assert by_id[first.id].is_current is False
    assert sum(1 for v in versions if v.is_current) == 1


async def test_restoring_an_old_script_version_makes_it_current_again() -> None:
    service = ScriptService(FakeScriptStore())
    original = await service.create_version(
        workspace_id=WORKSPACE_ID,
        video_id=VIDEO_ID,
        variant_label="v1",
        author=ScriptAuthor.HUMAN,
        hook="h",
        outline="o",
        body="original body",
    )
    await service.create_version(
        workspace_id=WORKSPACE_ID,
        video_id=VIDEO_ID,
        variant_label="v2",
        author=ScriptAuthor.HUMAN,
        hook="",
        outline="",
        body="replacement",
    )
    restored = await service.restore_version(
        workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, version_id=original.id
    )
    assert restored.body == "original body"
    assert restored.is_current is True
    assert restored.parent_version_id == original.id

    versions = await service.list_versions(workspace_id=WORKSPACE_ID, video_id=VIDEO_ID)
    assert len(versions) == 3  # original, replacement, restored-copy - history is never deleted


async def test_restoring_a_missing_script_version_raises() -> None:
    service = ScriptService(FakeScriptStore())
    with pytest.raises(ScriptVersionNotFoundError):
        await service.restore_version(
            workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, version_id=uuid.uuid4()
        )


# --- MetadataService ------------------------------------------------------


async def test_create_metadata_version_warns_on_long_title() -> None:
    service = MetadataService(FakeMetadataStore())
    _version, warnings = await service.create_version(
        workspace_id=WORKSPACE_ID,
        video_id=VIDEO_ID,
        title="x" * 150,
        description="",
        tags=(),
        category=None,
        disclosure_altered=False,
        disclosure_synthetic=False,
        rationale="testing the limit",
    )
    assert any("Title" in w for w in warnings)


async def test_metadata_version_within_limits_has_no_warnings() -> None:
    service = MetadataService(FakeMetadataStore())
    _version, warnings = await service.create_version(
        workspace_id=WORKSPACE_ID,
        video_id=VIDEO_ID,
        title="A short, clear title",
        description="A short description.",
        tags=("tag1",),
        category="Education",
        disclosure_altered=False,
        disclosure_synthetic=False,
        rationale="clear and on-brand",
    )
    assert warnings == []


async def test_restoring_a_missing_metadata_version_raises() -> None:
    service = MetadataService(FakeMetadataStore())
    with pytest.raises(MetadataVersionNotFoundError):
        await service.restore_version(
            workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, version_id=uuid.uuid4()
        )


# --- ChapterService ---------------------------------------------------


def _chapter_service() -> tuple[ChapterService, FakeTranscriptStore]:
    transcripts = FakeTranscriptStore()
    return ChapterService(FakeChapterStore(), transcripts), transcripts


async def test_create_chapter_version_rejects_invalid_chapters() -> None:
    service, _ = _chapter_service()
    with pytest.raises(ChapterValidationError):
        await service.create_version(
            workspace_id=WORKSPACE_ID,
            video_id=VIDEO_ID,
            transcript_id=uuid.uuid4(),
            chapters=(Chapter(start_seconds=0, title="Only one"),),
        )


async def test_create_chapter_version_accepts_valid_chapters() -> None:
    service, _ = _chapter_service()
    chapters = (
        Chapter(start_seconds=0, title="Intro"),
        Chapter(start_seconds=30, title="Main"),
        Chapter(start_seconds=90, title="Outro"),
    )
    version = await service.create_version(
        workspace_id=WORKSPACE_ID,
        video_id=VIDEO_ID,
        transcript_id=uuid.uuid4(),
        chapters=chapters,
    )
    assert version.chapters == chapters


async def test_generate_from_transcript_without_timing_is_rejected() -> None:
    service, transcripts = _chapter_service()
    transcript = await transcripts.create(
        NewTranscript(
            workspace_id=WORKSPACE_ID,
            video_id=VIDEO_ID,
            source=TranscriptSource.PASTED,
            language="en",
            segments=(TranscriptSegment(start_seconds=0, end_seconds=None, text="no timing"),),
        )
    )
    with pytest.raises(TranscriptRequiredForChaptersError):
        await service.generate_from_transcript(
            workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, transcript_id=transcript.id
        )


async def test_generate_from_a_missing_transcript_raises() -> None:
    service, _ = _chapter_service()
    with pytest.raises(TranscriptNotFoundForChaptersError):
        await service.generate_from_transcript(
            workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, transcript_id=uuid.uuid4()
        )


async def test_generate_from_a_fully_timed_transcript_produces_valid_chapters() -> None:
    service, transcripts = _chapter_service()
    segments = tuple(
        TranscriptSegment(
            start_seconds=float(i * 60), end_seconds=float((i + 1) * 60), text=f"part {i}"
        )
        for i in range(6)
    )
    transcript = await transcripts.create(
        NewTranscript(
            workspace_id=WORKSPACE_ID,
            video_id=VIDEO_ID,
            source=TranscriptSource.UPLOADED_FILE,
            language="en",
            segments=segments,
        )
    )
    version = await service.generate_from_transcript(
        workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, transcript_id=transcript.id
    )
    assert version.transcript_id == transcript.id
    assert version.chapters[0].start_seconds == 0
    assert len(version.chapters) >= 3


async def test_restoring_a_chapter_version_keeps_its_transcript_reference() -> None:
    service, _ = _chapter_service()
    chapters = (
        Chapter(start_seconds=0, title="Intro"),
        Chapter(start_seconds=30, title="Main"),
        Chapter(start_seconds=90, title="Outro"),
    )
    transcript_id = uuid.uuid4()
    original = await service.create_version(
        workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, transcript_id=transcript_id, chapters=chapters
    )
    restored = await service.restore_version(
        workspace_id=WORKSPACE_ID, video_id=VIDEO_ID, version_id=original.id
    )
    assert restored.transcript_id == transcript_id
    assert restored.is_current is True

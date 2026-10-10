"""HTTP behaviour of the Phase 1C routes: transcripts, scripts, metadata,
chapters (spec §4 features 22, 5, 9, 10).

Same approach as ``test_planning_routes.py``: the real app factory, with
in-memory session/access doubles and fakes standing in for the five new SQL
stores - no real database needed.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app
from creatoriqx_api.modules.content.application.chapter_service import ChapterService
from creatoriqx_api.modules.content.application.metadata_service import MetadataService
from creatoriqx_api.modules.content.application.ports import (
    NewChapterVersion,
    NewMetadataVersion,
    NewScriptVersion,
)
from creatoriqx_api.modules.content.application.script_service import ScriptService
from creatoriqx_api.modules.content.domain.chapters import ChapterVersion
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion
from creatoriqx_api.modules.content.domain.script import ScriptVersion
from creatoriqx_api.modules.identity.api.dependencies import CSRF_HEADER
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore
from creatoriqx_api.modules.transcripts.application.ports import NewTranscript
from creatoriqx_api.modules.transcripts.application.transcript_service import TranscriptService
from creatoriqx_api.modules.transcripts.domain.transcript import Transcript
from creatoriqx_api.modules.workspaces.application.access_service import WorkspaceAccessService
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.modules.workspaces.infrastructure.memory_access_store import (
    InMemoryWorkspaceAccessStore,
)
from creatoriqx_api.settings import Settings


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class FakeTranscriptStore:
    """Duplicated from ``test_transcript_service.py`` - no precedent in this
    suite for importing fixtures across test modules (same convention
    ``test_planning_routes.py`` recorded for Phase 1B)."""

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
    """Generic "exactly one is_current per video" fake, duplicated per
    version type below (same convention as ``test_content_services.py``)."""

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


POLICY = SessionPolicy(idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12))
SESSION_COOKIE = "__Host-creatoriqx_session"
WORKSPACE_ID = uuid.UUID(int=501)
USER_ID = uuid.UUID(int=601)
VIEWER_ID = uuid.UUID(int=602)
VIDEO_ID = uuid.uuid4()


def _settings() -> Settings:
    return Settings(
        database_app_url=SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        redis_url=SecretStr("redis://localhost:1/0"),
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(_settings(), checks=[])
    store = InMemoryKeyValueStore()
    app.state.key_value_store = store
    app.state.session_service = SessionService(store, POLICY)
    access = InMemoryWorkspaceAccessStore()
    access.grant(
        WorkspaceAccess(workspace_id=WORKSPACE_ID, name="workspace", role=Role.EDITOR), USER_ID
    )
    access.grant(
        WorkspaceAccess(workspace_id=WORKSPACE_ID, name="workspace", role=Role.VIEWER), VIEWER_ID
    )
    app.state.workspace_access_service = WorkspaceAccessService(access)

    transcript_store = FakeTranscriptStore()
    app.state.transcript_service = TranscriptService(transcript_store)
    app.state.script_service = ScriptService(FakeScriptStore())
    app.state.metadata_service = MetadataService(FakeMetadataStore())
    app.state.chapter_service = ChapterService(FakeChapterStore(), transcript_store)
    with TestClient(app, base_url="https://testserver") as built:
        yield built


async def _sign_in(client: TestClient, *, user_id: uuid.UUID) -> str:
    app: FastAPI = client.app  # type: ignore[assignment]
    service: SessionService = app.state.session_service
    session = await service.create(
        subject=str(user_id),
        email="creator@example.com",
        user_id=user_id,
        workspace_id=WORKSPACE_ID,
    )
    client.cookies.set(SESSION_COOKIE, session.id)
    return session.csrf_token


# --- transcripts -----------------------------------------------------


async def test_paste_transcript_then_list_it(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)
    created = client.post(
        f"/api/v1/videos/{VIDEO_ID}/transcripts/paste",
        json={"text": "A pasted transcript."},
        headers={CSRF_HEADER: csrf},
    )
    assert created.status_code == 201
    assert created.json()["source"] == "pasted"

    listed = client.get(f"/api/v1/videos/{VIDEO_ID}/transcripts")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_viewer_cannot_paste_a_transcript(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=VIEWER_ID)
    response = client.post(
        f"/api/v1/videos/{VIDEO_ID}/transcripts/paste",
        json={"text": "nope"},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 403


async def test_upload_srt_transcript_is_fully_timed(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)
    srt = "1\n00:00:00,000 --> 00:00:10,000\nHello.\n\n2\n00:00:10,000 --> 00:00:20,000\nWorld.\n\n"
    response = client.post(
        f"/api/v1/videos/{VIDEO_ID}/transcripts/upload",
        json={"filename": "clip.srt", "content": srt},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 201
    assert response.json()["is_fully_timed"] is True


# --- scripts -----------------------------------------------------------


async def test_create_and_restore_a_script_version(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)
    first = client.post(
        f"/api/v1/videos/{VIDEO_ID}/scripts",
        json={"body": "first draft"},
        headers={CSRF_HEADER: csrf},
    ).json()
    client.post(
        f"/api/v1/videos/{VIDEO_ID}/scripts",
        json={"body": "second draft"},
        headers={CSRF_HEADER: csrf},
    )

    versions = client.get(f"/api/v1/videos/{VIDEO_ID}/scripts").json()
    assert len(versions) == 2

    restored = client.post(
        f"/api/v1/videos/{VIDEO_ID}/scripts/{first['id']}/restore", headers={CSRF_HEADER: csrf}
    )
    assert restored.status_code == 201
    assert restored.json()["body"] == "first draft"
    assert restored.json()["is_current"] is True


# --- metadata/SEO --------------------------------------------------------


async def test_metadata_version_reports_character_limit_warnings(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)
    response = client.post(
        f"/api/v1/videos/{VIDEO_ID}/metadata",
        json={"title": "x" * 150, "rationale": "testing limits"},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 201
    assert response.json()["character_limit_warnings"]


# --- chapters ------------------------------------------------------------


async def test_generate_chapters_from_a_timed_transcript(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)
    srt_blocks = "".join(
        f"{i + 1}\n00:0{i}:00,000 --> 00:0{i + 1}:00,000\nSegment {i}.\n\n" for i in range(6)
    )
    transcript = client.post(
        f"/api/v1/videos/{VIDEO_ID}/transcripts/upload",
        json={"filename": "clip.srt", "content": srt_blocks},
        headers={CSRF_HEADER: csrf},
    ).json()

    generated = client.post(
        f"/api/v1/videos/{VIDEO_ID}/chapters/generate",
        json={"transcript_id": transcript["id"]},
        headers={CSRF_HEADER: csrf},
    )
    assert generated.status_code == 201
    body = generated.json()
    assert body["chapters"][0]["start_seconds"] == 0
    assert len(body["chapters"]) >= 3


async def test_manual_chapter_version_rejects_invalid_chapters(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)
    response = client.post(
        f"/api/v1/videos/{VIDEO_ID}/chapters",
        json={
            "transcript_id": str(uuid.uuid4()),
            "chapters": [{"start_seconds": 5, "title": "Not at zero"}],
        },
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 422
    assert response.json()["type"] == "/problems/chapter-validation-failed"


async def test_generate_chapters_without_a_timed_transcript_is_rejected(
    client: TestClient,
) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)
    transcript = client.post(
        f"/api/v1/videos/{VIDEO_ID}/transcripts/paste",
        json={"text": "untimed text"},
        headers={CSRF_HEADER: csrf},
    ).json()

    response = client.post(
        f"/api/v1/videos/{VIDEO_ID}/chapters/generate",
        json={"transcript_id": transcript["id"]},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 422
    assert response.json()["type"] == "/problems/chapter-generation-needs-timed-transcript"

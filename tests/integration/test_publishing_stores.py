"""Regression coverage for the publishing module's SQL stores against real
Postgres (spec §6 multi-tenancy, Phase 1D P1D-04).

The connect-flow production bug (P1A-03, fix commit ``c7e4939``) was a
tenant-scoped store that never called ``set_tenant_context`` before querying
its ``FORCE ROW LEVEL SECURITY`` tables - invisible to unit tests against
fakes, and invisible to the generic RLS meta-test (``test_rls.py``), which
proves the *policies* exist but never calls application code. This test
exercises every new store's real create/read path the same way that bug was
finally caught, so the same class of defect cannot silently recur in
``publish_snapshots``/``youtube_video_links``/``sync_operations``/
``remote_snapshots``/``youtube_capabilities``.

Runs against creatoriqx_test. Needs ``py scripts/dev.py up``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from creatoriqx_api.modules.publishing.application.ports import (
    NewPublishSnapshot,
    NewRemoteSnapshot,
    NewSyncOperation,
    NewYoutubeVideoLink,
)
from creatoriqx_api.modules.publishing.domain.capability import (
    Capability,
    CapabilityEvidence,
    CapabilityStatus,
)
from creatoriqx_api.modules.publishing.domain.sync_operation import (
    SyncFieldGroup,
    SyncOperationStatus,
)
from creatoriqx_api.modules.publishing.domain.sync_state import SyncState
from creatoriqx_api.modules.publishing.infrastructure.sql_publish_snapshot_store import (
    SqlPublishSnapshotStore,
)
from creatoriqx_api.modules.publishing.infrastructure.sql_remote_snapshot_store import (
    SqlRemoteSnapshotStore,
)
from creatoriqx_api.modules.publishing.infrastructure.sql_sync_operation_store import (
    SqlSyncOperationStore,
)
from creatoriqx_api.modules.publishing.infrastructure.sql_video_link_store import (
    SqlYoutubeVideoLinkStore,
)
from creatoriqx_api.modules.youtube.infrastructure.sql_capability_store import SqlCapabilityStore
from creatoriqx_api.platform.database import set_tenant_context

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"


def _test_url(key: str) -> str:
    value = dotenv_values(REPO_ROOT / ".env").get(key)
    if not value:
        pytest.fail(f"{key} missing from .env. Run: py scripts/dev.py setup")
    base, _ = value.rsplit("/", 1)
    return f"{base}/creatoriqx_test"


async def _add_user(session: AsyncSession, user_id: uuid.UUID, email: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, email) VALUES (:i, :e)"), {"i": user_id, "e": email}
    )


async def _add_workspace(session: AsyncSession, workspace_id: uuid.UUID, name: str) -> None:
    await session.execute(
        text("INSERT INTO workspaces (id, name) VALUES (:i, :n)"), {"i": workspace_id, "n": name}
    )


async def _add_channel(
    session: AsyncSession, channel_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO channels (id, workspace_id, youtube_channel_id, title) "
            "VALUES (:i, :w, :y, :t)"
        ),
        {"i": channel_id, "w": workspace_id, "y": "UC_test", "t": "Test Channel"},
    )


@pytest.fixture(scope="module", autouse=True)
def _schema_at_head() -> None:
    os.environ["ALEMBIC_DATABASE_URL"] = _test_url("DATABASE_OWNER_URL")
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


def test_publishing_stores_round_trip_under_rls() -> None:
    engine = create_async_engine(_test_url("DATABASE_APP_URL"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    channel_id = uuid.uuid4()
    video_id = uuid.uuid4()

    async def body() -> None:
        try:
            async with factory() as session:
                await _add_user(session, user_id, "owner@example.com")
                await _add_workspace(session, workspace_id, "W")
                await set_tenant_context(session, workspace_id=workspace_id, user_id=user_id)
                await _add_channel(session, channel_id, workspace_id)
                await session.commit()

            snapshot_store = SqlPublishSnapshotStore(factory)
            snapshot = await snapshot_store.create(
                NewPublishSnapshot(
                    workspace_id=workspace_id,
                    video_id=video_id,
                    script_version_id=uuid.uuid4(),
                    metadata_version_id=uuid.uuid4(),
                    chapter_version_id=None,
                    thumbnail_variant_id=None,
                    disclosure_altered=False,
                    disclosure_synthetic=False,
                    scheduled_at=None,
                    approved_by=user_id,
                )
            )
            assert snapshot.video_id == video_id
            fetched = await snapshot_store.get(workspace_id=workspace_id, snapshot_id=snapshot.id)
            assert fetched is not None
            latest = await snapshot_store.get_latest_for_video(
                workspace_id=workspace_id, video_id=video_id
            )
            assert latest is not None
            assert latest.id == snapshot.id

            link_store = SqlYoutubeVideoLinkStore(factory)
            link = await link_store.create(
                NewYoutubeVideoLink(
                    workspace_id=workspace_id,
                    video_id=video_id,
                    channel_id=channel_id,
                    youtube_video_id="yt-real-1",
                )
            )
            assert link.sync_state == SyncState.LINKED
            by_video = await link_store.get_for_video(workspace_id=workspace_id, video_id=video_id)
            assert by_video is not None
            by_yt_id = await link_store.get_by_youtube_video_id(
                workspace_id=workspace_id, youtube_video_id="yt-real-1"
            )
            assert by_yt_id is not None
            assert by_yt_id.id == link.id

            updated_link = await link_store.update_sync_state(
                workspace_id=workspace_id,
                link_id=link.id,
                sync_state=SyncState.PENDING_SYNC,
            )
            assert updated_link.sync_state == SyncState.PENDING_SYNC

            sync_op_store = SqlSyncOperationStore(factory)
            operation = await sync_op_store.create(
                NewSyncOperation(
                    workspace_id=workspace_id,
                    video_link_id=link.id,
                    applied_snapshot_id=snapshot.id,
                    field_group=SyncFieldGroup.METADATA,
                    status=SyncOperationStatus.SUCCEEDED,
                    error_details=None,
                    quota_cost=50,
                    remote_etag="etag-1",
                    readback_verified=True,
                    finished_at=datetime.now(UTC),
                )
            )
            operations = await sync_op_store.list_for_link(
                workspace_id=workspace_id, video_link_id=link.id
            )
            assert [o.id for o in operations] == [operation.id]

            remote_store = SqlRemoteSnapshotStore(factory)
            remote = await remote_store.save(
                NewRemoteSnapshot(
                    workspace_id=workspace_id,
                    video_link_id=link.id,
                    fields={"title": "Remote Title"},
                    privacy_status="private",
                    has_been_published=False,
                )
            )
            latest_remote = await remote_store.get_latest_for_link(
                workspace_id=workspace_id, video_link_id=link.id
            )
            assert latest_remote is not None
            assert latest_remote.id == remote.id

            capability_store = SqlCapabilityStore(factory)
            evidence = CapabilityEvidence(
                capability=Capability.METADATA_UPDATE,
                status=CapabilityStatus.AVAILABLE,
                verified_on=date(2026, 10, 1),
                source_url="https://developers.google.com/youtube/v3/docs/videos/update",
                required_scopes=("https://www.googleapis.com/auth/youtube",),
                verification_notes="Verified against current docs.",
                updated_at=datetime.now(UTC),
            )
            saved = await capability_store.upsert(evidence)
            assert saved.status == CapabilityStatus.AVAILABLE
            fetched_capability = await capability_store.get(Capability.METADATA_UPDATE)
            assert fetched_capability is not None
            assert fetched_capability.source_url == evidence.source_url
            all_capabilities = await capability_store.list_all()
            assert any(c.capability == Capability.METADATA_UPDATE for c in all_capabilities)

            # Teardown via the owner engine, not the app-role factory:
            # publish_snapshots has no DELETE grant for creatoriqx_app at all
            # (insert-only, ADR 0006/migration 0009), so the app role could
            # never clean this row up even with tenant context set. The owner
            # role is not a bypass-RLS role either (these tables use FORCE ROW
            # LEVEL SECURITY, which applies even to the owner) - it still
            # needs app.workspace_id set, same as the app role would.
            #
            # publish_snapshots also has a BEFORE UPDATE OR DELETE trigger
            # (``publish_snapshots_block_update_delete``, migration 0009) that
            # unconditionally raises, by design (ADR 0006 immutability) - it
            # fires for every role, owner included. The established precedent
            # for cleaning up an append-only table under test (see
            # ``test_platform_tables.py``'s audit_log teardown) is to disable
            # that trigger for the duration of the delete and re-enable it
            # immediately after, rather than skip the delete or touch grants.
            owner_engine = create_async_engine(_test_url("DATABASE_OWNER_URL"))
            try:
                owner_factory = async_sessionmaker(owner_engine, expire_on_commit=False)
                async with owner_factory() as cleanup:
                    await set_tenant_context(cleanup, workspace_id=workspace_id, user_id=user_id)
                    await cleanup.execute(
                        text("DELETE FROM remote_snapshots WHERE workspace_id = :w"),
                        {"w": workspace_id},
                    )
                    await cleanup.execute(
                        text("DELETE FROM sync_operations WHERE workspace_id = :w"),
                        {"w": workspace_id},
                    )
                    await cleanup.execute(
                        text("DELETE FROM youtube_video_links WHERE workspace_id = :w"),
                        {"w": workspace_id},
                    )
                    await cleanup.execute(
                        text(
                            "ALTER TABLE publish_snapshots "
                            "DISABLE TRIGGER publish_snapshots_block_update_delete"
                        )
                    )
                    await cleanup.execute(
                        text("DELETE FROM publish_snapshots WHERE workspace_id = :w"),
                        {"w": workspace_id},
                    )
                    await cleanup.execute(
                        text(
                            "ALTER TABLE publish_snapshots "
                            "ENABLE TRIGGER publish_snapshots_block_update_delete"
                        )
                    )
                    await cleanup.execute(
                        text("DELETE FROM channels WHERE workspace_id = :w"), {"w": workspace_id}
                    )
                    await cleanup.execute(
                        text("DELETE FROM workspaces WHERE id = :w"), {"w": workspace_id}
                    )
                    await cleanup.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
                    await cleanup.execute(
                        text("DELETE FROM youtube_capabilities WHERE capability = :c"),
                        {"c": Capability.METADATA_UPDATE.value},
                    )
                    await cleanup.commit()
            finally:
                await owner_engine.dispose()
        finally:
            await engine.dispose()

    asyncio.run(body())

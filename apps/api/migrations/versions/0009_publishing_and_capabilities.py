"""publish_snapshots, youtube_video_links, sync_operations, remote_snapshots, youtube_capabilities

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-10

Phase 1D tables (spec §3, §7, §15; ADR 0006, ADR 0007). Ownership:
``publish_snapshots``, ``youtube_video_links``, ``sync_operations`` and
``remote_snapshots`` -> publishing module; ``youtube_capabilities`` ->
youtube module.

The first four are ordinary tenant tables: forced RLS, one ``FOR ALL``
policy each. ``youtube_capabilities`` has no ``workspace_id`` column by
design (ADR 0007/0015: one Google Cloud project per deployment, not per
workspace) - the RLS meta-test discovers tenant tables purely by that
column's presence, so it is skipped automatically, not via an allow-list.

``publish_snapshots`` is insert-only for the app role (ADR 0006): UPDATE and
DELETE are revoked and a trigger rejects both, the same enforcement already
proven on ``audit_log`` (migration 0004).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_TABLES = (
    "publish_snapshots",
    "youtube_video_links",
    "sync_operations",
    "remote_snapshots",
)


def upgrade() -> None:
    op.create_table(
        "publish_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("script_version_id", sa.Uuid(), nullable=False),
        sa.Column("metadata_version_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_version_id", sa.Uuid(), nullable=True),
        sa.Column("thumbnail_variant_id", sa.Uuid(), nullable=True),
        sa.Column("disclosure_altered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "disclosure_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publish_snapshots")),
    )
    op.create_table(
        "youtube_video_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=32), nullable=False),
        sa.Column("sync_state", sa.String(length=20), nullable=False, server_default="linked"),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_remote_etag", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_youtube_video_links")),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["channels.id"], name=op.f("fk_youtube_video_links_channel_id_channels")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "youtube_video_id",
            name=op.f("uq_youtube_video_links_workspace_id"),
        ),
    )
    op.create_table(
        "sync_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_link_id", sa.Uuid(), nullable=False),
        sa.Column("applied_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("field_group", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("quota_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remote_etag", sa.String(length=200), nullable=True),
        sa.Column(
            "readback_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_operations")),
        sa.ForeignKeyConstraint(
            ["video_link_id"],
            ["youtube_video_links.id"],
            name=op.f("fk_sync_operations_video_link_id_youtube_video_links"),
        ),
        sa.ForeignKeyConstraint(
            ["applied_snapshot_id"],
            ["publish_snapshots.id"],
            name=op.f("fk_sync_operations_applied_snapshot_id_publish_snapshots"),
        ),
    )
    op.create_table(
        "remote_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_link_id", sa.Uuid(), nullable=False),
        sa.Column(
            "fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("privacy_status", sa.String(length=20), nullable=False),
        sa.Column(
            "has_been_published", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_remote_snapshots")),
        sa.ForeignKeyConstraint(
            ["video_link_id"],
            ["youtube_video_links.id"],
            name=op.f("fk_remote_snapshots_video_link_id_youtube_video_links"),
        ),
    )
    op.create_table(
        "youtube_capabilities",
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="restricted"),
        sa.Column("verified_on", sa.Date(), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "required_scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("verification_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("capability", name=op.f("pk_youtube_capabilities")),
    )

    # --- Row-level security (tenant tables only - youtube_capabilities is global) ---
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL
            USING (workspace_id = current_setting('app.workspace_id', true)::uuid)
            WITH CHECK (workspace_id = current_setting('app.workspace_id', true)::uuid)
            """
        )

    # --- Insert-only enforcement on publish_snapshots (ADR 0006) --------
    op.execute("REVOKE UPDATE, DELETE ON publish_snapshots FROM creatoriqx_app")
    op.execute(
        """
        CREATE FUNCTION publish_snapshots_insert_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'publish_snapshots is immutable: % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER publish_snapshots_block_update_delete
        BEFORE UPDATE OR DELETE ON publish_snapshots
        FOR EACH ROW EXECUTE FUNCTION publish_snapshots_insert_only()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS publish_snapshots_block_update_delete ON publish_snapshots"
    )
    op.execute("DROP FUNCTION IF EXISTS publish_snapshots_insert_only()")
    op.execute("GRANT UPDATE, DELETE ON publish_snapshots TO creatoriqx_app")

    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("youtube_capabilities")
    op.drop_table("remote_snapshots")
    op.drop_table("sync_operations")
    op.drop_table("youtube_video_links")
    op.drop_table("publish_snapshots")

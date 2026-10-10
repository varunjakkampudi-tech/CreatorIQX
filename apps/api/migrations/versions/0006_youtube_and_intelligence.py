"""youtube connection/ingestion tables, quota ledger, recommendations

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-10

Phase 1A tables (spec §7). Ownership: channels, oauth_connections,
channel_videos, quota_ledger -> youtube module; recommendations ->
intelligence module.

All five are ordinary tenant tables: forced RLS, one ``FOR ALL`` policy each
(the same pattern as ``0004_platform_tables.py`` / ``0005_workspaces_rls.py``).
``recommendations.channel_id`` is a cross-module foreign key to
``channels.id`` for referential integrity only - the intelligence module
never writes to ``channels`` and reads it only through the youtube module's
own application-layer port (spec §3 module rule).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_TABLES = (
    "channels",
    "oauth_connections",
    "channel_videos",
    "quota_ledger",
    "recommendations",
)


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("youtube_channel_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=2048), nullable=True),
        sa.Column("subscriber_count", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=True),
        sa.Column("video_count", sa.Integer(), nullable=True),
        sa.Column("uploads_playlist_id", sa.String(length=64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
        sa.UniqueConstraint(
            "workspace_id", "youtube_channel_id", name=op.f("uq_channels_workspace_id")
        ),
    )
    op.create_table(
        "oauth_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("connected_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_connections")),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["channels.id"], name=op.f("fk_oauth_connections_channel_id_channels")
        ),
        sa.UniqueConstraint(
            "workspace_id", "channel_id", name=op.f("uq_oauth_connections_workspace_id")
        ),
    )
    op.create_table(
        "channel_videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=True),
        sa.Column("comment_count", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_videos")),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["channels.id"], name=op.f("fk_channel_videos_channel_id_channels")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "channel_id",
            "youtube_video_id",
            name=op.f("uq_channel_videos_workspace_id"),
        ),
    )
    op.create_table(
        "quota_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=100), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quota_ledger")),
    )
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=True),
        sa.Column("video_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_strength", sa.String(length=10), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendations")),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["channels.id"], name=op.f("fk_recommendations_channel_id_channels")
        ),
    )

    # --- Row-level security ---------------------------------------------
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


def downgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("recommendations")
    op.drop_table("quota_ledger")
    op.drop_table("channel_videos")
    op.drop_table("oauth_connections")
    op.drop_table("channels")

"""plans and videos tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-10

Phase 1B tables (spec §7). Ownership: both -> planning module.

``plans`` is the backlog/calendar entry (spec feature 4). ``videos`` starts
the video aggregate: identity, lifecycle status, and a pointer back to the
plan it was promoted from, if any. Both are ordinary tenant tables: forced
RLS, one ``FOR ALL`` policy each, the same pattern as every other tenant
table (``0006_youtube_and_intelligence.py``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_TABLES = ("plans", "videos")


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("series", sa.String(length=255), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("promoted_video_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plans")),
    )
    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=True),
        sa.Column("plan_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="idea"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_videos")),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name=op.f("fk_videos_plan_id_plans")),
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
    op.drop_table("videos")
    op.drop_table("plans")

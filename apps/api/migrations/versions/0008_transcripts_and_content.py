"""transcripts, transcript_segments, script_versions, metadata_versions, chapter_versions

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-10

Phase 1C tables (spec §7, feature 22, 5, 9, 10). Ownership: ``transcripts``
and ``transcript_segments`` -> transcripts module; ``script_versions``,
``metadata_versions``, ``chapter_versions`` -> content module. All five are
ordinary tenant tables: forced RLS, one ``FOR ALL`` policy each, the same
pattern as every prior tenant table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_TABLES = (
    "transcripts",
    "transcript_segments",
    "script_versions",
    "metadata_versions",
    "chapter_versions",
)


def upgrade() -> None:
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_transcript_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcripts")),
        sa.ForeignKeyConstraint(
            ["parent_transcript_id"],
            ["transcripts.id"],
            name=op.f("fk_transcripts_parent_transcript_id_transcripts"),
        ),
    )
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("transcript_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcript_segments")),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name=op.f("fk_transcript_segments_transcript_id_transcripts"),
        ),
    )
    op.create_table(
        "script_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("variant_label", sa.String(length=100), nullable=False),
        sa.Column("author", sa.String(length=10), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False, server_default=""),
        sa.Column("outline", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_script_versions")),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["script_versions.id"],
            name=op.f("fk_script_versions_parent_version_id_script_versions"),
        ),
    )
    op.create_table(
        "metadata_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("disclosure_altered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("disclosure_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metadata_versions")),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["metadata_versions.id"],
            name=op.f("fk_metadata_versions_parent_version_id_metadata_versions"),
        ),
    )
    op.create_table(
        "chapter_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("transcript_id", sa.Uuid(), nullable=False),
        sa.Column(
            "chapters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chapter_versions")),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name=op.f("fk_chapter_versions_transcript_id_transcripts"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["chapter_versions.id"],
            name=op.f("fk_chapter_versions_parent_version_id_chapter_versions"),
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
    op.drop_table("chapter_versions")
    op.drop_table("metadata_versions")
    op.drop_table("script_versions")
    op.drop_table("transcript_segments")
    op.drop_table("transcripts")

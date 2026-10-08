"""row-level security on tenant tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08

Enables and FORCES RLS on every tenant table (ADR 0002). memberships is the
access table, so reads also allow a user to see their own rows (workspace
discovery at login); writes are restricted to the current workspace.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tenant tables (those with a workspace_id column). Extended as tables are added.
TENANT_TABLES = ("memberships",)


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY memberships_read ON memberships FOR SELECT
        USING (
            workspace_id = current_setting('app.workspace_id', true)::uuid
            OR user_id = current_setting('app.user_id', true)::uuid
        )
        """
    )
    op.execute(
        """
        CREATE POLICY memberships_write ON memberships FOR ALL
        USING (workspace_id = current_setting('app.workspace_id', true)::uuid)
        WITH CHECK (workspace_id = current_setting('app.workspace_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS memberships_write ON memberships")
    op.execute("DROP POLICY IF EXISTS memberships_read ON memberships")
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

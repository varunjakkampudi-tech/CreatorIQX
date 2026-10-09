"""row-level security on workspaces

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-09

``workspaces`` has no ``workspace_id`` column (its own id is the tenant key),
so the RLS meta-test does not select it. It still needs forced RLS (ADR 0002,
ADR 0011). Policies:

* read: the current workspace, or any workspace the current user is a member of
  (workspace discovery at login and in P0-054 workspace selection);
* insert: any row. The bootstrap inserts a new workspace before its membership
  exists, so the insert check cannot depend on membership. The following
  ``INSERT ... RETURNING`` is still checked by the read policy, which the new
  row satisfies because the bootstrap sets the new id as current;
* update: only the current workspace. Deletes are not granted.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspaces FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY workspaces_read ON workspaces FOR SELECT
        USING (
            id = current_setting('app.workspace_id', true)::uuid
            OR EXISTS (
                SELECT 1 FROM memberships m
                WHERE m.workspace_id = workspaces.id
                  AND m.user_id = current_setting('app.user_id', true)::uuid
            )
        )
        """
    )
    op.execute("CREATE POLICY workspaces_insert ON workspaces FOR INSERT WITH CHECK (true)")
    op.execute(
        """
        CREATE POLICY workspaces_update ON workspaces FOR UPDATE
        USING (id = current_setting('app.workspace_id', true)::uuid)
        WITH CHECK (id = current_setting('app.workspace_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS workspaces_update ON workspaces")
    op.execute("DROP POLICY IF EXISTS workspaces_insert ON workspaces")
    op.execute("DROP POLICY IF EXISTS workspaces_read ON workspaces")
    op.execute("ALTER TABLE workspaces NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspaces DISABLE ROW LEVEL SECURITY")

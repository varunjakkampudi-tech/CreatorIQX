"""platform tables: audit log, usage events, outbox, idempotency keys

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09

Four platform tables (spec §6, §7). Ownership: audit_log -> audit module,
usage_events -> telemetry module, outbox_events and idempotency_keys -> jobs
module.

RLS: usage_events and idempotency_keys are ordinary tenant tables (forced RLS,
one policy each). audit_log is special: ``workspace_id`` is nullable (some
events, such as user creation at first login, happen before any workspace
exists), so it gets a read policy that also allows nullable rows and a
separate insert policy that allows any workspace (the app writes audit rows
for actions it is already trusted to perform). outbox_events carries no
``workspace_id`` and stays outside RLS: the relay worker (P0-061) must read
unpublished rows across every tenant.

Append-only: audit_log rows are never updated or deleted (STRIDE T-T2, spec
§10). Defence in depth: the runtime role's UPDATE/DELETE privileges (granted
by the default-privilege rule in ``infra/compose/postgres-init/01-roles.sh``)
are revoked, and a trigger rejects UPDATE/DELETE for every role, including
the owner, so no SQL path can tamper with history.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_events")),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("workspace_id", "key", name=op.f("uq_idempotency_keys_workspace_id")),
    )

    # --- Row-level security ---------------------------------------------
    for table in ("usage_events", "idempotency_keys", "audit_log"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY usage_events_tenant_isolation ON usage_events FOR ALL
        USING (workspace_id = current_setting('app.workspace_id', true)::uuid)
        WITH CHECK (workspace_id = current_setting('app.workspace_id', true)::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY idempotency_keys_tenant_isolation ON idempotency_keys FOR ALL
        USING (workspace_id = current_setting('app.workspace_id', true)::uuid)
        WITH CHECK (workspace_id = current_setting('app.workspace_id', true)::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY audit_log_read ON audit_log FOR SELECT
        USING (
            workspace_id = current_setting('app.workspace_id', true)::uuid
            OR workspace_id IS NULL
        )
        """
    )
    op.execute("CREATE POLICY audit_log_write ON audit_log FOR INSERT WITH CHECK (true)")

    # --- Append-only enforcement on audit_log ---------------------------
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM creatoriqx_app")
    op.execute(
        """
        CREATE FUNCTION audit_log_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_block_update_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_block_update_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")
    op.execute("GRANT UPDATE, DELETE ON audit_log TO creatoriqx_app")

    op.execute("DROP POLICY IF EXISTS audit_log_write ON audit_log")
    op.execute("DROP POLICY IF EXISTS audit_log_read ON audit_log")
    op.execute("DROP POLICY IF EXISTS idempotency_keys_tenant_isolation ON idempotency_keys")
    op.execute("DROP POLICY IF EXISTS usage_events_tenant_isolation ON usage_events")

    for table in ("usage_events", "idempotency_keys", "audit_log"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("idempotency_keys")
    op.drop_table("outbox_events")
    op.drop_table("usage_events")
    op.drop_table("audit_log")

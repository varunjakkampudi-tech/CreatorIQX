"""Integration tests for the PostgreSQL roles (P0-020, ADR 0002).

They run SQL as the real roles inside the local Postgres container, against the
``creatoriqx_test`` database. Start services first: ``py scripts/dev.py up``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.integration

CONTAINER = "creatoriqx-postgres-1"
DB = "creatoriqx_test"
WS_A = "00000000-0000-7000-8000-00000000000a"
WS_B = "00000000-0000-7000-8000-00000000000b"
TABLE = "p0020_rls_probe"


def psql(role: str, sql: str) -> subprocess.CompletedProcess[str]:
    """Run SQL as ``role`` in the test database; never raises on SQL errors."""
    return subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "psql",
            "-U",
            role,
            "-d",
            DB,
            "-v",
            "ON_ERROR_STOP=1",
            "-qAt",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.fixture(scope="module", autouse=True)
def probe_table() -> Iterator[None]:
    health = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINER],
        capture_output=True,
        text=True,
        check=False,
    )
    if health.stdout.strip() != "healthy":
        pytest.fail("Postgres container is not running. Start it with: py scripts/dev.py up")
    setup = psql(
        "creatoriqx_owner",
        f"""
        DROP TABLE IF EXISTS {TABLE};
        CREATE TABLE {TABLE} (workspace_id uuid NOT NULL, note text NOT NULL);
        ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON {TABLE}
          USING (workspace_id = current_setting('app.workspace_id', true)::uuid)
          WITH CHECK (workspace_id = current_setting('app.workspace_id', true)::uuid);
        SET app.workspace_id = '{WS_A}';
        INSERT INTO {TABLE} VALUES ('{WS_A}', 'row-a');
        SET app.workspace_id = '{WS_B}';
        INSERT INTO {TABLE} VALUES ('{WS_B}', 'row-b');
    """,
    )
    assert setup.returncode == 0, setup.stderr
    yield
    psql("creatoriqx_owner", f"DROP TABLE IF EXISTS {TABLE};")


def test_roles_cannot_escalate_or_bypass_rls() -> None:
    result = psql(
        "creatoriqx_owner",
        "SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles "
        "WHERE rolname IN ('creatoriqx_owner', 'creatoriqx_app') ORDER BY rolname;",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        "creatoriqx_app|f|f|f|f",
        "creatoriqx_owner|f|f|f|f",
    ]


def test_app_role_cannot_create_tables() -> None:
    result = psql("creatoriqx_app", "CREATE TABLE should_not_exist (id int);")
    assert result.returncode != 0
    assert "permission denied for schema public" in result.stderr


def test_app_role_cannot_alter_or_disable_rls() -> None:
    result = psql("creatoriqx_app", f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;")
    assert result.returncode != 0
    assert "must be owner" in result.stderr


def test_app_role_sees_only_its_workspace() -> None:
    result = psql(
        "creatoriqx_app",
        f"SET app.workspace_id = '{WS_A}'; SELECT note FROM {TABLE} ORDER BY note;",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["row-a"]


def test_missing_tenant_context_fails_closed() -> None:
    result = psql("creatoriqx_app", f"SELECT count(*) FROM {TABLE};")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0"


def test_app_role_cannot_write_into_another_workspace() -> None:
    result = psql(
        "creatoriqx_app",
        f"SET app.workspace_id = '{WS_A}'; INSERT INTO {TABLE} VALUES ('{WS_B}', 'smuggled');",
    )
    assert result.returncode != 0
    assert "violates row-level security policy" in result.stderr


def test_app_role_cannot_update_other_workspace_rows() -> None:
    result = psql(
        "creatoriqx_app",
        f"SET app.workspace_id = '{WS_A}'; "
        f"UPDATE {TABLE} SET note = 'hijacked' WHERE workspace_id = '{WS_B}' RETURNING note;",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""  # zero rows visible, zero rows changed

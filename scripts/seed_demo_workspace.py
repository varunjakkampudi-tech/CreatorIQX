"""Create a second demo workspace, for manual cross-tenant checks (P0-022).

The real login flow (P0-053) creates a personal workspace for whichever
Google account signs in - there is deliberately no other way to create one,
so this script goes through the exact same tenant-safe code path
(``WorkspaceBootstrapService.ensure_personal_workspace``), just with a fixed,
fake Google subject instead of a real OIDC callback. That means the seeded
workspace is written under the same forced row-level security as a real
login, with the same audit trail and outbox event, not a backdoor insert.

Idempotent: re-running it finds the same fake subject and returns the
existing ids rather than creating a second copy.

Usage:
    uv run python scripts/seed_demo_workspace.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SEED_SUBJECT = "seed:demo-cross-tenant"
_SEED_EMAIL = "demo-cross-tenant@creatoriqx.local"


def _load_env() -> None:
    """Load KEY=VALUE lines from .env into the environment (mirrors dev.py)."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        print("ERROR: .env is missing. Run: python scripts/dev.py setup", file=sys.stderr)
        raise SystemExit(1)
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


async def _seed() -> None:
    # Imported after _load_env() populates the environment that Settings() reads.
    from creatoriqx_api.modules.workspaces.application.bootstrap_service import (
        WorkspaceBootstrapService,
    )
    from creatoriqx_api.modules.workspaces.infrastructure.sql_store import (
        SqlPersonalWorkspaceStore,
    )
    from creatoriqx_api.platform.database import create_engine, create_session_factory
    from creatoriqx_api.settings import get_settings

    settings = get_settings()
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        service = WorkspaceBootstrapService(SqlPersonalWorkspaceStore(factory))
        result = await service.ensure_personal_workspace(
            subject=_SEED_SUBJECT,
            email=_SEED_EMAIL,
            correlation_id="seed-demo-workspace",
        )
        verb = "Created" if result.workspace_created else "Found existing"
        print(f"{verb} demo workspace {result.workspace_id} (user {result.user_id}).")
        print(f"Sign-in email for manual cross-tenant checks: {_SEED_EMAIL}")
    finally:
        await engine.dispose()


def main() -> int:
    _load_env()
    asyncio.run(_seed())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Single import point that registers every ORM table on ``Base.metadata``.

Alembic's env imports this module so autogenerate sees all tables. Bounded
contexts add their table-module imports here as they are built.
"""

from __future__ import annotations

from creatoriqx_api.modules.audit.infrastructure import tables as _audit
from creatoriqx_api.modules.identity.infrastructure import tables as _identity
from creatoriqx_api.modules.jobs.infrastructure import tables as _jobs
from creatoriqx_api.modules.telemetry.infrastructure import tables as _telemetry
from creatoriqx_api.modules.workspaces.infrastructure import tables as _workspaces

__all__ = ["_audit", "_identity", "_jobs", "_telemetry", "_workspaces"]

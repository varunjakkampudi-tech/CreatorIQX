"""Single import point that registers every ORM table on ``Base.metadata``.

Alembic's env imports this module so autogenerate sees all tables. Bounded
contexts add their table-module imports here as they are built.
"""

from __future__ import annotations

from creatoriqx_api.modules.identity.infrastructure import tables as _identity

__all__ = ["_identity"]

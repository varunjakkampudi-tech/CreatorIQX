"""Single import point that registers every ORM table on ``Base.metadata``.

Alembic's env imports this module so autogenerate sees all tables. Bounded
contexts add their table-module imports here as they are built (P0-041 onward);
until then there are no tables and the baseline migration is empty.
"""

from __future__ import annotations

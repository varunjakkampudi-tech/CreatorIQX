"""baseline (empty): establishes the migration chain

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema yet; the first tables arrive in the next migration (P0-041)."""


def downgrade() -> None:
    """Nothing to undo."""

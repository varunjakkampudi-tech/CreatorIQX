"""Workspace roles (spec §10 Authorization: RBAC owner/editor/viewer)."""

from __future__ import annotations

import enum


class Role(enum.StrEnum):
    """A member's role within one workspace."""

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

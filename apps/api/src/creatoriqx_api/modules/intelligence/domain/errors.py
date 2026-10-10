"""Typed errors for the intelligence module (spec §8)."""

from __future__ import annotations

from creatoriqx_api.platform.errors import DomainError


class RecommendationNotFoundError(DomainError):
    """No recommendation with that id exists in this workspace."""

    status = 404
    title = "Recommendation not found"
    code = "recommendation-not-found"

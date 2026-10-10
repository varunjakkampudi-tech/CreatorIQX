"""The YouTube publishing capability model (spec §3 "YouTube publishing capability
model"): every write operation is a capability with recorded verification
evidence, never an assumption. ``youtube_capabilities`` is a global,
non-tenant table (ADR 0007/0015) - one row per capability, shared by every
workspace, since it describes what *this app's* Google API project can do,
not per-workspace data.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime


class Capability(enum.StrEnum):
    """One YouTube write operation this app may perform (spec §3 table)."""

    METADATA_UPDATE = "metadata_update"
    THUMBNAIL_UPDATE = "thumbnail_update"
    SCHEDULING = "scheduling"
    COMMENT_REPLY = "comment_reply"
    DIRECT_VIDEO_UPLOAD = "direct_video_upload"
    DIRECT_PUBLISH = "direct_publish"


class CapabilityStatus(enum.StrEnum):
    """Every capability resolves to exactly one of these (spec §3)."""

    AVAILABLE = "available"
    RESTRICTED = "restricted"
    UNSUPPORTED = "unsupported"
    REQUIRES_AUDIT = "requires_audit"


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    """The recorded evidence for one capability's current status (spec §3).

    A capability cannot become :attr:`CapabilityStatus.AVAILABLE` without all
    four evidence fields populated - see :func:`assert_evidence_complete`,
    which ``CapabilityService`` calls before persisting any status change to
    ``available``. ``requires_audit``/``restricted``/``unsupported`` statuses
    may carry partial evidence (e.g. "no evidence yet, default-restricted").
    """

    capability: Capability
    status: CapabilityStatus
    verified_on: date | None
    source_url: str | None
    required_scopes: tuple[str, ...]
    verification_notes: str | None
    updated_at: datetime


def is_evidence_complete(evidence: CapabilityEvidence) -> bool:
    """Whether every evidence field needed to claim ``available`` is present."""
    return bool(
        evidence.verified_on is not None
        and evidence.source_url
        and evidence.required_scopes
        and evidence.verification_notes
    )


def assert_evidence_complete(evidence: CapabilityEvidence) -> None:
    """Refuse to enable any write capability without recorded verification evidence
    (spec §3, verbatim rule). Only relevant when the caller is about to set
    ``status = available``; the caller enforces that gating, this just checks the
    evidence shape.
    """
    from creatoriqx_api.modules.publishing.domain.errors import (
        CapabilityEvidenceIncompleteError,
    )

    if not is_evidence_complete(evidence):
        raise CapabilityEvidenceIncompleteError(
            f"{evidence.capability.value} is missing verified_on, source_url, "
            "required_scopes, or verification_notes"
        )

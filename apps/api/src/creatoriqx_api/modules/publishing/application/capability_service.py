"""Resolves and records capability evidence (spec §3: every YouTube write
operation is a capability with recorded evidence, never an assumption).
"""

from __future__ import annotations

from creatoriqx_api.modules.publishing.application.ports import CapabilityStore
from creatoriqx_api.modules.publishing.domain.capability import (
    Capability,
    CapabilityEvidence,
    CapabilityStatus,
    assert_evidence_complete,
)
from creatoriqx_api.modules.publishing.domain.errors import (
    CapabilityNotFoundError,
    CapabilityUnavailableError,
)


class CapabilityService:
    def __init__(self, store: CapabilityStore) -> None:
        self._store = store

    async def get(self, capability: Capability) -> CapabilityEvidence:
        evidence = await self._store.get(capability)
        if evidence is None:
            raise CapabilityNotFoundError()
        return evidence

    async def list_all(self) -> list[CapabilityEvidence]:
        return await self._store.list_all()

    async def require_available(self, capability: Capability) -> CapabilityEvidence:
        """Refuse to proceed unless this capability is verified ``available``
        (spec §3: "Refuse to enable any write capability without recorded
        verification evidence."). Used by ``YoutubeSyncService`` before every
        write attempt.
        """
        evidence = await self.get(capability)
        if evidence.status != CapabilityStatus.AVAILABLE:
            raise CapabilityUnavailableError(
                f"{capability.value} is {evidence.status.value}, not available"
            )
        return evidence

    async def record_evidence(self, evidence: CapabilityEvidence) -> CapabilityEvidence:
        """Record a status/evidence change, verified by the owner against current
        Google docs before being called (this is not itself a verification step -
        it only enforces that ``available`` can never be recorded without the
        full evidence shape, spec §3's hard rule).
        """
        if evidence.status == CapabilityStatus.AVAILABLE:
            assert_evidence_complete(evidence)
        return await self._store.upsert(evidence)

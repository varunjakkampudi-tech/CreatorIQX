"""SQLAlchemy adapter for ``publishing.application.ports.CapabilityStore``.

Lives here, not under ``publishing``, because ``youtube_capabilities`` is
owned by the ``youtube`` module (``docs/DATA_MODEL.md``'s table-ownership
list, ADR 0007/0015) - the same cross-module-port shape as
``content.application`` depending on ``transcripts``' own port, just with
the adapter on the owning side instead of the consuming side. No tenant
context: this is a global, non-RLS table (one row per capability, shared by
every workspace), so a plain ``session_scope`` is enough.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.publishing.domain.capability import (
    Capability,
    CapabilityEvidence,
    CapabilityStatus,
)
from creatoriqx_api.modules.youtube.infrastructure.tables import YoutubeCapabilityRow
from creatoriqx_api.platform.database import session_scope


class SqlCapabilityStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def get(self, capability: Capability) -> CapabilityEvidence | None:
        async with session_scope(self._factory) as session:
            result = await session.execute(
                select(YoutubeCapabilityRow).where(
                    YoutubeCapabilityRow.capability == capability.value
                )
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def list_all(self) -> list[CapabilityEvidence]:
        async with session_scope(self._factory) as session:
            result = await session.execute(select(YoutubeCapabilityRow))
            return [_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, evidence: CapabilityEvidence) -> CapabilityEvidence:
        async with session_scope(self._factory) as session:
            values = {
                "capability": evidence.capability.value,
                "status": evidence.status.value,
                "verified_on": evidence.verified_on,
                "source_url": evidence.source_url,
                "required_scopes": list(evidence.required_scopes),
                "verification_notes": evidence.verification_notes or "",
            }
            stmt = (
                pg_insert(YoutubeCapabilityRow)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["capability"],
                    set_={k: v for k, v in values.items() if k != "capability"},
                )
            )
            await session.execute(stmt)
            result = await session.execute(
                select(YoutubeCapabilityRow).where(
                    YoutubeCapabilityRow.capability == evidence.capability.value
                )
            )
            row = result.scalar_one()
            return _to_domain(row)


def _to_domain(row: YoutubeCapabilityRow) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=Capability(row.capability),
        status=CapabilityStatus(row.status),
        verified_on=row.verified_on,
        source_url=row.source_url,
        required_scopes=tuple(row.required_scopes),
        verification_notes=row.verification_notes or None,
        updated_at=row.updated_at,
    )

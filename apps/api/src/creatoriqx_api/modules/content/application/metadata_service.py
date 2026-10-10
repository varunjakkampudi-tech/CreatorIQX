"""The metadata/SEO use case (spec feature 9): create, compare, restore versions."""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.content.application.ports import (
    MetadataVersionStore,
    NewMetadataVersion,
)
from creatoriqx_api.modules.content.domain.errors import MetadataVersionNotFoundError
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion, character_limit_warnings


class MetadataService:
    def __init__(self, store: MetadataVersionStore) -> None:
        self._store = store

    async def create_version(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        title: str,
        description: str,
        tags: tuple[str, ...],
        category: str | None,
        disclosure_altered: bool,
        disclosure_synthetic: bool,
        rationale: str,
    ) -> tuple[MetadataVersion, list[str]]:
        version = await self._store.create(
            NewMetadataVersion(
                workspace_id=workspace_id,
                video_id=video_id,
                title=title,
                description=description,
                tags=tags,
                category=category,
                disclosure_altered=disclosure_altered,
                disclosure_synthetic=disclosure_synthetic,
                rationale=rationale,
            )
        )
        return version, character_limit_warnings(title=title, description=description)

    async def list_versions(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[MetadataVersion]:
        return await self._store.list_for_video(workspace_id=workspace_id, video_id=video_id)

    async def restore_version(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID, version_id: uuid.UUID
    ) -> MetadataVersion:
        target = await self._store.get(workspace_id=workspace_id, version_id=version_id)
        if target is None or target.video_id != video_id:
            raise MetadataVersionNotFoundError()
        return await self._store.create(
            NewMetadataVersion(
                workspace_id=workspace_id,
                video_id=video_id,
                title=target.title,
                description=target.description,
                tags=target.tags,
                category=target.category,
                disclosure_altered=target.disclosure_altered,
                disclosure_synthetic=target.disclosure_synthetic,
                rationale=target.rationale,
                parent_version_id=target.id,
            )
        )

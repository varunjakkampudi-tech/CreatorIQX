"""The script use case (spec feature 5): create, compare, restore versions."""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.content.application.ports import NewScriptVersion, ScriptVersionStore
from creatoriqx_api.modules.content.domain.errors import ScriptVersionNotFoundError
from creatoriqx_api.modules.content.domain.script import ScriptAuthor, ScriptVersion


class ScriptService:
    def __init__(self, store: ScriptVersionStore) -> None:
        self._store = store

    async def create_version(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        variant_label: str,
        author: ScriptAuthor,
        hook: str,
        outline: str,
        body: str,
    ) -> ScriptVersion:
        return await self._store.create(
            NewScriptVersion(
                workspace_id=workspace_id,
                video_id=video_id,
                variant_label=variant_label,
                author=author,
                hook=hook,
                outline=outline,
                body=body,
            )
        )

    async def list_versions(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[ScriptVersion]:
        return await self._store.list_for_video(workspace_id=workspace_id, video_id=video_id)

    async def restore_version(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID, version_id: uuid.UUID
    ) -> ScriptVersion:
        """Make an old version current again by creating a new version with its content."""
        target = await self._store.get(workspace_id=workspace_id, version_id=version_id)
        if target is None or target.video_id != video_id:
            raise ScriptVersionNotFoundError()
        return await self._store.create(
            NewScriptVersion(
                workspace_id=workspace_id,
                video_id=video_id,
                variant_label=target.variant_label,
                author=target.author,
                hook=target.hook,
                outline=target.outline,
                body=target.body,
                parent_version_id=target.id,
            )
        )

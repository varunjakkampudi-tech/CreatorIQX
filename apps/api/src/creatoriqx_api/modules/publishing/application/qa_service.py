"""Runs the pre-publish QA checklist against a video's current artifacts (spec
feature 12).

Reads ``content``'s stores directly through their own public ports - the
same shape of cross-module read ``content.application.chapter_service``
already has on ``transcripts`` - never ``content``'s tables.
"""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.content.application.ports import (
    ChapterVersionStore,
    MetadataVersionStore,
    ScriptVersionStore,
)
from creatoriqx_api.modules.content.domain.chapters import ChapterVersion
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion
from creatoriqx_api.modules.content.domain.script import ScriptVersion
from creatoriqx_api.modules.publishing.application.ports import (
    RemoteSnapshotStore,
    YoutubeVideoLinkStore,
)
from creatoriqx_api.modules.publishing.domain.qa import QaInput, QaResult, run_qa_checklist


def _current_metadata(versions: list[MetadataVersion]) -> MetadataVersion | None:
    return next((v for v in versions if v.is_current), None)


def _current_script(versions: list[ScriptVersion]) -> ScriptVersion | None:
    return next((v for v in versions if v.is_current), None)


def _current_chapters(versions: list[ChapterVersion]) -> ChapterVersion | None:
    return next((v for v in versions if v.is_current), None)


class QaService:
    def __init__(
        self,
        *,
        script_store: ScriptVersionStore,
        metadata_store: MetadataVersionStore,
        chapter_store: ChapterVersionStore,
        video_link_store: YoutubeVideoLinkStore,
        remote_snapshot_store: RemoteSnapshotStore,
    ) -> None:
        self._scripts = script_store
        self._metadata = metadata_store
        self._chapters = chapter_store
        self._links = video_link_store
        self._remote_snapshots = remote_snapshot_store

    async def run(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        wants_scheduling: bool = False,
    ) -> QaResult:
        """Build :class:`QaInput` from the video's *current* versions and run the
        checklist. Missing versions are treated as empty values, which the
        checklist itself fails on a specific, named check rather than raising -
        "incomplete video" isn't a special case, it's just several failing rows.
        """
        metadata = _current_metadata(
            await self._metadata.list_for_video(workspace_id=workspace_id, video_id=video_id)
        )
        script = _current_script(
            await self._scripts.list_for_video(workspace_id=workspace_id, video_id=video_id)
        )
        chapters = _current_chapters(
            await self._chapters.list_for_video(workspace_id=workspace_id, video_id=video_id)
        )
        link = await self._links.get_for_video(workspace_id=workspace_id, video_id=video_id)
        remote = (
            await self._remote_snapshots.get_latest_for_link(
                workspace_id=workspace_id, video_link_id=link.id
            )
            if link is not None
            else None
        )

        qa_input = QaInput(
            title=metadata.title if metadata else "",
            hook=script.hook if script else "",
            description=metadata.description if metadata else "",
            tags=metadata.tags if metadata else (),
            chapters=chapters.chapters if chapters else None,
            # No thumbnail_variants producer exists in Core yet (Known gap 3),
            # so this is always advisory-only until that tier is built.
            has_thumbnail=False,
            disclosure_altered=metadata.disclosure_altered if metadata else False,
            disclosure_synthetic=metadata.disclosure_synthetic if metadata else False,
            wants_scheduling=wants_scheduling,
            linked_video_privacy_status=remote.privacy_status if remote else None,
            linked_video_has_been_published=remote.has_been_published if remote else None,
        )
        return run_qa_checklist(video_id, qa_input)

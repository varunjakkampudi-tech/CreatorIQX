"""Ports for the transcripts use case (spec §6 ports and adapters).

``TranscriptStore`` is this module's public interface: the ``content``
module's chapter generation (Phase 1C) depends on this protocol, not on
``SqlTranscriptStore`` directly, which is the "other modules consume it
through the owner's public interface" rule from spec §3 applied across
module application layers rather than only at the infrastructure boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from creatoriqx_api.modules.transcripts.domain.transcript import (
    Transcript,
    TranscriptSegment,
    TranscriptSource,
)


@dataclass(frozen=True, slots=True)
class NewTranscript:
    """What the application layer asks a :class:`TranscriptStore` to persist."""

    workspace_id: uuid.UUID
    video_id: uuid.UUID | None
    source: TranscriptSource
    language: str
    segments: tuple[TranscriptSegment, ...]
    parent_transcript_id: uuid.UUID | None = None


class TranscriptStore(Protocol):
    """Persists transcripts and their segments (write-once, spec §7)."""

    async def create(self, transcript: NewTranscript) -> Transcript: ...

    async def get(
        self, *, workspace_id: uuid.UUID, transcript_id: uuid.UUID
    ) -> Transcript | None: ...

    async def list_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> list[Transcript]: ...

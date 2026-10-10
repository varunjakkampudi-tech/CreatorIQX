"""ORM tables owned by the content module (spec §7, Phase 1C).

``script_versions``, ``metadata_versions`` and ``chapter_versions`` each
carry their own ``is_current`` flag per ``video_id`` - "pointers to the
current version of each artifact" (spec §7) live here, one boolean per
table, rather than as columns on ``videos`` itself. Phase 1D's
``publish_snapshots`` is the first thing that actually needs a single,
frozen combination of version ids; until then, each table answering "what's
current for this video" on its own is simpler and needs no cross-module
write access to ``planning``'s ``videos`` table. Recorded as a scope
decision in ADR 0014.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class ScriptVersionRow(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "script_versions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    video_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    variant_label: Mapped[str] = mapped_column(String(100), nullable=False)
    author: Mapped[str] = mapped_column(String(10), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("script_versions.id"), default=None
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MetadataVersionRow(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "metadata_versions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    video_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    category: Mapped[str | None] = mapped_column(String(100), default=None)
    disclosure_altered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disclosure_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("metadata_versions.id"), default=None
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ChapterVersionRow(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "chapter_versions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    video_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transcripts.id"), nullable=False
    )
    chapters: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("chapter_versions.id"), default=None
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

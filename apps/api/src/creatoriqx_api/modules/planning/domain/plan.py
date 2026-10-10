"""The planner's backlog/calendar entry (spec feature 4).

A ``Plan`` is a lightweight idea on the backlog or calendar - a title, notes,
an optional series/cluster label and an optional target date. It carries no
lifecycle of its own; "becoming a Video" (spec feature 4 acceptance: "Plans
persist and can become Video records in one click") is the one thing a plan
can do, recorded here as ``promoted_video_id`` once it happens. Promotion is
one-way: a promoted plan does not go back to being unpromoted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class Plan:
    """One backlog/calendar entry (spec §7 context: owned by ``planning``)."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    notes: str
    series: str | None
    scheduled_date: date | None
    promoted_video_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

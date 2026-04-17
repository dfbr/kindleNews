from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Story:
    story_id: str
    title: str
    url: str
    source: str
    published_at: datetime
    summary: str = ""
    content: str = ""
    image_url: str | None = None
    image_credit: str | None = None
    relevance_reason: str = ""
    word_budget: int = 0


@dataclass(slots=True)
class WeeklyDigest:
    publication_date: str
    title: str
    editor_note: str
    stories: list[Story] = field(default_factory=list)

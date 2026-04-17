from datetime import UTC, datetime
from pathlib import Path

from kindle_news.config import default_config
from kindle_news.models import Story
from kindle_news.pipeline import _exclude_seen, _exclude_seen_with_config
from kindle_news.state import StoryState


def test_exclude_seen_stories() -> None:
    stories = [
        Story(
            story_id="1",
            title="Seen",
            url="https://example.com/seen",
            source="feed",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        Story(
            story_id="2",
            title="Fresh",
            url="https://example.com/fresh",
            source="feed",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    ]
    state = StoryState(used_urls={"https://example.com/seen"}, used_titles=set())
    fresh = _exclude_seen(stories, state)
    assert [item.story_id for item in fresh] == ["2"]


def test_exclude_similar_seen_story_unless_continuation() -> None:
    config = default_config(Path("."))
    state = StoryState(used_urls=set(), used_titles={"uk budget plan announced"})
    stories = [
        Story(
            story_id="1",
            title="UK budget plan announced again",
            url="https://example.com/repeat",
            source="feed",
            published_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        Story(
            story_id="2",
            title="UK budget plan announced update",
            url="https://example.com/update",
            source="feed",
            published_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
    ]

    fresh = _exclude_seen_with_config(stories, state, config)

    assert [item.story_id for item in fresh] == ["2"]

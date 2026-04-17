from datetime import UTC, datetime

from kindle_news.feeds import are_titles_similar, canonicalize_url, dedupe_stories
from kindle_news.models import Story


def test_canonicalize_url_removes_tracking_params() -> None:
    url = "https://example.com/story?utm_source=x&id=1&fbclid=y"
    assert canonicalize_url(url) == "https://example.com/story?id=1"


def test_dedupe_stories_prefers_newest() -> None:
    older = Story(
        story_id="a",
        title="Major event unfolds",
        url="https://example.com/story",
        source="feed-a",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = Story(
        story_id="b",
        title="Major event unfolds",
        url="https://example.com/story",
        source="feed-b",
        published_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    deduped = dedupe_stories([older, newer])
    assert len(deduped) == 1
    assert deduped[0].story_id == "b"


def test_title_similarity() -> None:
    assert are_titles_similar("AI policy update", "AI policy updates")

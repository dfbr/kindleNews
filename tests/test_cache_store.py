from datetime import UTC, datetime
from pathlib import Path

from kindle_news.cache_store import clear_cache, load_cached_stories, save_daily_cache
from kindle_news.models import Story


def _story(story_id: str, published_at: datetime) -> Story:
    return Story(
        story_id=story_id,
        title=f"Story {story_id}",
        url=f"https://example.com/{story_id}",
        source="https://example.com/feed.xml",
        published_at=published_at,
        summary="Summary",
    )


def test_save_and_load_daily_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    expected = _story("s1", now)

    path = save_daily_cache(cache_dir, [expected], now=now)
    stories, files = load_cached_stories(cache_dir, lookback_days=7, now=now)

    assert path.exists()
    assert files == [path]
    assert len(stories) == 1
    assert stories[0].story_id == "s1"


def test_load_cached_stories_ignores_old_files(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    recent = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    old = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    save_daily_cache(cache_dir, [_story("recent", recent)], now=recent)
    save_daily_cache(cache_dir, [_story("old", old)], now=old)

    stories, _ = load_cached_stories(cache_dir, lookback_days=7, now=recent)

    assert [item.story_id for item in stories] == ["recent"]


def test_clear_cache_removes_daily_files(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    save_daily_cache(cache_dir, [_story("s1", now)], now=now)

    removed = clear_cache(cache_dir)

    assert removed == 1
    assert list(cache_dir.glob("daily-*.json")) == []

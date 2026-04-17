from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .models import Story


def save_daily_cache(cache_dir: Path, stories: list[Story], now: datetime | None = None) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).date().isoformat()
    target = cache_dir / f"daily-{stamp}.json"
    payload = [_story_to_dict(item) for item in stories]
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def load_cached_stories(
    cache_dir: Path,
    lookback_days: int,
    now: datetime | None = None,
) -> tuple[list[Story], list[Path]]:
    if not cache_dir.exists():
        return [], []

    pivot = now or datetime.now(UTC)
    cutoff_date = (pivot - timedelta(days=lookback_days)).date()

    selected_files: list[Path] = []
    stories: list[Story] = []
    for path in sorted(cache_dir.glob("daily-*.json")):
        day = _date_from_daily_file(path)
        if day is None or day < cutoff_date:
            continue

        selected_files.append(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue

        for raw in data:
            if isinstance(raw, dict):
                parsed = _story_from_dict(raw)
                if parsed is not None:
                    stories.append(parsed)

    return stories, selected_files


def clear_cache(cache_dir: Path) -> int:
    if not cache_dir.exists():
        return 0

    removed = 0
    for path in cache_dir.glob("daily-*.json"):
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def _story_to_dict(story: Story) -> dict[str, str | int]:
    item = asdict(story)
    item["published_at"] = story.published_at.isoformat()
    return item


def _story_from_dict(raw: dict[str, object]) -> Story | None:
    required = ["story_id", "title", "url", "source", "published_at"]
    if any(key not in raw for key in required):
        return None

    published_raw = raw.get("published_at")
    if not isinstance(published_raw, str):
        return None

    try:
        published_at = datetime.fromisoformat(published_raw)
    except ValueError:
        return None

    return Story(
        story_id=str(raw["story_id"]),
        title=str(raw["title"]),
        url=str(raw["url"]),
        source=str(raw["source"]),
        published_at=published_at,
        summary=str(raw.get("summary", "")),
        content=str(raw.get("content", "")),
        image_url=str(raw["image_url"]) if raw.get("image_url") else None,
        image_credit=str(raw["image_credit"]) if raw.get("image_credit") else None,
        relevance_reason=str(raw.get("relevance_reason", "")),
        word_budget=_to_int(raw.get("word_budget")),
    )


def _date_from_daily_file(path: Path) -> date | None:
    stem = path.stem
    if not stem.startswith("daily-"):
        return None

    try:
        return datetime.strptime(stem[6:], "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0

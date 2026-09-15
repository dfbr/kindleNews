from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypeAlias

import yaml

from .ai import (
    DEFAULT_RANKING_PROMPT_TEMPLATE,
    AIClient,
)
from .cache_store import clear_cache, load_cached_stories, save_daily_cache
from .config_loader import load_config
from .cost import CostTracker
from .emailer import send_epub
from .epub_writer import build_epub
from .feeds import (
    are_titles_similar,
    dedupe_stories,
    ingest_recent_stories,
    is_continuation_story,
    load_feed_urls,
    normalize_title,
)
from .fetch_article import enrich_story_content
from .models import Story, WeeklyDigest
from .state import StoryState, load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list[Any] | dict[str, Any]

_NON_STORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "reader_callout",
        re.compile(
            r"\b(tell us what you think|share your views|send us your|have your say|"
            r"reader poll|reader survey|ask us your questions|q&a callout)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "listicle",
        re.compile(
            r"\b(\d+\s+(ways|things|reasons|lessons|tips|takeaways)|top\s+\d+|best\s+\d+)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "video_content",
        re.compile(
            r"\b(video|watch|clip|livestream|live stream|youtube|tiktok|reel)\b",
            re.IGNORECASE,
        ),
    ),
)

def run(
    root: Path,
    config_path: Path | None = None,
    send_email: bool = True,
    mode: Literal["weekly", "ingest"] = "weekly",
) -> Path:
    config = load_config(root, config_path)
    config.paths.output_dir.mkdir(parents=True, exist_ok=True)
    config.paths.artifact_dir.mkdir(parents=True, exist_ok=True)
    config.paths.cache_dir.mkdir(parents=True, exist_ok=True)

    if mode == "ingest":
        feed_urls = load_feed_urls(str(config.paths.feeds_file))
        raw_stories = ingest_recent_stories(feed_urls, config.selection.lookback_days)
        _write_json(config.paths.artifact_dir / "01_raw_stories.json", raw_stories)
        cache_file = save_daily_cache(config.paths.cache_dir, raw_stories)
        _write_json(
            config.paths.artifact_dir / "01b_cache_ingest.json",
            {
                "cache_file": str(cache_file),
                "ingested_story_count": len(raw_stories),
            },
        )
        return cache_file

    cached_raw_stories, cache_files_used = load_cached_stories(
        config.paths.cache_dir,
        config.selection.lookback_days,
    )
    cache_source_used = "cache"
    if cached_raw_stories:
        raw_stories = cached_raw_stories
    else:
        cache_source_used = "live"
        feed_urls = load_feed_urls(str(config.paths.feeds_file))
        raw_stories = ingest_recent_stories(feed_urls, config.selection.lookback_days)

    _write_json(config.paths.artifact_dir / "01_raw_stories.json", raw_stories)
    _write_json(
        config.paths.artifact_dir / "01c_cache_load.json",
        {
            "cache_source_used": cache_source_used,
            "cache_story_count": len(cached_raw_stories),
            "cache_files_used": [str(path) for path in cache_files_used],
        },
    )

    deduped = dedupe_stories(raw_stories)
    _write_json(config.paths.artifact_dir / "02_deduped_stories.json", deduped)

    state = load_state(config.paths.state_file)
    fresh = _exclude_seen_with_config(deduped, state, config)
    fresh, non_story_filtered = _exclude_non_story_candidates(fresh)
    _write_json(config.paths.artifact_dir / "02b_non_story_filtered.json", non_story_filtered)

    persona = config.paths.editor_persona_file.read_text(encoding="utf-8")
    persona_overrides = _persona_publication_overrides(persona)
    story_limit = _resolve_story_limit(config, persona_overrides)
    topics_payload = yaml.safe_dump(
        yaml.safe_load(config.paths.reader_topics_file.read_text(encoding="utf-8")),
        sort_keys=False,
    )

    tracker = CostTracker(
        max_cost_usd=config.ai.max_cost_usd,
        input_cost_per_1m=config.ai.input_cost_per_1m,
        output_cost_per_1m=config.ai.output_cost_per_1m,
    )
    ranking_prompt_template = _read_prompt_template(
        root,
        config.ai.ranking_prompt_file,
        DEFAULT_RANKING_PROMPT_TEMPLATE,
    )
    ai_client = AIClient(
        config.ai,
        tracker,
        ranking_prompt_template=ranking_prompt_template,
    )
    ranking = ai_client.rank_stories(fresh, persona, topics_payload, story_limit)

    selected_ids = set(ranking.selected_ids)
    picked = [story for story in fresh if story.story_id in selected_ids]
    for story in picked:
        story.relevance_reason = ranking.reasons.get(story.story_id, "")
    _write_json(config.paths.artifact_dir / "03_picked_stories.json", picked)

    downloaded: list[Story] = []
    failures: list[dict[str, str]] = []
    for story in picked:
        enriched = enrich_story_content(story)
        if enriched is None:
            logger.warning("Failed to download story content: %s", story.url)
            failures.append(
                {
                    "story_id": story.story_id,
                    "url": story.url,
                    "reason": "download_failed",
                }
            )
            continue
        downloaded.append(enriched)
    _write_json(config.paths.artifact_dir / "04_downloaded_stories.json", downloaded)
    _write_json(config.paths.artifact_dir / "04_download_failures.json", failures)

    selected_stories: list[Story] = []
    for story in downloaded:
        story.summary = story.content.strip()
        selected_stories.append(story)

    publication_date = datetime.now(UTC).date().isoformat()
    title = f"Weekly News Digest {publication_date}"
    digest = WeeklyDigest(
        publication_date=publication_date,
        title=title,
        editor_note=ranking.editor_note,
        stories=selected_stories,
    )

    output_epub = config.paths.output_dir / f"{publication_date}.epub"
    build_epub(digest, output_epub)

    email_delivery_status = "skipped"
    email_error = ""
    if send_email:
        try:
            send_epub(config.smtp, output_epub, title)
            email_delivery_status = "sent"
        except RuntimeError as exc:
            email_delivery_status = "failed"
            email_error = str(exc)
            logger.warning("Failed to email EPUB; keeping generated file for manual use: %s", exc)

    _write_json(
        config.paths.artifact_dir / "05_digest_metadata.json",
        {
            "publication_date": publication_date,
            "title": title,
            "raw_story_count": len(raw_stories),
            "deduped_story_count": len(deduped),
            "fresh_story_count": len(fresh),
            "non_story_filtered_count": len(non_story_filtered),
            "picked_story_count": len(picked),
            "story_count": len(selected_stories),
            "email_delivery_status": email_delivery_status,
            "email_error": email_error,
            "cost_usd": round(tracker.total_cost_usd, 6),
            "selected_story_ids": ranking.selected_ids,
            "cache_source_used": cache_source_used,
            "cache_files_used": [str(path) for path in cache_files_used],
        },
    )
    _write_json(
        config.paths.artifact_dir / "06_email_delivery.json",
        {
            "email_delivery_status": email_delivery_status,
            "email_error": email_error,
        },
    )

    for story in selected_stories:
        state.used_urls.add(story.url)
        state.used_titles.add(normalize_title(story.title))
    save_state(config.paths.state_file, state)

    removed_cache_files = clear_cache(config.paths.cache_dir)
    _write_json(
        config.paths.artifact_dir / "07_cache_cleanup.json",
        {
            "removed_cache_files": removed_cache_files,
            "cache_source_used": cache_source_used,
        },
    )

    return output_epub


def _write_json(path: Path, value: list[Story] | JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, list) and value and isinstance(value[0], Story):
        payload: JsonValue = [_story_to_dict(item) for item in value]
    else:
        payload = value
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _story_to_dict(story: Story) -> dict[str, str | int]:
    item = asdict(story)
    item["published_at"] = story.published_at.isoformat()
    return item


def _exclude_seen(stories: list[Story], state: StoryState) -> list[Story]:
    return _exclude_seen_with_config(stories, state, None)


def _exclude_seen_with_config(
    stories: list[Story],
    state: StoryState,
    config: Any | None,
) -> list[Story]:
    fresh: list[Story] = []
    continuation_markers: tuple[str, ...] = ()
    threshold = 0.9
    if config is not None:
        continuation_markers = tuple(config.dedupe.continuation_markers)
        threshold = float(config.dedupe.title_similarity_threshold)

    for story in stories:
        if story.url in state.used_urls:
            continue
        normalized_title = normalize_title(story.title)
        if normalized_title in state.used_titles:
            continue

        has_similar_seen_title = any(
            are_titles_similar(normalized_title, seen_title, threshold)
            for seen_title in state.used_titles
        )

        if has_similar_seen_title and continuation_markers and is_continuation_story(
            normalized_title,
            state.used_titles,
            continuation_markers,
            threshold,
        ):
            fresh.append(story)
            continue
        if has_similar_seen_title:
            continue
        fresh.append(story)
    return fresh


def _persona_publication_overrides(persona: str) -> dict[str, Any]:
    if not persona.startswith("---"):
        return {}

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", persona, re.DOTALL)
    if not match:
        return {}

    parsed = yaml.safe_load(match.group(1))
    if not isinstance(parsed, dict):
        return {}
    publication = parsed.get("publication", {})
    return publication if isinstance(publication, dict) else {}


def _resolve_story_limit(config: Any, publication_overrides: dict[str, Any]) -> int:
    target_stories = _coerce_positive_int(
        publication_overrides.get("target_stories"),
        config.selection.max_stories,
    )
    return max(1, target_stories)


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _read_prompt_template(root: Path, path: Path, fallback: str) -> str:
    target = path if path.is_absolute() else root / path
    if not target.exists():
        logger.warning("Prompt template file not found; using fallback: %s", target)
        return fallback
    return target.read_text(encoding="utf-8")


def _exclude_non_story_candidates(stories: list[Story]) -> tuple[list[Story], list[dict[str, str]]]:
    kept: list[Story] = []
    filtered: list[dict[str, str]] = []

    for story in stories:
        text = f"{story.title} {story.summary}"
        url = story.url.lower()
        matched_reason = ""

        for reason, pattern in _NON_STORY_PATTERNS:
            if pattern.search(text):
                matched_reason = reason
                break

        if not matched_reason and ("/video" in url or "video." in url):
            matched_reason = "video_content"

        if matched_reason:
            filtered.append(
                {
                    "story_id": story.story_id,
                    "url": story.url,
                    "title": story.title,
                    "reason": matched_reason,
                }
            )
            continue

        kept.append(story)

    return kept, filtered

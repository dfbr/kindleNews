from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias

import yaml

from .ai import AIClient
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


def run(root: Path, config_path: Path | None = None, send_email: bool = True) -> Path:
    config = load_config(root, config_path)
    config.paths.output_dir.mkdir(parents=True, exist_ok=True)
    config.paths.artifact_dir.mkdir(parents=True, exist_ok=True)

    feed_urls = load_feed_urls(str(config.paths.feeds_file))
    raw_stories = ingest_recent_stories(feed_urls, config.selection.lookback_days)
    _write_json(config.paths.artifact_dir / "01_raw_stories.json", raw_stories)

    deduped = dedupe_stories(raw_stories)
    _write_json(config.paths.artifact_dir / "02_deduped_stories.json", deduped)

    state = load_state(config.paths.state_file)
    fresh = _exclude_seen_with_config(deduped, state, config)

    persona = config.paths.editor_persona_file.read_text(encoding="utf-8")
    persona_overrides = _persona_publication_overrides(persona)
    story_limit, target_pages, max_pages = _resolve_story_and_page_targets(
        config,
        persona_overrides,
    )
    topics_payload = yaml.safe_dump(
        yaml.safe_load(config.paths.reader_topics_file.read_text(encoding="utf-8")),
        sort_keys=False,
    )

    tracker = CostTracker(
        max_cost_usd=config.ai.max_cost_usd,
        input_cost_per_1m=config.ai.input_cost_per_1m,
        output_cost_per_1m=config.ai.output_cost_per_1m,
    )
    ai_client = AIClient(config.ai, tracker)
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

    total_words = target_pages * config.selection.words_per_page
    budgets = _allocate_word_budgets(downloaded, total_words)
    summarized: list[Story] = []
    summary_failures: list[dict[str, str]] = []
    for story, budget in zip(downloaded, budgets, strict=True):
        story.word_budget = budget
        try:
            story.summary = ai_client.summarize_story(story, persona, budget)
        except RuntimeError as exc:
            logger.warning("Failed to summarize story %s: %s", story.story_id, exc)
            summary_failures.append(
                {
                    "story_id": story.story_id,
                    "url": story.url,
                    "reason": "summary_failed",
                }
            )
            continue
        summarized.append(story)
    _write_json(config.paths.artifact_dir / "04_summary_failures.json", summary_failures)

    publication_date = datetime.now(UTC).date().isoformat()
    title = f"Weekly News Digest {publication_date}"
    digest = WeeklyDigest(
        publication_date=publication_date,
        title=title,
        editor_note=ranking.editor_note,
        stories=summarized,
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
            "target_pages": target_pages,
            "max_pages": max_pages,
            "raw_story_count": len(raw_stories),
            "deduped_story_count": len(deduped),
            "fresh_story_count": len(fresh),
            "picked_story_count": len(picked),
            "story_count": len(summarized),
            "summary_failure_count": len(summary_failures),
            "email_delivery_status": email_delivery_status,
            "email_error": email_error,
            "cost_usd": round(tracker.total_cost_usd, 6),
            "selected_story_ids": ranking.selected_ids,
        },
    )
    _write_json(
        config.paths.artifact_dir / "06_email_delivery.json",
        {
            "email_delivery_status": email_delivery_status,
            "email_error": email_error,
        },
    )

    for story in summarized:
        state.used_urls.add(story.url)
        state.used_titles.add(normalize_title(story.title))
    save_state(config.paths.state_file, state)

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


def _resolve_story_and_page_targets(
    config: Any,
    publication_overrides: dict[str, Any],
) -> tuple[int, int, int]:
    target_stories = _coerce_positive_int(
        publication_overrides.get("target_stories"),
        config.selection.max_stories,
    )
    max_pages = _coerce_positive_int(
        publication_overrides.get("max_pages"),
        config.selection.max_pages,
    )
    target_pages = _coerce_positive_int(publication_overrides.get("target_pages"), max_pages)

    min_pages = max(1, config.selection.min_pages)
    max_pages = max(min_pages, max_pages)
    target_pages = max(min_pages, min(target_pages, max_pages))
    story_limit = max(1, target_stories)
    return story_limit, target_pages, max_pages


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _allocate_word_budgets(stories: list[Story], total_words: int) -> list[int]:
    if not stories:
        return []

    count = len(stories)
    if total_words <= 0:
        return [0] * count

    floor = min(100, max(40, total_words // count))
    if count == 1:
        return [max(floor, total_words)]

    span = 0.30
    weights = [1.15 - span * (idx / (count - 1)) for idx in range(count)]
    total_weight = sum(weights)
    budgets = [max(floor, int(total_words * weight / total_weight)) for weight in weights]

    current = sum(budgets)
    while current > total_words:
        changed = False
        for idx in sorted(range(count), key=lambda item: budgets[item], reverse=True):
            if budgets[idx] > floor and current > total_words:
                budgets[idx] -= 1
                current -= 1
                changed = True
        if not changed:
            break

    while current < total_words:
        for idx in sorted(range(count), key=lambda item: budgets[item], reverse=True):
            if current >= total_words:
                break
            budgets[idx] += 1
            current += 1

    return budgets

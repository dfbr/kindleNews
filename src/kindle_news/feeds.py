from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import requests
from dateutil import parser as date_parser

from .models import Story

logger = logging.getLogger(__name__)

_TZINFOS = {
    "EST": timezone(timedelta(hours=-5)),
    "EDT": timezone(timedelta(hours=-4)),
    "CST": timezone(timedelta(hours=-6)),
    "CDT": timezone(timedelta(hours=-5)),
    "MST": timezone(timedelta(hours=-7)),
    "MDT": timezone(timedelta(hours=-6)),
    "PST": timezone(timedelta(hours=-8)),
    "PDT": timezone(timedelta(hours=-7)),
}

_TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k not in _TRACKING_KEYS
    ]
    cleaned = parsed._replace(query=urlencode(query), fragment="")
    return urlunparse(cleaned)


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", title.lower())).strip()


def are_titles_similar(left: str, right: str, threshold: float = 0.9) -> bool:
    left_normalized = normalize_title(left)
    right_normalized = normalize_title(right)
    if SequenceMatcher(a=left_normalized, b=right_normalized).ratio() >= threshold:
        return True

    left_tokens = left_normalized.split()
    right_tokens = right_normalized.split()
    if not left_tokens or not right_tokens:
        return False

    shorter, longer = sorted((left_tokens, right_tokens), key=len)
    shared_tokens = [token for token in shorter if token in longer]
    return len(shorter) >= 3 and len(shared_tokens) / len(shorter) >= 0.8


def strip_continuation_markers(title: str, continuation_markers: tuple[str, ...]) -> str:
    cleaned = normalize_title(title)
    normalized_markers = (normalize_title(item) for item in continuation_markers)
    for marker in sorted(normalized_markers, key=len, reverse=True):
        if marker:
            cleaned = re.sub(rf"\b{re.escape(marker)}\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def is_continuation_story(
    title: str,
    seen_titles: set[str],
    continuation_markers: tuple[str, ...],
    threshold: float,
) -> bool:
    normalized_title = normalize_title(title)
    has_marker = any(normalize_title(marker) in normalized_title for marker in continuation_markers)
    if not has_marker:
        return False

    stripped_title = strip_continuation_markers(normalized_title, continuation_markers)
    for seen_title in seen_titles:
        stripped_seen = strip_continuation_markers(seen_title, continuation_markers)
        if (
            stripped_title
            and stripped_seen
            and are_titles_similar(stripped_title, stripped_seen, threshold)
        ):
            return True
    return False


def _story_id(url: str, title: str) -> str:
    token = f"{canonicalize_url(url)}::{normalize_title(title)}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def load_feed_urls(path: str) -> list[str]:
    urls = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            value = line.strip()
            if value and not value.startswith("#"):
                urls.append(value)
    return urls


def ingest_recent_stories(feed_urls: list[str], lookback_days: int) -> list[Story]:
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    stories: list[Story] = []
    for feed_url in feed_urls:
        try:
            response = requests.get(
                feed_url,
                timeout=20,
                headers={
                    "User-Agent": "kindle-news-bot/0.1",
                    "Accept": (
                        "application/rss+xml, application/atom+xml, application/xml, "
                        "text/xml;q=0.9, */*;q=0.8"
                    ),
                },
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch feed %s: %s", feed_url, exc)
            continue

        parsed = feedparser.parse(response.content)
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
            logger.warning(
                "Failed to parse feed %s: %s",
                feed_url,
                getattr(parsed, "bozo_exception", "invalid feed"),
            )
            continue

        for entry in parsed.entries:
            raw_date = getattr(entry, "published", None) or getattr(entry, "updated", None)
            if not raw_date:
                continue
            published_at = date_parser.parse(raw_date, tzinfos=_TZINFOS)
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=UTC)
            if published_at < cutoff:
                continue

            url = getattr(entry, "link", "")
            title = getattr(entry, "title", "Untitled")
            summary = getattr(entry, "summary", "")
            if not url:
                continue

            image_url = None
            media = getattr(entry, "media_content", None)
            if media and isinstance(media, list) and media:
                image_url = media[0].get("url")

            stories.append(
                Story(
                    story_id=_story_id(url, title),
                    title=title.strip(),
                    url=canonicalize_url(url),
                    source=feed_url,
                    published_at=published_at,
                    summary=summary,
                    image_url=image_url,
                )
            )
    return stories


def dedupe_stories(stories: list[Story]) -> list[Story]:
    ordered = sorted(stories, key=lambda s: s.published_at, reverse=True)
    kept: list[Story] = []
    seen_urls: set[str] = set()
    for story in ordered:
        if story.url in seen_urls:
            continue
        if any(are_titles_similar(story.title, existing.title) for existing in kept):
            continue
        seen_urls.add(story.url)
        kept.append(story)
    return kept

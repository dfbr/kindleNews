from __future__ import annotations

import mimetypes
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import requests
from ebooklib import epub

from .models import Story, WeeklyDigest


def build_epub(digest: WeeklyDigest, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier(f"kindle-news-{digest.publication_date}")
    book.set_title(digest.title)
    book.set_language("en")

    cover_image_src: str | None = None
    cover_image_note: str | None = None
    coverage_range = _coverage_date_range(digest)
    cover_title = f"Weekly news digest {coverage_range}"

    cover_thumbnail = _build_cover_thumbnail_svg(cover_title)
    # This metadata cover is what many readers (including Kindle library view)
    # use for thumbnails, so it must include digest title/date text.
    book.set_cover("cover_thumbnail.svg", cover_thumbnail)

    cover_asset, cover_story = _select_cover_asset(digest)
    if cover_asset:
        filename, content, media_type = cover_asset
        cover_item = epub.EpubItem(
            uid="cover-page-image",
            file_name=f"images/{filename}",
            media_type=media_type,
            content=content,
        )
        book.add_item(cover_item)
        cover_image_src = f"images/{filename}"
        cover_image_note = _build_cover_image_note(cover_story)

    cover_page = epub.EpubHtml(title="Cover", file_name="front_cover.xhtml", lang="en")
    cover_page.content = _build_cover_page_html(cover_title, cover_image_src, cover_image_note)

    chapters = [cover_page]

    for idx, story in enumerate(digest.stories, start=1):
        chapter = epub.EpubHtml(title=story.title, file_name=f"story_{idx}.xhtml", lang="en")
        body = [f"<h2>{story.title}</h2>"]
        published_label = _format_published_date(story.published_at)
        source_label = _source_label(story.source or story.url)
        published_source_text = (
            f"<p><strong>Published:</strong> {published_label} in {escape(source_label)}</p>"
        )
        body.append(published_source_text)
        if story.image_url:
            asset = _download_image_asset(story.image_url, f"story_{idx}")
            if asset:
                filename, content, media_type = asset
                item = epub.EpubItem(
                    uid=filename,
                    file_name=f"images/{filename}",
                    media_type=media_type,
                    content=content,
                )
                book.add_item(item)
                body.append(f'<p><img src="images/{filename}" alt="{story.title}"/></p>')
        if story.image_credit:
            body.append(f"<p><em>Image credit: {story.image_credit}</em></p>")
        body.append(f"<p>{story.summary}</p>")
        link_label = f"Read original at {source_label}"
        body.append(f'<p><a href="{story.url}">{escape(link_label)}</a></p>')
        chapter.content = "\n".join(body)
        chapters.append(chapter)

    for chapter in chapters:
        book.add_item(chapter)

    book.toc = tuple(chapters)
    book.spine = ["nav", *chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(output_path), book, {})
    return output_path


def _pick_cover_story(digest: WeeklyDigest) -> Story | None:
    for story in digest.stories:
        if story.image_url:
            return story
    return None


def _select_cover_asset(
    digest: WeeklyDigest,
) -> tuple[tuple[str, bytes, str] | None, Story | None]:
    # Prefer a successfully downloaded image from chosen stories.
    for story in digest.stories:
        if not story.image_url:
            continue
        asset = _download_image_asset(story.image_url, "cover")
        if asset:
            return asset, story

    # If no remote image is available, fall back to a local bundled asset.
    fallback_asset = _load_local_cover_fallback("cover")
    return fallback_asset, None


def _download_image_asset(url: str, stem: str) -> tuple[str, bytes, str] | None:
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None

    suffix = _guess_suffix(url, response.headers.get("Content-Type", ""))
    media_type = mimetypes.guess_type(f"asset{suffix}")[0] or "image/jpeg"
    filename = f"{stem}{suffix}"
    return filename, response.content, media_type


def _format_published_date(value: datetime | None) -> str:
    if value is None:
        return "Unknown"
    return value.strftime("%d.%m.%Y")


def _format_cover_date(publication_date: str) -> str:
    try:
        parsed = datetime.strptime(publication_date, "%Y-%m-%d")
    except ValueError:
        return publication_date
    return parsed.strftime("%d.%m.%Y")


def _coverage_date_range(digest: WeeklyDigest) -> str:
    dates = [story.published_at for story in digest.stories if story.published_at is not None]
    if not dates:
        fallback = _format_cover_date(digest.publication_date)
        return f"{fallback} - {fallback}"

    first = min(dates).strftime("%d.%m.%Y")
    last = max(dates).strftime("%d.%m.%Y")
    return f"{first} - {last}"


def _build_cover_image_note(story: Story | None) -> str:
    if story is None:
        return "Cover image: default fallback artwork."
    image_what = story.image_credit.strip() if story.image_credit else "Lead image"
    return f"{image_what}. From: {story.title}."


def _load_local_cover_fallback(stem: str) -> tuple[str, bytes, str] | None:
    fallback_path = Path(__file__).resolve().parents[2] / "config" / "fallback_cover.svg"
    if not fallback_path.exists():
        return None

    content = fallback_path.read_bytes()
    suffix = fallback_path.suffix.lower() or ".svg"
    media_type = mimetypes.guess_type(f"asset{suffix}")[0] or "image/svg+xml"
    return f"{stem}{suffix}", content, media_type


def _source_label(source: str) -> str:
    host = urlparse(source).netloc.lower().split(":")[0]
    if not host:
        return "source"

    if host.startswith("www."):
        host = host[4:]

    overrides = {
        "theguardian.com": "The Guardian",
        "guardian.co.uk": "The Guardian",
        "economist.com": "The Economist",
        "bbc.co.uk": "BBC",
        "bbci.co.uk": "BBC",
        "nytimes.com": "The New York Times",
        "wsj.com": "The Wall Street Journal",
    }
    for suffix, label in overrides.items():
        if host == suffix or host.endswith(f".{suffix}"):
            return label

    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gov", "ac"}:
        base = parts[-3]
    elif len(parts) >= 2:
        base = parts[-2]
    else:
        base = parts[0]
    return base.replace("-", " ").title()


def _build_cover_page_html(
    title: str,
    image_src: str | None,
    image_note: str | None,
) -> str:
    escaped_title = escape(title)
    image_html = ""
    if image_src:
        note_html = ""
        if image_note:
            note_html = f'<p class="cover-image-note">{escape(image_note)}</p>'
        image_html = (
            '<div class="cover-image-wrap">'
            f'<img class="cover-image" src="{image_src}" alt="Cover image"/>'
            f"{note_html}"
            "</div>"
        )

    return (
        "<html><head><style>"
        "body { margin: 0; padding: 0; background: #ffffff; color: #111111; }"
        ".cover { min-height: 95vh; display: flex; flex-direction: column; "
        "justify-content: space-between; padding: 2rem 1.5rem 1.5rem 1.5rem; "
        "box-sizing: border-box; background: #ffffff; }"
        ".cover-title { margin: 0; font-size: 2rem; line-height: 1.2; font-weight: 700; }"
        ".cover-image-wrap { width: 100%; display: flex; flex-direction: column; "
        "justify-content: flex-end; align-items: center; gap: 0.6rem; }"
        ".cover-image { max-width: 100%; max-height: 62vh; object-fit: contain; }"
        ".cover-image-note { margin: 0; font-size: 0.9rem; line-height: 1.35; color: #333333; }"
        "</style></head><body>"
        f'<div class="cover"><h1 class="cover-title">{escaped_title}</h1>{image_html}</div>'
        "</body></html>"
    )


def _build_cover_thumbnail_svg(title: str) -> bytes:
    escaped_title = escape(title)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="2560" '
        'viewBox="0 0 1600 2560">'
        '<rect width="1600" height="2560" fill="#ffffff"/>'
        '<rect x="120" y="180" width="1360" height="2200" rx="28" fill="#f2f5f8"/>'
        '<text x="200" y="580" font-family="Georgia, serif" font-size="86" '
        'font-weight="700" fill="#121212">Weekly News Digest</text>'
        f'<text x="200" y="760" font-family="Georgia, serif" font-size="56" '
        f'font-weight="600" fill="#2a2a2a">{escaped_title}</text>'
        '<text x="200" y="2280" font-family="Georgia, serif" font-size="38" '
        'fill="#444444">Kindle News</text>'
        "</svg>"
    )
    return svg.encode("utf-8")


def _guess_suffix(url: str, content_type: str) -> str:
    path = urlparse(url).path
    candidate = Path(path).suffix.lower()
    if candidate in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return candidate
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if guessed:
        return guessed
    return ".jpg"

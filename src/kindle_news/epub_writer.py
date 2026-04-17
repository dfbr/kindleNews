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
    cover_story = _pick_cover_story(digest)
    if cover_story and cover_story.image_url:
        cover_asset = _download_image_asset(cover_story.image_url, "cover")
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

    cover_title = f"Weekly news digest {_format_cover_date(digest.publication_date)}"
    cover_page = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang="en")
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


def _build_cover_image_note(story: Story) -> str:
    image_what = story.image_credit.strip() if story.image_credit else "Lead image"
    return f"{image_what}. From: {story.title}."


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


def _guess_suffix(url: str, content_type: str) -> str:
    path = urlparse(url).path
    candidate = Path(path).suffix.lower()
    if candidate in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return candidate
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if guessed:
        return guessed
    return ".jpg"

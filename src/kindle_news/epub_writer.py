from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from ebooklib import epub

from .models import WeeklyDigest


def build_epub(digest: WeeklyDigest, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier(f"kindle-news-{digest.publication_date}")
    book.set_title(digest.title)
    book.set_language("en")

    intro = epub.EpubHtml(title="Editor's Note", file_name="intro.xhtml", lang="en")
    intro.content = f"<h1>{digest.title}</h1><p>{digest.editor_note}</p>"
    chapters = [intro]

    cover_image = _pick_cover_image(digest)
    if cover_image:
        cover_asset = _download_image_asset(cover_image, "cover")
        if cover_asset:
            filename, content, _ = cover_asset
            book.set_cover(filename, content)

    for idx, story in enumerate(digest.stories, start=1):
        chapter = epub.EpubHtml(title=story.title, file_name=f"story_{idx}.xhtml", lang="en")
        body = [f"<h2>{story.title}</h2>"]
        published_label = _format_published_date(story.published_at)
        body.append(f"<p><strong>Published:</strong> {published_label}</p>")
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
        body.append(f'<p><a href="{story.url}">Read original</a></p>')
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


def _pick_cover_image(digest: WeeklyDigest) -> str | None:
    for story in digest.stories:
        if story.image_url:
            return story.image_url
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


def _guess_suffix(url: str, content_type: str) -> str:
    path = urlparse(url).path
    candidate = Path(path).suffix.lower()
    if candidate in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return candidate
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if guessed:
        return guessed
    return ".jpg"

from __future__ import annotations

import io
import mimetypes
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont

from .models import Story, WeeklyDigest


def build_epub(digest: WeeklyDigest, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier(f"kindle-news-{digest.publication_date}")
    book.set_title(digest.title)
    book.set_language("en")

    coverage_range = _coverage_date_range(digest)
    cover_label = "Weekly news digest"

    # Build story chapters; capture the first downloaded image bytes so they
    # can be composited into the cover without a second network request.
    story_chapters: list[epub.EpubHtml] = []
    first_image_bytes: bytes | None = None
    cover_story: Story | None = None

    for idx, story in enumerate(digest.stories, start=1):
        chapter = epub.EpubHtml(title=story.title, file_name=f"story_{idx}.xhtml", lang="en")
        body = [f"<h2>{story.title}</h2>"]
        published_label = _format_published_date(story.published_at)
        source_label = _source_label(story.source or story.url)
        body.append(
            f"<p><strong>Published:</strong> {published_label} in {escape(source_label)}</p>"
        )
        if story.image_url:
            asset = _download_image_asset(story.image_url, f"story_{idx}")
            if asset:
                filename, content, media_type = asset
                if first_image_bytes is None:
                    first_image_bytes = content
                    cover_story = story
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
        story_chapters.append(chapter)

    # Build Pillow-composited cover JPEG (title + date + story photo).
    cover_jpeg = _build_cover_jpeg(cover_label, coverage_range, first_image_bytes)
    cover_item = epub.EpubItem(
        uid="cover-image",
        file_name="images/cover.jpg",
        media_type="image/jpeg",
        content=cover_jpeg,
    )
    cover_item.properties = ["cover-image"]
    book.add_item(cover_item)
    # Legacy EPUB2 meta required for Kindle library thumbnails.
    book.add_metadata(None, "meta", "", {"name": "cover", "content": "cover-image"})

    cover_image_note = _build_cover_image_note(cover_story)
    cover_page = epub.EpubHtml(title="Cover", file_name="front_cover.xhtml", lang="en")
    cover_page.content = _build_cover_page_html("images/cover.jpg", cover_image_note)

    chapters = [cover_page, *story_chapters]
    for chapter in chapters:
        book.add_item(chapter)

    book.toc = tuple(chapters)
    book.spine = ["nav", *chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(output_path), book, {})
    return output_path



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
        return ""
    image_what = story.image_credit.strip() if story.image_credit else "Lead image"
    return f"{image_what}. From: {story.title}."


def _build_cover_jpeg(
    label: str,
    date_range: str,
    story_image_bytes: bytes | None,
) -> bytes:
    """Composite a 1600×2560 cover JPEG with title text and an optional story photo."""
    W, H = 1600, 2560
    HEADER_H = 600
    FOOTER_H = 100
    IMAGE_H = H - HEADER_H - FOOTER_H
    PAD = 80
    NAVY: tuple[int, int, int] = (26, 30, 60)
    WHITE: tuple[int, int, int] = (255, 255, 255)
    LIGHT: tuple[int, int, int] = (200, 210, 230)
    PLACEHOLDER: tuple[int, int, int] = (235, 238, 242)

    canvas = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(canvas)

    # Header band
    draw.rectangle([(0, 0), (W, HEADER_H)], fill=NAVY)

    # Story photo (or light placeholder when unavailable)
    if story_image_bytes:
        try:
            story_img = Image.open(io.BytesIO(story_image_bytes)).convert("RGB")
            ratio = W / story_img.width
            new_h = max(int(story_img.height * ratio), 1)
            story_img = story_img.resize((W, new_h), Image.Resampling.LANCZOS)
            if story_img.height >= IMAGE_H:
                top = (story_img.height - IMAGE_H) // 2
                story_img = story_img.crop((0, top, W, top + IMAGE_H))
            canvas.paste(story_img, (0, HEADER_H))
        except Exception:
            draw.rectangle([(0, HEADER_H), (W, H - FOOTER_H)], fill=PLACEHOLDER)
    else:
        draw.rectangle([(0, HEADER_H), (W, H - FOOTER_H)], fill=PLACEHOLDER)

    # Footer band
    draw.rectangle([(0, H - FOOTER_H), (W, H)], fill=NAVY)

    # Fonts
    title_font = _load_cover_font(size=108, bold=True)
    date_font = _load_cover_font(size=72, bold=False)
    footer_font = _load_cover_font(size=46, bold=False)

    # Vertically centre title + date range in the header band
    title_bb = draw.textbbox((0, 0), label, font=title_font)
    date_bb = draw.textbbox((0, 0), date_range, font=date_font)
    title_h = title_bb[3] - title_bb[1]
    date_h = date_bb[3] - date_bb[1]
    gap = 28
    block_h = title_h + gap + date_h
    title_y = (HEADER_H - block_h) // 2
    date_y = title_y + title_h + gap

    draw.text((PAD, title_y), label, font=title_font, fill=WHITE)
    draw.text((PAD, date_y), date_range, font=date_font, fill=LIGHT)

    # Footer label
    draw.text((PAD, H - FOOTER_H + 27), "Kindle News", font=footer_font, fill=LIGHT)

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _load_cover_font(size: int, bold: bool = False) -> Any:
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    )
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default(size=size)


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


def _build_cover_page_html(image_src: str, image_note: str) -> str:
    """Full-screen cover page: the composited JPEG fills the screen, note below."""
    note_html = ""
    if image_note:
        note_html = (
            f'<p style="margin:0.6rem 1rem;font-size:0.78em;'
            f'color:#555;line-height:1.35;">{escape(image_note)}</p>'
        )
    return (
        "<html><head><style>"
        "body{margin:0;padding:0;background:#ffffff;}"
        "img.cover{width:100%;display:block;}"
        "</style></head><body>"
        f'<img class="cover" src="{image_src}" alt="Cover"/>'
        f"{note_html}"
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

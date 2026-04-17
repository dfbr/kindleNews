from __future__ import annotations

import datetime
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import requests
from PIL import Image

from kindle_news.epub_writer import build_epub
from kindle_news.models import Story, WeeklyDigest


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "image/jpeg") -> None:
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


def _make_jpeg_bytes() -> bytes:
    """Minimal valid JPEG for Pillow to open during cover composition."""
    img = Image.new("RGB", (100, 75), color=(80, 120, 180))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_digest(with_image: bool = True) -> WeeklyDigest:
    return WeeklyDigest(
        publication_date="2026-04-17",
        title="Weekly News Digest 2026-04-17",
        editor_note="Editor note",
        stories=[
            Story(
                story_id="1",
                title="Story One",
                url="https://example.com/story",
                source="feed",
                published_at=datetime.datetime(2026, 4, 17),
                summary="Summary text",
                image_url="https://example.com/image.jpg" if with_image else None,
                image_credit="Photographer" if with_image else None,
            )
        ],
    )


def test_cover_jpg_always_present(monkeypatch, tmp_path: Path) -> None:
    """cover.jpg is always written (Pillow-composited) as the EPUB cover-image."""
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **kw: FakeResponse(_make_jpeg_bytes()),
    )
    output_path = tmp_path / "digest.epub"
    build_epub(_make_digest(), output_path)

    with ZipFile(output_path) as archive:
        names = archive.namelist()
    assert any(name.endswith("images/cover.jpg") for name in names)


def test_story_image_not_duplicated_as_cover(monkeypatch, tmp_path: Path) -> None:
    """story_1.jpg is a regular story asset; cover.jpg is the dedicated cover-image."""
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **kw: FakeResponse(_make_jpeg_bytes()),
    )
    output_path = tmp_path / "digest.epub"
    build_epub(_make_digest(), output_path)

    with ZipFile(output_path) as archive:
        names = archive.namelist()
        opf_text = archive.read(next(n for n in names if n.endswith(".opf"))).decode("utf-8")

    root = ET.fromstring(opf_text)
    ns = {"opf": "http://www.idpf.org/2007/opf"}
    manifest = root.find("opf:manifest", ns)
    assert manifest is not None

    # story_1.jpg must not carry cover-image property
    story_items = [
        item
        for item in manifest.findall("opf:item", ns)
        if item.get("href", "").endswith("story_1.jpg")
    ]
    assert story_items, "story_1.jpg should be in the manifest"
    for item in story_items:
        assert "cover-image" not in (item.get("properties") or "")

    # cover.jpg must be the sole cover-image
    cover_items = [
        item
        for item in manifest.findall("opf:item", ns)
        if "cover-image" in (item.get("properties") or "")
    ]
    assert len(cover_items) == 1
    assert cover_items[0].get("href") == "images/cover.jpg"


def test_cover_jpg_generated_even_without_story_images(monkeypatch, tmp_path: Path) -> None:
    """Pillow generates a text-only cover.jpg when no story image downloads succeed."""

    def _fail_get(*args: object, **kwargs: object) -> None:
        raise requests.RequestException("download failed")

    monkeypatch.setattr("requests.get", _fail_get)
    output_path = tmp_path / "digest-noimg.epub"
    build_epub(_make_digest(with_image=True), output_path)

    with ZipFile(output_path) as archive:
        names = archive.namelist()
        assert any(name.endswith("images/cover.jpg") for name in names)
        cover_bytes = archive.read(next(n for n in names if n.endswith("images/cover.jpg")))

    img = Image.open(io.BytesIO(cover_bytes))
    assert img.format == "JPEG"
    assert img.size == (1600, 2560)

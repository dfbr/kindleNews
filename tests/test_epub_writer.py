from pathlib import Path
from zipfile import ZipFile

import requests

from kindle_news.epub_writer import build_epub
from kindle_news.models import Story, WeeklyDigest


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "image/jpeg") -> None:
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


def test_build_epub_embeds_images(monkeypatch, tmp_path: Path) -> None:
    digest = WeeklyDigest(
        publication_date="2026-04-17",
        title="Weekly News Digest 2026-04-17",
        editor_note="Editor note",
        stories=[
            Story(
                story_id="1",
                title="Story One",
                url="https://example.com/story",
                source="feed",
                published_at=__import__("datetime").datetime(2026, 4, 17),
                summary="Summary text",
                image_url="https://example.com/image.jpg",
                image_credit="Photographer",
            )
        ],
    )

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse(b"img-bytes"))
    output_path = tmp_path / "digest.epub"
    build_epub(digest, output_path)

    with ZipFile(output_path) as archive:
        names = archive.namelist()
        assert any(name.endswith("images/story_1.jpg") for name in names)
        assert any(name.endswith("cover.jpg") for name in names)


def test_build_epub_uses_fallback_cover_when_story_images_fail(
    monkeypatch,
    tmp_path: Path,
) -> None:
    digest = WeeklyDigest(
        publication_date="2026-04-17",
        title="Weekly News Digest 2026-04-17",
        editor_note="Editor note",
        stories=[
            Story(
                story_id="1",
                title="Story One",
                url="https://example.com/story",
                source="feed",
                published_at=__import__("datetime").datetime(2026, 4, 17),
                summary="Summary text",
                image_url="https://example.com/image.jpg",
            )
        ],
    )

    def _fail_get(*args, **kwargs):
        raise requests.RequestException("download failed")

    monkeypatch.setattr("requests.get", _fail_get)
    output_path = tmp_path / "digest-fallback.epub"
    build_epub(digest, output_path)

    with ZipFile(output_path) as archive:
        names = archive.namelist()
        assert any(name.endswith("images/cover.svg") for name in names)


def test_build_epub_sets_text_thumbnail_cover(monkeypatch, tmp_path: Path) -> None:
    digest = WeeklyDigest(
        publication_date="2026-04-17",
        title="Weekly News Digest 2026-04-17",
        editor_note="Editor note",
        stories=[
            Story(
                story_id="1",
                title="Story One",
                url="https://example.com/story",
                source="feed",
                published_at=__import__("datetime").datetime(2026, 4, 17),
                summary="Summary text",
                image_url="https://example.com/image.jpg",
            )
        ],
    )

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse(b"img-bytes"))
    output_path = tmp_path / "digest-thumbnail.epub"
    build_epub(digest, output_path)

    with ZipFile(output_path) as archive:
        thumbnail_name = next(
            name for name in archive.namelist() if name.endswith("cover_thumbnail.svg")
        )
        thumbnail_svg = archive.read(thumbnail_name).decode("utf-8")
        assert "Weekly News Digest" in thumbnail_svg
        assert "17.04.2026 - 17.04.2026" in thumbnail_svg

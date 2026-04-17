from pathlib import Path
from zipfile import ZipFile

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

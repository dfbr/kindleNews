from datetime import UTC, datetime

from kindle_news.fetch_article import enrich_story_content
from kindle_news.models import Story


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_enrich_story_content_retries(monkeypatch) -> None:
    attempts = {"count": 0}

    def fake_get(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("temporary")
        return FakeResponse(
            "<html><head><meta property=\"og:image\" "
            "content=\"https://example.com/image.jpg\" /></head>"
            "<body><p>This is a sufficiently long paragraph for extraction "
            "with more than forty characters.</p></body></html>"
        )

    monkeypatch.setattr("requests.get", fake_get)
    story = Story(
        story_id="1",
        title="Title",
        url="https://example.com/story",
        source="feed",
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
    )

    enriched = enrich_story_content(story)

    assert enriched is not None
    assert attempts["count"] == 2
    assert enriched.image_url == "https://example.com/image.jpg"

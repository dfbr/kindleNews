import logging

from kindle_news.feeds import ingest_recent_stories


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def test_ingest_recent_stories_logs_feed_fetch_failures(monkeypatch, caplog) -> None:
    def fake_get(*args, **kwargs):
        raise __import__("requests").RequestException("boom")

    monkeypatch.setattr("requests.get", fake_get)

    with caplog.at_level(logging.WARNING):
        stories = ingest_recent_stories(["https://example.com/feed.xml"], 7)

    assert stories == []
    assert "Failed to fetch feed" in caplog.text
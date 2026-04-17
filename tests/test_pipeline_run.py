from datetime import UTC, datetime
from pathlib import Path

from kindle_news.models import Story
from kindle_news.pipeline import run


def test_run_generates_dated_output_and_download_failure_artifact(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text(
        """
smtp:
  host: smtp.example.com
  port: 587
  username: user
  password_env_var: SMTP_PASSWORD
  from_address: from@example.com
  to_address: to@example.com
""",
        encoding="utf-8",
    )
    (config_dir / "feeds.txt").write_text("https://example.com/feed.xml\n", encoding="utf-8")
    (config_dir / "editor_persona.md").write_text("Editor persona", encoding="utf-8")
    (config_dir / "reader_topics.yaml").write_text("interests: []\n", encoding="utf-8")

    story = Story(
        story_id="story-1",
        title="A story",
        url="https://example.com/story",
        source="feed",
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
        summary="Feed summary",
    )

    class FakeRanking:
        selected_ids = ["story-1"]
        reasons = {"story-1": "Relevant"}
        editor_note = "Note"

    class FakeAIClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def rank_stories(self, *args, **kwargs):
            return FakeRanking()

        def summarize_story(self, story: Story, persona: str, word_budget: int) -> str:
            return f"Summary for {story.story_id}"

    monkeypatch.setattr("kindle_news.pipeline.load_feed_urls", lambda path: ["https://example.com/feed.xml"])
    monkeypatch.setattr("kindle_news.pipeline.ingest_recent_stories", lambda urls, days: [story])
    monkeypatch.setattr("kindle_news.pipeline.AIClient", FakeAIClient)
    monkeypatch.setattr("kindle_news.pipeline.enrich_story_content", lambda item: None)

    def fake_build_epub(digest, output_path: Path) -> Path:
        output_path.write_bytes(b"epub")
        return output_path

    monkeypatch.setattr("kindle_news.pipeline.build_epub", fake_build_epub)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 17, 5, 0, tzinfo=UTC)

    monkeypatch.setattr("kindle_news.pipeline.datetime", FakeDatetime)

    output = run(root=root, send_email=False)

    assert output.name == "2026-04-17.epub"
    assert (root / "output" / "artifacts" / "04_download_failures.json").exists()

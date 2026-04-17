import json
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


def test_run_continues_when_summary_fails(monkeypatch, tmp_path: Path) -> None:
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
        content=" ".join(["word"] * 250),
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
            raise RuntimeError("invalid AI summary response")

    monkeypatch.setattr("kindle_news.pipeline.load_feed_urls", lambda path: ["https://example.com/feed.xml"])
    monkeypatch.setattr("kindle_news.pipeline.ingest_recent_stories", lambda urls, days: [story])
    monkeypatch.setattr("kindle_news.pipeline.AIClient", FakeAIClient)
    monkeypatch.setattr("kindle_news.pipeline.enrich_story_content", lambda item: item)

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
    assert (root / "output" / "artifacts" / "04_summary_failures.json").exists()


def test_run_continues_when_email_fails(monkeypatch, tmp_path: Path) -> None:
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
        content=" ".join(["word"] * 250),
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
            return "Summary"

    monkeypatch.setattr("kindle_news.pipeline.load_feed_urls", lambda path: ["https://example.com/feed.xml"])
    monkeypatch.setattr("kindle_news.pipeline.ingest_recent_stories", lambda urls, days: [story])
    monkeypatch.setattr("kindle_news.pipeline.AIClient", FakeAIClient)
    monkeypatch.setattr("kindle_news.pipeline.enrich_story_content", lambda item: item)
    monkeypatch.setattr(
        "kindle_news.pipeline.send_epub",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("smtp failed")),
    )

    def fake_build_epub(digest, output_path: Path) -> Path:
        output_path.write_bytes(b"epub")
        return output_path

    monkeypatch.setattr("kindle_news.pipeline.build_epub", fake_build_epub)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 17, 5, 0, tzinfo=UTC)

    monkeypatch.setattr("kindle_news.pipeline.datetime", FakeDatetime)

    output = run(root=root, send_email=True)

    assert output.name == "2026-04-17.epub"
    email_artifact = root / "output" / "artifacts" / "06_email_delivery.json"
    assert email_artifact.exists()
    payload = json.loads(email_artifact.read_text(encoding="utf-8"))
    assert payload["email_delivery_status"] == "failed"


def test_run_filters_non_story_candidates_before_ranking(monkeypatch, tmp_path: Path) -> None:
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

    good_story = Story(
        story_id="good-1",
        title="UK competition regulator publishes platform market findings",
        url="https://example.com/news",
        source="feed",
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
        summary="Regulator report analyzes incentives and policy options.",
        content=" ".join(["word"] * 250),
    )
    listicle_story = Story(
        story_id="listicle-1",
        title="10 ways to optimize your startup pitch",
        url="https://example.com/listicle",
        source="feed",
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
        summary="Practical tips list.",
        content=" ".join(["word"] * 250),
    )
    video_story = Story(
        story_id="video-1",
        title="Watch: live interview with the minister",
        url="https://example.com/video/interview",
        source="feed",
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
        summary="Video interview.",
        content=" ".join(["word"] * 250),
    )

    seen_ids: list[str] = []

    class FakeRanking:
        selected_ids: list[str]
        reasons: dict[str, str]
        editor_note = "Note"

        def __init__(self, ids: list[str]) -> None:
            self.selected_ids = ids
            self.reasons = {item: "Relevant" for item in ids}

    class FakeAIClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def rank_stories(self, stories, *args, **kwargs):
            seen_ids.extend([story.story_id for story in stories])
            return FakeRanking([story.story_id for story in stories])

        def summarize_story(self, story: Story, persona: str, word_budget: int) -> str:
            return "Summary"

    monkeypatch.setattr("kindle_news.pipeline.load_feed_urls", lambda path: ["https://example.com/feed.xml"])
    monkeypatch.setattr(
        "kindle_news.pipeline.ingest_recent_stories",
        lambda urls, days: [good_story, listicle_story, video_story],
    )
    monkeypatch.setattr("kindle_news.pipeline.AIClient", FakeAIClient)
    monkeypatch.setattr("kindle_news.pipeline.enrich_story_content", lambda item: item)

    def fake_build_epub(digest, output_path: Path) -> Path:
        output_path.write_bytes(b"epub")
        return output_path

    monkeypatch.setattr("kindle_news.pipeline.build_epub", fake_build_epub)

    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 17, 5, 0, tzinfo=UTC)

    monkeypatch.setattr("kindle_news.pipeline.datetime", FakeDatetime)

    run(root=root, send_email=False)

    assert seen_ids == ["good-1"]
    filtered_artifact = root / "output" / "artifacts" / "02b_non_story_filtered.json"
    assert filtered_artifact.exists()
    filtered_payload = json.loads(filtered_artifact.read_text(encoding="utf-8"))
    assert [item["story_id"] for item in filtered_payload] == ["listicle-1", "video-1"]

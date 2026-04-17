import json

from kindle_news.ai import AIClient
from kindle_news.config import AIConfig
from kindle_news.cost import CostTracker
from kindle_news.models import Story


class FakeUsage:
    def __init__(self) -> None:
        self.input_tokens = 10
        self.output_tokens = 10


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.output_text = text
        self.usage = FakeUsage()


class FakeResponsesAPI:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls = 0

    def create(self, **kwargs):
        text = self.outputs[self.calls]
        self.calls += 1
        return FakeResponse(text)


class FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.responses = FakeResponsesAPI(outputs)


def test_rank_stories_repairs_invalid_json() -> None:
    tracker = CostTracker(max_cost_usd=1.0, input_cost_per_1m=0.1, output_cost_per_1m=0.1)
    client = AIClient(AIConfig(allow_heuristic_fallback=False, max_retries=0), tracker)
    client._client = FakeClient([
        "not json",
        json.dumps({"selected": [{"story_id": "1", "reason": "relevant"}], "editor_note": "note"}),
    ])
    stories = [
        Story(
            story_id="1",
            title="Story",
            url="https://example.com",
            source="feed",
            published_at=__import__("datetime").datetime(2026, 4, 17),
            summary="summary",
        )
    ]

    result = client.rank_stories(stories, "persona", "topics", 5)

    assert result.selected_ids == ["1"]
    assert result.editor_note == "note"


def test_summarize_story_repairs_invalid_schema() -> None:
    tracker = CostTracker(max_cost_usd=1.0, input_cost_per_1m=0.1, output_cost_per_1m=0.1)
    client = AIClient(AIConfig(allow_heuristic_fallback=False, max_retries=0), tracker)
    client._client = FakeClient([
        json.dumps({"summary": ["wrong"]}),
        json.dumps({"summary": "Repaired summary"}),
    ])
    story = Story(
        story_id="1",
        title="Story",
        url="https://example.com",
        source="feed",
        published_at=__import__("datetime").datetime(2026, 4, 17),
        content="Longer content body for summarization",
    )

    result = client.summarize_story(story, "persona", 120)

    assert result == "Repaired summary"


def test_summarize_story_falls_back_on_unparseable_response() -> None:
    tracker = CostTracker(max_cost_usd=1.0, input_cost_per_1m=0.1, output_cost_per_1m=0.1)
    client = AIClient(AIConfig(allow_heuristic_fallback=True, max_retries=0), tracker)
    client._client = FakeClient(["", "still not json"])
    story = Story(
        story_id="1",
        title="Story",
        url="https://example.com",
        source="feed",
        published_at=__import__("datetime").datetime(2026, 4, 17),
        content=" ".join(["word"] * 250),
    )

    result = client.summarize_story(story, "persona", 120)

    assert result
    assert isinstance(result, str)


def test_heuristic_rank_respects_negative_topic_scores() -> None:
    tracker = CostTracker(max_cost_usd=1.0, input_cost_per_1m=0.1, output_cost_per_1m=0.1)
    client = AIClient(AIConfig(allow_heuristic_fallback=True, max_retries=0), tracker)
    stories = [
        Story(
            story_id="sports-1",
            title="Sports roundup: championship highlights",
            url="https://example.com/sports",
            source="feed",
            published_at=__import__("datetime").datetime(2026, 4, 17),
            summary="A major sports tournament and results update.",
        ),
        Story(
            story_id="climate-1",
            title="Climate policy update from Brussels",
            url="https://example.com/climate",
            source="feed",
            published_at=__import__("datetime").datetime(2026, 4, 17),
            summary="New climate regulations and environmental policy milestones.",
        ),
    ]

    topics_payload = """
interests:
  - topic: climate
    score: 70
  - topic: sports
    score: -20
"""

    result = client.rank_stories(stories, "persona", topics_payload, 2)

    assert result.selected_ids[0] == "climate-1"

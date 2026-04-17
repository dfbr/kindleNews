from pathlib import Path

from kindle_news.config import default_config
from kindle_news.pipeline import (
    _allocate_word_budgets,
    _persona_publication_overrides,
    _resolve_story_and_page_targets,
)


def test_persona_publication_overrides_parsed() -> None:
    persona = """---
publication:
  max_pages: 18
  target_pages: 12
  target_stories: 9
---
Editor notes here.
"""
    overrides = _persona_publication_overrides(persona)
    assert overrides == {"max_pages": 18, "target_pages": 12, "target_stories": 9}


def test_resolve_story_and_page_targets_clamps_target_pages() -> None:
    config = default_config(Path("."))
    config.selection.min_pages = 10
    config.selection.max_pages = 20
    config.selection.max_stories = 15

    story_limit, target_pages, max_pages = _resolve_story_and_page_targets(
        config,
        {"target_stories": 8, "target_pages": 25, "max_pages": 14},
    )

    assert story_limit == 8
    assert max_pages == 14
    assert target_pages == 14


def test_allocate_word_budgets_total_and_varied() -> None:
    stories = [object() for _ in range(5)]
    budgets = _allocate_word_budgets(stories, total_words=2500)

    assert len(budgets) == 5
    assert sum(budgets) == 2500
    assert len(set(budgets)) > 1
    assert min(budgets) >= 100

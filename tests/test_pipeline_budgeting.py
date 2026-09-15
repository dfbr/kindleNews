from pathlib import Path

from kindle_news.config import default_config
from kindle_news.pipeline import (
    _persona_publication_overrides,
    _resolve_story_limit,
)


def test_persona_publication_overrides_parsed() -> None:
    persona = """---
publication:
  target_stories: 9
---
Editor notes here.
"""
    overrides = _persona_publication_overrides(persona)
    assert overrides == {"target_stories": 9}


def test_resolve_story_limit_uses_persona_override() -> None:
    config = default_config(Path("."))
    config.selection.max_stories = 15

    story_limit = _resolve_story_limit(config, {"target_stories": 8})

    assert story_limit == 8

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .feeds import normalize_title


@dataclass(slots=True)
class StoryState:
    used_urls: set[str] = field(default_factory=set)
    used_titles: set[str] = field(default_factory=set)


def load_state(path: Path) -> StoryState:
    if not path.exists():
        return StoryState()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return StoryState(
        used_urls=set(payload.get("used_urls", [])),
        used_titles={normalize_title(title) for title in payload.get("used_titles", [])},
    )


def save_state(path: Path, state: StoryState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "used_urls": sorted(state.used_urls),
        "used_titles": sorted(normalize_title(title) for title in state.used_titles),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

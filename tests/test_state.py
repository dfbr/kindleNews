from pathlib import Path

from kindle_news.state import StoryState, load_state, save_state


def test_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = StoryState(used_urls={"https://a"}, used_titles={"title"})
    save_state(path, state)
    loaded = load_state(path)
    assert loaded.used_urls == {"https://a"}
    assert loaded.used_titles == {"title"}

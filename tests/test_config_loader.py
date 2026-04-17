from pathlib import Path

from kindle_news.config_loader import load_config


def test_load_config_defaults(tmp_path: Path) -> None:
    app = load_config(tmp_path)
    assert app.paths.feeds_file == tmp_path / "config" / "feeds.txt"
    assert app.selection.max_stories == 15


def test_load_config_override(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    cfg = config_dir / "config.yaml"
    cfg.write_text(
        "selection:\n  max_stories: 7\npaths:\n  feeds_file: config/custom_feeds.txt\n",
        encoding="utf-8",
    )

    app = load_config(tmp_path)
    assert app.selection.max_stories == 7
    assert str(app.paths.feeds_file) == "config/custom_feeds.txt"

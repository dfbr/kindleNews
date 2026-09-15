from pathlib import Path

from kindle_news.config_loader import load_config


def test_load_config_defaults(tmp_path: Path) -> None:
    app = load_config(tmp_path)
    assert app.paths.feeds_file == tmp_path / "config" / "feeds.txt"
    assert app.paths.cache_dir == tmp_path / "output" / "cache"
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


def test_load_config_override_cache_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    cfg = config_dir / "config.yaml"
    cfg.write_text("paths:\n  cache_dir: output/custom_cache\n", encoding="utf-8")

    app = load_config(tmp_path)
    assert str(app.paths.cache_dir) == "output/custom_cache"


def test_load_config_ignores_removed_summary_prompt_setting(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    cfg = config_dir / "config.yaml"
    cfg.write_text(
        "ai:\n  summary_prompt_file: config/prompts/summary_prompt.txt\n",
        encoding="utf-8",
    )

    app = load_config(tmp_path)

    assert str(app.ai.ranking_prompt_file) == "config/prompts/ranking_prompt.txt"


def test_load_config_ignores_removed_page_budget_settings(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    cfg = config_dir / "config.yaml"
    cfg.write_text(
        "selection:\n  min_pages: 10\n  max_pages: 20\n  words_per_page: 500\n",
        encoding="utf-8",
    )

    app = load_config(tmp_path)

    assert app.selection.max_stories == 15

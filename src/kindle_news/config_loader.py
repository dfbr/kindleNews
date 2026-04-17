from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .config import (
    AIConfig,
    AppConfig,
    DedupeConfig,
    SelectionConfig,
    SMTPConfig,
    default_config,
)


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(root: Path, config_path: Path | None = None) -> AppConfig:
    app = default_config(root)
    target = config_path or (root / "config" / "config.yaml")
    if not target.exists():
        return app

    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    base = {
        "timezone": app.timezone,
        "publication_hour_gmt": app.publication_hour_gmt,
        "paths": {
            "feeds_file": str(app.paths.feeds_file),
            "editor_persona_file": str(app.paths.editor_persona_file),
            "reader_topics_file": str(app.paths.reader_topics_file),
            "state_file": str(app.paths.state_file),
            "output_dir": str(app.paths.output_dir),
            "artifact_dir": str(app.paths.artifact_dir),
            "cache_dir": str(app.paths.cache_dir),
        },
        "selection": asdict(app.selection),
        "dedupe": asdict(app.dedupe),
        "ai": asdict(app.ai),
        "smtp": asdict(app.smtp),
    }
    merged = _merge_dict(base, payload)

    app.timezone = str(merged["timezone"])
    app.publication_hour_gmt = int(merged["publication_hour_gmt"])

    paths = merged["paths"]
    app.paths.feeds_file = Path(paths["feeds_file"])
    app.paths.editor_persona_file = Path(paths["editor_persona_file"])
    app.paths.reader_topics_file = Path(paths["reader_topics_file"])
    app.paths.state_file = Path(paths["state_file"])
    app.paths.output_dir = Path(paths["output_dir"])
    app.paths.artifact_dir = Path(paths["artifact_dir"])
    app.paths.cache_dir = Path(paths["cache_dir"])

    app.selection = SelectionConfig(**merged["selection"])
    app.dedupe = DedupeConfig(**merged["dedupe"])
    app.ai = AIConfig(**merged["ai"])
    app.ai.ranking_prompt_file = Path(merged["ai"]["ranking_prompt_file"])
    app.ai.summary_prompt_file = Path(merged["ai"]["summary_prompt_file"])
    app.smtp = SMTPConfig(**merged["smtp"])
    return app

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PathsConfig:
    feeds_file: Path
    editor_persona_file: Path
    reader_topics_file: Path
    state_file: Path
    output_dir: Path
    artifact_dir: Path
    cache_dir: Path


@dataclass(slots=True)
class SelectionConfig:
    lookback_days: int = 7
    max_stories: int = 15
    min_pages: int = 10
    max_pages: int = 20
    words_per_page: int = 500


@dataclass(slots=True)
class DedupeConfig:
    title_similarity_threshold: float = 0.9
    continuation_markers: tuple[str, ...] = (
        "update",
        "updated",
        "live",
        "latest",
        "briefing",
        "what next",
        "analysis",
    )


@dataclass(slots=True)
class AIConfig:
    provider: str = "openai"
    model: str = "gpt-4.1-mini"
    max_input_tokens: int = 200000
    max_output_tokens: int = 2000
    max_cost_usd: float = 1.0
    input_cost_per_1m: float = 0.4
    output_cost_per_1m: float = 1.6
    allow_heuristic_fallback: bool = True
    max_retries: int = 2
    repair_invalid_json_once: bool = True
    ranking_prompt_file: Path = Path("config/prompts/ranking_prompt.txt")
    summary_prompt_file: Path = Path("config/prompts/summary_prompt.txt")


@dataclass(slots=True)
class SMTPConfig:
    host: str
    port: int
    username: str
    password_env_var: str
    from_address: str
    to_address: str
    use_tls: bool = True
    max_retries: int = 2
    timeout_seconds: int = 30


@dataclass(slots=True)
class AppConfig:
    timezone: str
    publication_hour_gmt: int
    paths: PathsConfig
    selection: SelectionConfig
    dedupe: DedupeConfig
    ai: AIConfig
    smtp: SMTPConfig


def default_config(root: Path) -> AppConfig:
    config_dir = root / "config"
    output_dir = root / "output"
    artifact_dir = output_dir / "artifacts"
    return AppConfig(
        timezone="GMT",
        publication_hour_gmt=5,
        paths=PathsConfig(
            feeds_file=config_dir / "feeds.txt",
            editor_persona_file=config_dir / "editor_persona.md",
            reader_topics_file=config_dir / "reader_topics.yaml",
            state_file=config_dir / "state.json",
            output_dir=output_dir,
            artifact_dir=artifact_dir,
            cache_dir=output_dir / "cache",
        ),
        selection=SelectionConfig(),
        dedupe=DedupeConfig(),
        ai=AIConfig(),
        smtp=SMTPConfig(
            host="",
            port=587,
            username="",
            password_env_var="SMTP_PASSWORD",
            from_address="",
            to_address="",
            use_tls=True,
        ),
    )

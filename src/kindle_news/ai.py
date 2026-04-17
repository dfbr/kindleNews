from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from .config import AIConfig
from .cost import CostTracker
from .models import Story
from .retry import retry_call


@dataclass(slots=True)
class RankingResult:
    selected_ids: list[str]
    reasons: dict[str, str]
    editor_note: str


class AIClient:
    def __init__(self, config: AIConfig, cost_tracker: CostTracker) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        api_key = os.getenv("OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key) if api_key else None

    def _require_client(self) -> OpenAI:
        if not self._client:
            raise RuntimeError("OPENAI_API_KEY is required for AI processing")
        return self._client

    def rank_stories(
        self,
        stories: list[Story],
        persona: str,
        topics_payload: str,
        max_stories: int,
    ) -> RankingResult:
        if not stories:
            return RankingResult(selected_ids=[], reasons={}, editor_note="")

        if not self._client and self.config.allow_heuristic_fallback:
            return self._heuristic_rank(stories, topics_payload, max_stories)

        self._require_client()
        compact = [
            {
                "story_id": s.story_id,
                "title": s.title,
                "url": s.url,
                "summary": s.summary[:500],
            }
            for s in stories
        ]
        prompt = (
            "You are ranking stories for a weekly digest. Return JSON only matching this schema: "
            '{"selected": [{"story_id": "string", "reason": "string"}], "editor_note": "string"}. '
            f"Select up to {max_stories} stories.\n"
            f"Persona:\n{persona}\n\nReader topics:\n{topics_payload}\n\n"
            f"Stories:\n{json.dumps(compact)}"
        )
        parsed = self._json_response(
            prompt,
            validator=self._validate_ranking_payload,
            repair_prompt=(
                "Your previous response was invalid. Return valid JSON only matching "
                'this schema: {"selected": [{"story_id": "string", "reason": '
                '"string"}], "editor_note": "string"}.'
            ),
        )
        selected = parsed.get("selected", [])
        valid_selected = [
            entry
            for entry in selected
            if isinstance(entry, dict) and entry.get("story_id")
        ]
        selected_ids = [str(entry["story_id"]) for entry in valid_selected]
        reasons = {
            str(entry["story_id"]): str(entry.get("reason", ""))
            for entry in valid_selected
        }
        editor_note = str(parsed.get("editor_note", ""))
        return RankingResult(
            selected_ids=selected_ids[:max_stories],
            reasons=reasons,
            editor_note=editor_note,
        )

    def summarize_story(self, story: Story, persona: str, word_budget: int) -> str:
        if not self._client and self.config.allow_heuristic_fallback:
            return self._heuristic_summary(story, word_budget)

        self._require_client()
        prompt = (
            "Return JSON only matching this schema: {\"summary\": \"string\"}. "
            f"Write around {word_budget} words.\nPersona:\n{persona}\n\n"
            f"Title: {story.title}\nURL: {story.url}\nContent:\n{story.content[:12000]}"
        )
        parsed = self._json_response(
            prompt,
            validator=self._validate_summary_payload,
            repair_prompt=(
                "Your previous response was invalid. Return valid JSON only matching "
                'this schema: {"summary": "string"}.'
            ),
        )
        return str(parsed.get("summary", "")).strip()

    def _json_response(
        self,
        prompt: str,
        *,
        validator: Callable[[dict[str, Any]], None],
        repair_prompt: str,
    ) -> dict[str, Any]:
        client = self._require_client()
        raw = self._response_text(client, prompt)
        try:
            return self._parse_json_payload(raw, validator)
        except (JSONDecodeError, ValueError):
            if not self.config.repair_invalid_json_once:
                raise
            repair_input = f"{repair_prompt}\n\nPrevious response:\n{raw}"
            repaired = self._response_text(client, repair_input)
            return self._parse_json_payload(repaired, validator)

    def _response_text(self, client: OpenAI, prompt: str) -> str:
        def _create() -> Any:
            return client.responses.create(
                model=self.config.model,
                input=prompt,
                max_output_tokens=self.config.max_output_tokens,
            )

        response = retry_call(
            _create,
            retries=self.config.max_retries,
            retry_on=(APIConnectionError, APITimeoutError, RateLimitError),
        )
        usage = response.usage
        if usage:
            self.cost_tracker.add_usage(usage.input_tokens, usage.output_tokens)
            self.cost_tracker.ensure_under_budget()
        return response.output_text.strip()

    def _parse_json_payload(
        self,
        raw: str,
        validator: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("AI response must be a JSON object")
        validator(parsed)
        return parsed

    def _validate_ranking_payload(self, parsed: dict[str, Any]) -> None:
        selected = parsed.get("selected")
        editor_note = parsed.get("editor_note")

        if not isinstance(selected, list):
            raise ValueError("AI ranking payload must include a selected list")
        if not isinstance(editor_note, str):
            raise ValueError("AI ranking payload must include an editor_note string")

        for entry in selected:
            if not isinstance(entry, dict):
                raise ValueError("Each selected ranking entry must be an object")
            if not isinstance(entry.get("story_id"), str) or not entry["story_id"].strip():
                raise ValueError(
                    "Each selected ranking entry must include a non-empty story_id string"
                )
            reason = entry.get("reason", "")
            if not isinstance(reason, str):
                raise ValueError("Each selected ranking entry reason must be a string")

    def _validate_summary_payload(self, parsed: dict[str, Any]) -> None:
        summary = parsed.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("AI summary payload must include a non-empty summary string")

    def _heuristic_rank(
        self,
        stories: list[Story],
        topics_payload: str,
        max_stories: int,
    ) -> RankingResult:
        topics = topics_payload.lower()

        def score(story: Story) -> int:
            text = f"{story.title} {story.summary}".lower()
            hits = sum(1 for token in topics.split() if len(token) > 3 and token in text)
            return hits

        ordered = sorted(stories, key=score, reverse=True)
        selected = ordered[:max_stories]
        reasons = {s.story_id: "Matched topic keywords" for s in selected}
        return RankingResult(
            [s.story_id for s in selected],
            reasons,
            "Auto-selected from topical relevance.",
        )

    def _heuristic_summary(self, story: Story, word_budget: int) -> str:
        words = story.content.split()
        return " ".join(words[: max(80, word_budget)])

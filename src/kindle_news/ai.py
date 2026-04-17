from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from json import JSONDecodeError
from string import Template
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from .config import AIConfig
from .cost import CostTracker
from .models import Story
from .retry import retry_call

logger = logging.getLogger(__name__)

DEFAULT_RANKING_PROMPT_TEMPLATE = """Task: rank stories for a weekly digest.
Output contract:
- Return exactly one JSON object and nothing else.
- Do not use markdown, code fences, comments, or trailing commas.
- JSON must start with '{' and end with '}'.
- Use this schema exactly:
    {\"selected\": [{\"story_id\": \"string\", \"reason\": \"string\"}],
    \"editor_note\": \"string\"}.
- selected must contain at most $max_stories items.
- Every selected item must contain non-empty story_id and reason strings.
- editor_note must be a concise string.

Hard exclusions (never select):
- Reader callouts or participation requests.
- Housekeeping/promotional items (newsletters, subscriptions, donations, contests, app prompts).
- Listicles (for example: "10 ways", "5 things", "top 7", "best 12").
- Video-led content where the core item is a video, clip, or livestream.
- Pure live pages/rolling updates with no new reported development.
- Clickbait framing with weak policy, market, or institutional substance.
If uncertain whether an item is journalism or a callout/promo/listicle/video item, exclude it.

Eligibility test (must pass):
- Contains a concrete development, decision, data release, investigation, or reported analysis.
- Has clear public-interest relevance to policy, institutions, markets, science, or culture.

Persona:
$persona

Reader topics:
$topics_payload

Stories:
$stories_json
"""

DEFAULT_SUMMARY_PROMPT_TEMPLATE = """Task: summarize one story for a weekly digest.
Output contract:
- Return exactly one JSON object and nothing else.
- Do not use markdown, code fences, comments, or trailing commas.
- JSON must start with '{' and end with '}'.
- Use this schema exactly: {\"summary\": \"string\"}.
- summary must be non-empty plain text.
- Target length around $word_budget words.

Persona:
$persona

Title: $title
URL: $url
Content:
$content
"""


class AIResponseValidationError(RuntimeError):
    """Raised when an AI response cannot be parsed/validated after repair."""


@dataclass(slots=True)
class RankingResult:
    selected_ids: list[str]
    reasons: dict[str, str]
    editor_note: str


class AIClient:
    def __init__(
        self,
        config: AIConfig,
        cost_tracker: CostTracker,
        ranking_prompt_template: str = DEFAULT_RANKING_PROMPT_TEMPLATE,
        summary_prompt_template: str = DEFAULT_SUMMARY_PROMPT_TEMPLATE,
    ) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self.ranking_prompt_template = ranking_prompt_template
        self.summary_prompt_template = summary_prompt_template
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
        prompt = self._ranking_prompt(compact, persona, topics_payload, max_stories)
        try:
            parsed = self._json_response(
                prompt,
                validator=self._validate_ranking_payload,
                repair_prompt=(
                    "Your previous response was invalid. Output only one JSON object. "
                    "No markdown, no backticks, no prose. Use this exact schema: "
                    '{"selected": [{"story_id": "string", "reason": "string"}], '
                    '"editor_note": "string"}. Keep selected length <= requested max_stories.'
                ),
            )
        except AIResponseValidationError:
            if not self.config.allow_heuristic_fallback:
                raise
            logger.warning("Falling back to heuristic ranking due to invalid AI response")
            return self._heuristic_rank(stories, topics_payload, max_stories)
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
        prompt = self._summary_prompt(story, persona, word_budget)
        try:
            parsed = self._json_response(
                prompt,
                validator=self._validate_summary_payload,
                repair_prompt=(
                    "Your previous response was invalid. Output only one JSON object. "
                    "No markdown, no backticks, no prose. Use this exact schema: "
                    '{"summary": "string"}. Ensure summary is non-empty plain text.'
                ),
            )
        except AIResponseValidationError:
            if not self.config.allow_heuristic_fallback:
                raise
            logger.warning(
                "Falling back to heuristic summary for story_id=%s due to invalid AI response",
                story.story_id,
            )
            return self._heuristic_summary(story, word_budget)
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
            try:
                return self._parse_json_payload(repaired, validator)
            except (JSONDecodeError, ValueError) as exc:
                raise AIResponseValidationError(
                    "AI response remained invalid after one repair attempt"
                ) from exc

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
        payload = self._extract_json_object(raw)
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise ValueError("AI response must be a JSON object")
        validator(parsed)
        return parsed

    def _extract_json_object(self, raw: str) -> str:
        cleaned = raw.strip()
        if not cleaned:
            raise ValueError("AI response was empty")

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and start < end:
            return cleaned[start : end + 1]
        return cleaned

    def _ranking_prompt(
        self,
        compact: list[dict[str, str]],
        persona: str,
        topics_payload: str,
        max_stories: int,
    ) -> str:
        return Template(self.ranking_prompt_template).safe_substitute(
            max_stories=str(max_stories),
            persona=persona,
            topics_payload=topics_payload,
            stories_json=json.dumps(compact),
        )

    def _summary_prompt(self, story: Story, persona: str, word_budget: int) -> str:
        return Template(self.summary_prompt_template).safe_substitute(
            word_budget=str(word_budget),
            persona=persona,
            title=story.title,
            url=story.url,
            content=story.content[:12000],
        )

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

from __future__ import annotations

import requests
from bs4 import BeautifulSoup, Tag

from .models import Story
from .retry import retry_call


def enrich_story_content(story: Story, timeout_seconds: int = 20) -> Story | None:
    def _get() -> requests.Response:
        response = requests.get(
            story.url,
            timeout=timeout_seconds,
            headers={
                "User-Agent": "kindle-news-bot/0.1",
                "Accept-Language": "en-GB,en;q=0.9",
            },
        )
        response.raise_for_status()
        return response

    try:
        response = retry_call(_get, retries=2, retry_on=(requests.RequestException, OSError))
    except (requests.RequestException, OSError):
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    content = "\n\n".join(p for p in paragraphs if len(p) > 40)
    if not content:
        return None

    if not story.image_url:
        image_tag = soup.find("meta", property="og:image")
        if isinstance(image_tag, Tag):
            image_content = image_tag.get("content")
            if isinstance(image_content, str):
                story.image_url = image_content

    story.content = content
    credit = soup.find("meta", attrs={"name": "author"})
    if isinstance(credit, Tag):
        credit_content = credit.get("content")
        if isinstance(credit_content, str) and credit_content:
            story.image_credit = credit_content
    return story

# Kindle News

Weekly AI-curated EPUB digest generated from RSS feeds and delivered by email.

## Quick start

1. Create and activate virtualenv:
   - `python3 -m venv venv`
   - `source venv/bin/activate`
2. Install dependencies:
   - `pip install -r requirements.txt`
   - `pip install -e .`
3. Update files in `config/`:
   - `config/config.yaml`
   - `config/feeds.txt`
   - `config/editor_persona.md`
   - `config/reader_topics.yaml`
4. Set env vars:
   - `OPENAI_API_KEY`
   - `SMTP_PASSWORD`
5. Run:
   - `python -m kindle_news`

To run without sending email:
- `python -m kindle_news --no-email`

## Output

- Final EPUB: `output/YYYY-MM-DD.epub`
- Artifacts: `output/artifacts/`

## Tests

- `pytest -q`

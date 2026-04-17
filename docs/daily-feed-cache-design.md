# Daily Feed Cache Design

## Problem
Several active RSS feeds expose only a short rolling window (for example 1 to 4 days). A weekly-only ingestion run can miss stories that were visible mid-week but rolled out of feed history before weekly publication.

## Goals
- Preserve full-week candidate coverage even when feed windows are short.
- Keep weekly ranking and EPUB generation unchanged in quality.
- Make failures observable and recoverable.
- Allow safe cleanup so each publication cycle starts fresh.

## Non-goals (Phase 1)
- Building a new external storage service.
- Replacing existing ranking or summarization logic.
- Cross-repo archival retention policy.

## High-level Architecture
1. Daily ingest mode:
- Fetch and normalize stories from active feeds.
- Save daily snapshot into local cache storage.
- Emit ingest artifacts for observability.

2. Weekly publish mode:
- Load stories from cache for the lookback window.
- Consolidate and dedupe before ranking.
- Generate EPUB and send email using existing pipeline.
- Clear cache only after successful weekly completion.

## Data Model
Cached file naming:
- daily-YYYY-MM-DD.json

Cached story payload:
- story_id
- title
- url
- source
- published_at (ISO datetime)
- summary
- image_url

Metadata emitted per run:
- cache_source_used (cache or live)
- cache_story_count
- cache_files_used
- cache_clear_removed_files

## Directory Layout
- output/cache/: rolling weekly snapshots.
- output/artifacts/: cache ingest/load/clear metadata files.

## Pipeline Changes (Phase 1)
- Add pipeline mode selector:
  - weekly (default)
  - ingest
- In ingest mode:
  - fetch recent stories from feeds
  - write daily cache file
  - return cache file path
- In weekly mode:
  - prefer cache stories for lookback period
  - fall back to live ingestion if cache is empty
  - clear cache after successful EPUB generation

## Failure Handling
- If daily ingest fails for some feeds, partial successes are still cached.
- If weekly cache load is empty, fallback to live feed ingestion is used.
- Cache clear runs only after successful weekly output path is produced.

## Operational Workflow
- Daily schedule: run ingest mode.
- Weekly schedule: run weekly mode.
- Manual dispatch can run either mode for recovery.

## Rollout Plan
Phase 1 (this change set):
- Add cache store module.
- Add ingest/weekly pipeline modes.
- Add CLI mode switch.
- Add config path for cache directory.
- Add baseline tests for cache serialization and mode behavior.

Phase 2:
- Add dedicated daily GitHub Action.
- Add weekly cache health checks and feed coverage gate artifacts.
- Optional: keep a short archive of prior-week cache manifests.

## Future Features
- Group stories into explicit editorial sections in the EPUB (for example Tech Business, UK Politics, Norway Politics, Science, Culture), implemented via ranking schema updates, prompt taxonomy, and section-aware rendering.

## Risks and Mitigations
- Risk: cache growth if cleanup is skipped.
  - Mitigation: weekly clear on success and explicit clear metadata artifact.

- Risk: duplicate stories across daily files.
  - Mitigation: existing dedupe pass in weekly pipeline remains in place.

- Risk: stale cache usage.
  - Mitigation: load only files within configured lookback window.

# Application requirements

## Overview

This application will get a week's worth of news and summarise it based on a reader topics file using an AI provider (probably openAI).

The AI will look through the stories from the last week gathered from provided RSS feeds. It will compare the stories with the reader topics file and pick the 15 (configurable) most relevant stories, summarising them so that they fit within the space constraints. Photos from the articles should be included so that there is visual interest as well.

The resulting summary will be a maximum 10 pages (configurable) from which an ebook will be created and then emailed to my kindle (SMTP details for an email server will be provided)

The reader topics file should have a way of marking things that are of interest and that are not of interest (for example, a score from -100 to +100 along with the topic). While the reader topics should be taken into account, the resulting ebook should also be a balanced review of the retreived news stories of the week.

Configuration files should be stored in a config folder in the repository.
The config folder should contain:
- A script configuration file (default: config/config.yaml) for runtime configuration such as input/output filenames and other script settings
- An RSS feeds file (default: config/feeds.txt, one feed URL per line)
- An editor persona file (default: config/editor_persona.md)
- A reader topics file for the specific reader's interests (default: config/reader_topics.yaml)

These filenames are defaults and should be configurable via the script configuration file.

## Editor persona

A file will be provided with the persona of the editor and the editorial outlook of the resulting ebook.

The file is expected to be either plaintext or plaintext with yaml frontmatter for specific configuration (length of publication, number of articles etc).

The editor persona file will also define what constitutes a balanced review and how page budgeting should be handled.

## RSS feeds

These will be in a text file, one rss feed per line. They should be retreived when the process is run and if the feed doesn't go back for a full week paging should be implemented.

From the summaries in the feeds, the AI should pick the most relevant stories. These should then be downloaded in full for the AI to summarise.

Expect in the region of 10-20 RSS feeds but you should be flexible on the number of feeds.

Stories across the feeds should be normalised and duplicates removed (favour the newest published date when removing duplicates.) If articles don't have images or they can't be retreived, there is no need to include them.

Some feeds may be paywalled in which case I need you to be able to handle authentication to sites if at all possible. This is however a next level requirement so if it's not easy to implement, miss it for now.

If a story cannot be downloaded in full, this should be logged and the process should continue without that story.

There should be state included to avoid duplicate stories from week to week (unless there is new information or an update/continuation to the story).

## AI interaction

OpenAI should be used with a cost effective model.
The AI should be given the persona file of the editor, the reader topics file, and the list of stories from the various RSS summaries. From this it should pick the stories that are most relevant for the rounded weekly summary.
With the list of stories that it picks, they should then be downloaded and each should be summarised by the AI to an appropriate length based on the space constraints of the weekly summary.
Not all stories should be summarised to the same length to provide variety and interest for the reader.

The total AI cost for a weekly run should remain under 1 USD.

## Images

Included images should use the native quality. Size should be amended to fit in with length constraints

Licensing constraints for images do not need to be considered for this personal-use application.

## Output ebook

This will be an ebook of the summary and should be generated as an epub suitable for sending over whispernet to a kindle device unless a later implementation constraint requires a different Kindle-compatible format. It should include a cover image that represents the most interesting photo image of the week.
The cover should have a title including the date of publication.

Images should have credits included. Default layout should be flowing around the pictures if possible.

Page budgeting should assume approximately 500 words per page, with the publication usually expected to be between 10 and 20 pages as defined by the editor persona file.

## Scheduling

The ebook should be created overnight on a Sunday and emailed to the kindle ready to read by 5am on a Monday morning. Assume GMT times

## Observability

Artifacts should be created including:
- A record of all stories retreived from the source RSS feeds
- A record of the resulting rss stories provided to the AI
- A record of the stories picked by the AI
- A record of the downloaded stories and images that are provided to the AI
- A record of the created ebook

The resulting ebook should be pushed to the repo for long term storage.

Only the output ebook needs to be persisted to the repo. A new weekly file should be stored using the publication date as the filename.

## Emailing

The ebook should be emailed to a specific email address as an attachment and from a specific email address. SMTP server details, password, from address and port will be provided in github actions secrets.

## Overall

The process should be run as a github action on a schedule. Language and approach are up to you, python would be.

## Copilot delivery requirements

### Definition of done (MVP)

The MVP is complete when all of the following are true:
- A scheduled GitHub Action runs weekly in GMT and finishes before the Monday 5am target.
- The workflow reads config from the config folder defaults unless overridden in config/config.yaml.
- The workflow retrieves feed entries, deduplicates stories, selects and summarises stories, generates an epub, and sends it by SMTP.
- Story download failures are logged and skipped without failing the full run.
- The weekly epub is saved to the repository using the publication date as the filename.
- Required artifacts are uploaded for observability.
- The total AI cost for a weekly run remains under 1 USD.

### Repository structure

The implementation should use the following structure (exact module names can vary):
- src/ for application code
- tests/ for automated tests
- config/ for runtime config and input files
- output/ for generated local outputs before upload/commit
- .github/workflows/ for scheduled automation

### Technical constraints

- Use Python 3.11+.
- Use a reproducible dependency file (requirements.txt or equivalent).
- Use typed Python where practical.
- Prefer widely used, maintained libraries for RSS parsing, HTTP retrieval, HTML extraction, image processing, and epub generation.

### Testing requirements

At minimum, include tests for:
- Config loading and default filename overrides
- Feed ingestion and duplicate removal behavior
- Story selection pipeline input/output shape
- Story download failure handling (log and continue)
- Page budgeting behavior based on configured constraints
- EPUB creation and expected output filename generation

### CI and quality gates

Pull requests should only be merged when all required checks pass:
- Formatting/lint checks
- Type checks
- Unit tests
- A workflow validation check (for GitHub Actions syntax)

### Error handling policy

- Feed-level fetch failure: log warning, continue with remaining feeds.
- Story download failure: log warning, skip story.
- AI call transient failure: retry with backoff, then fail run if unrecoverable.
- SMTP failure: retry with backoff, fail run if email cannot be sent.
- EPUB generation failure: fail run.

### Cost control enforcement

- Implement a per-run token/cost budget guardrail targeting under 1 USD total weekly AI spend.
- If projected or actual spend exceeds the budget threshold, stop additional AI processing and fail the run with a clear budget-exceeded message.

### Prompt and output contracts

- Use structured prompts with explicit expected JSON output schemas for story ranking and summary generation steps.
- Validate AI outputs before downstream processing.
- If output validation fails, retry with a repair prompt once before failing that specific item.

### State and dedupe requirements

- Keep a machine-readable state file storing previously used stories to reduce week-to-week repetition.
- Dedupe should consider URL canonicalization and title similarity.
- Permit repeat inclusion only where an item is detected as a continuation/update story according to configured logic.

### Output naming and persistence

- Weekly output epub filename should use publication date format YYYY-MM-DD.epub.
- Persist only the generated epub to repository history.

### Milestones for outsourced implementation

The work should be delivered in these milestones:
1. Project scaffolding, config loading, and validation.
2. Feed ingestion, normalization, dedupe, and state persistence.
3. AI-driven ranking and summarization pipeline with budget controls.
4. EPUB generation with images and cover.
5. Email delivery, scheduled workflow, and observability artifacts.

Each milestone should include:
- Working code
- Relevant automated tests
- A short implementation note
- A command or workflow step to verify behavior

### Runtime and branch policy defaults

- Target total runtime per scheduled run: under 20 minutes.
- Use PR-based development by default (no direct commits to main for feature work).

### Acceptance checklist

Use this checklist to approve outsourced delivery. Every item should be marked Pass or Fail during review.

| Area | Acceptance criteria | Evidence required | Status |
| --- | --- | --- | --- |
| Milestone 1: scaffold and config | Project structure created (src/, tests/, config/, output/, .github/workflows/). Config loads from config/config.yaml with documented overrides. | Repo tree, sample config files, test results for config loading. | [ ] Pass / [ ] Fail |
| Milestone 2: ingest and dedupe | RSS ingestion works for 10-20 feeds, stories are normalized, duplicates removed, and state file is read/written. | Test report for dedupe/state behavior, example artifact showing deduped list. | [ ] Pass / [ ] Fail |
| Milestone 3: AI pipeline and budget | AI ranking and summarization run with schema-validated outputs. Budget guardrail enforces under 1 USD and fails clearly when exceeded. | Prompt/output schema tests, run logs with estimated/actual spend, failure example for budget exceed. | [ ] Pass / [ ] Fail |
| Milestone 4: epub generation | EPUB generated with dated filename (YYYY-MM-DD.epub), includes cover/title/date, and handles image embedding/credits where available. | Generated EPUB artifact and automated test for filename/output path. | [ ] Pass / [ ] Fail |
| Milestone 5: delivery and observability | Weekly schedule configured in GMT, SMTP send works with retries, required artifacts uploaded, and epub persisted to repo history. | Workflow YAML, successful workflow run link/logs, artifact listing, commit showing persisted epub. | [ ] Pass / [ ] Fail |
| Reliability and failures | Feed/story failures log and continue; unrecoverable AI/SMTP/EPUB failures stop run with clear messages. | Logs from simulated failure tests and expected run outcomes. | [ ] Pass / [ ] Fail |
| Quality gates | Lint, type checks, tests, and workflow validation are required and passing in CI for merge. | CI configuration and latest passing CI run output. | [ ] Pass / [ ] Fail |
| Runtime target | Full scheduled run completes in under 20 minutes under normal conditions. | Workflow timing evidence from at least one representative run. | [ ] Pass / [ ] Fail |

Reviewer notes:
- Date reviewed:
- Reviewer:
- Open issues before production:

### How to review

Use the following process to evaluate each acceptance checklist row consistently.

1. Validate repository structure and config defaults.
- Confirm required folders exist: src/, tests/, config/, output/, .github/workflows/.
- Confirm default files exist in config/.
- Run the test target for config loading and verify override behavior.

2. Validate feed ingestion, dedupe, and state behavior.
- Run the test target for feed ingestion and duplicate handling.
- Review generated artifacts/logs to confirm normalization and dedupe outcomes.
- Confirm state file is created/updated and used on subsequent runs.

3. Validate AI contracts and budget controls.
- Run tests for AI response schema validation.
- Execute a representative pipeline run and inspect logs for token/cost reporting.
- Confirm budget-threshold behavior fails clearly when spend guardrail is exceeded.

4. Validate EPUB generation output.
- Run EPUB generation step or integration test.
- Confirm output filename matches YYYY-MM-DD.epub.
- Open the generated epub and verify title/date/cover and image credit presence when applicable.

5. Validate delivery workflow and observability.
- Inspect the scheduled workflow in .github/workflows/ and confirm GMT timing aligns with Monday 5am delivery target.
- Validate SMTP delivery logic, including retry behavior.
- Confirm all required artifacts are uploaded in workflow runs.
- Confirm only weekly epub output is persisted to repository history.

6. Validate quality gates and runtime target.
- Confirm CI requires lint, type checks, tests, and workflow validation before merge.
- Verify latest representative scheduled run completes under 20 minutes.

Evidence collection guidance:
- Attach links to passing CI runs and representative scheduled workflow runs.
- Attach artifact names/paths used for checklist verification.
- Record any deviations and required follow-up actions in Reviewer notes.
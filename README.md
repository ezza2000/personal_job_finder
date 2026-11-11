# Personal Job Finder

A personal job search aggregator and application tracker focused on graduate and junior IT/software roles in Melbourne.

## Current stage

Milestone 5 is in progress: preview-first Prosple RSS and forwarded/Gmail SEEK Grad email imports are available. At Windows sign-in, the app can launch automatically and import new listings from the configured Gmail label. The dashboard includes direct job links and an applied jobs view. The daily email report remains future work.

## Architecture

- Python 3.11+ and FastAPI for the API.
- SQLAlchemy 2 and Alembic for persistence and schema changes.
- SQLite locally, with `DATABASE_URL` ready to point at PostgreSQL later.
- React, TypeScript, and Vite power the responsive desktop/mobile dashboard in `frontend/`.
- Source adapters will be isolated by provider and enabled only for documented feeds/APIs or user-provided imports that are permitted by the source.

## Setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/health` to check the API or `/docs` to try its endpoints. The database path and logging level can be changed in `.env`.

After the first-time setup above, start both local servers and open the dashboard with one command:

```powershell
.\run.ps1
```

The launcher checks ports 8090–8110, reuses a running API when available, writes the matching local frontend API URL, starts the dashboard, and opens it in your browser. Stop the server windows with `Ctrl+C` when you are finished.

To start the app automatically each time you sign in to Windows, run this once from PowerShell:

```powershell
.\install-startup.ps1
```

The scheduled task runs `run.ps1` in your user session, opens the dashboard, and the dashboard checks the configured Gmail label and imports new supported SEEK Grad listings. To remove the startup task, run `Unregister-ScheduledTask -TaskName 'Personal Job Finder' -Confirm:$false`.

In a second terminal, run the dashboard:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The frontend expects the API at `http://127.0.0.1:8000`; set `VITE_API_URL` in `frontend/.env.local` to use a different API address. The dashboard uses the API's CORS allowlist for local Vite development.

## Tests

```powershell
pytest
```

## Data model

- `job_sources` records source/import channels and their last run outcome.
- `jobs` stores normalized listing fields, source URL, discovery/posting dates, and company/title keys for later duplicate matching.
- `applications` stores status and the application date, resume version, cover letter, contact, follow-up date, and interview notes.
- `candidate_profile` stores editable education, placement, experience summary, and skills for the later matching stage.
- `import_batches` retains a validated CSV preview until it is explicitly committed.
- `duplicate_candidates` records similar listing pairs for a user decision; possible matches are not silently merged.
- Match analysis is calculated from the current profile and job text on request, so profile edits do not leave stale saved scores.

## API

- `POST /api/jobs` manually creates a listing and initial status. An exact URL already in the database returns HTTP 409 with the existing job ID.
- `GET /api/jobs` lists current jobs, tracking details, and a current match analysis.
- `DELETE /api/jobs/{id}` removes a job, its application notes, and duplicate-review records.
- `GET /api/jobs/{id}/match` returns the match analysis for one job.
- `PATCH /api/jobs/{id}/application` changes status and application details. Moving to `applied` fills today's date when none is supplied.
- `GET /api/profile` and `PUT /api/profile` read and update the candidate's editable background and skills.
- `POST /api/imports/csv/preview` accepts JSON with `filename` and CSV `content`, validates up to 1,000 rows, and shows errors and potential duplicates without adding jobs.
- `POST /api/imports/csv/{batch_id}/commit` imports valid preview rows after confirmation. Exact URLs already present are reported and skipped; similar titles/companies are imported and flagged.
- `GET /api/duplicates` lists unresolved possible duplicates; `PATCH /api/duplicates/{id}` sets `review_state` to `confirmed_duplicate` or `confirmed_distinct`.
- `GET /api/sources` lists import channels and their last check/error state.
- `POST /api/imports/prosple/rss/preview` fetches the configured public feed, checks possible duplicates, and stores a reviewable preview.
- `POST /api/imports/prosple/rss/{batch_id}/commit` imports valid rows from that preview; exact URLs are skipped and possible duplicates are flagged.
- `POST /api/imports/seek-grad-email/preview` accepts pasted forwarded text, HTML, or a downloaded `.eml` file, parses SEEK Grad cards, skips expired listings, and returns a duplicate-aware preview.
- `POST /api/imports/seek-grad-email/{batch_id}/commit` imports valid listings from a reviewed email preview.
- `GET /api/email/gmail/status` reports whether local OAuth files exist.
- `POST /api/email/gmail/connect` opens Google's installed-app consent flow and requests Gmail read-only access.
- `POST /api/imports/gmail/seek-grad/preview` searches the configured Gmail label for SEEK Grad messages and returns a reviewable preview; `POST /api/imports/gmail/seek-grad/{batch_id}/commit` imports it after review.
- `POST /api/email/gmail/sync` imports newly found supported SEEK Grad listings and skips exact URLs or matching title/company/location combinations already discovered in the last 60 days. The dashboard calls it at startup when Gmail is connected.

### Optional Gmail connection

The Codex Gmail connection is separate from this local app. To enable mailbox import, create a Google Cloud project, enable the Gmail API, configure the OAuth consent screen, and create an OAuth client with application type **Desktop app**. During personal testing, add the Gmail account as a test user if the consent screen is in testing mode. Download the client JSON to `secrets/gmail-oauth-client.json` (the `secrets/` directory is ignored by Git), then start the app and choose **Import SEEK email → Connect Gmail**. Sign in in the browser and review Google's consent screen; the app does not need or store your email password. The OAuth token is stored locally at `secrets/gmail-token.json` and is also ignored by Git.

Create a Gmail label such as `SEEK Job Alerts`, and configure a Gmail filter to apply it to forwarded SEEK alert messages. Set `GMAIL_SEEK_LABEL` in `.env` to that exact label. `GMAIL_SEEK_QUERY` is an optional extra Gmail search query; leave it blank to search only that label, or set a sender filter if your forward preserves the original sender. The app only reads matching messages and leaves them untouched. The manual **Preview Gmail alerts** action remains review-first; automatic startup sync imports newly found supported listings and skips exact URLs already saved. Google's `gmail.readonly` scope is classified as restricted and technically permits reading mailbox messages and settings, even though this app's query targets one label. Public distribution with this scope has OAuth verification requirements; this setup is for your local personal app. See Google's [Desktop OAuth guide](https://developers.google.com/identity/protocols/oauth2/native-app), [Gmail scope classifications](https://developers.google.com/workspace/gmail/api/auth/scopes), and [Gmail search/filter guide](https://developers.google.com/workspace/gmail/api/guides/filtering).

### Prosple RSS setup

Prosple documents public RSS feeds for career directories. Configure a feed URL in `.env` by opening the relevant directory's `/search-jobs` page and replacing `search-jobs` with `rss?` (for example, the GradAustralia feed). The default host allowlist accepts `gradaustralia.com.au` and `prosple.com`; add another trusted directory host to `PROSPLE_RSS_ALLOWED_HOSTS` if its feed uses a custom domain. Only the feed is fetched; the importer does not crawl linked job pages. Preview an import in `/docs`, inspect the returned rows and duplicate candidates, then call the matching commit endpoint. Repeated previews are safe: exact URLs are skipped at commit. [Prosple RSS guidance](https://recruiters.prosple.com/resources-all/post/automated-job-alert-emails) and [technical FAQ](https://recruiters.prosple.com/resources-all/post/technical-faq).

### SEEK and email alerts

The app does not search or scrape SEEK. SEEK's current website terms prohibit automated access and collection without an approved technical interface or prior written consent. A forwarded SEEK Grad alert parser is available for pasted, uploaded, or Gmail-fetched messages; inspect duplicate matches, then explicitly import the preview. The parser does not follow tracked links and skips listings whose email alert includes an expired closing date. Gmail access requires a separate local OAuth setup; the Codex Gmail connection does not act as credentials for this app. Keep the OAuth client JSON and token in the ignored local `secrets/` directory.

CSV requires `title` and `company`. Optional headers include `location`, `salary`, `employment_type`, `description`, `experience_required`, `date_posted` (`YYYY-MM-DD`), `original_url`, `source`, `status`, `application_date`, `resume_version`, `cover_letter`, `contact_person`, `follow_up_date`, and `interview_notes`.

## Matching method

The score is a transparent heuristic for prioritizing listings, not a prediction of interview or hiring chances. It totals four components: recognizable technical skills (50 points), experience level (25), education alignment (15), and whether the role title fits the target technology areas (10). If a listing does not name recognizable skills, the skills component receives a neutral 25 points. The response includes component scores, matched and missing recognized skills, reasons, and experience or qualification flags. No external AI service is called.

## Updated roadmap

1. **Foundation (complete):** Configuration, logging, database models/migrations, and API skeleton.
2. **Manual tracking and imports (complete):** Job entry, application status/details, CSV import preview, validation, duplicate review, and editable candidate background/skills profile.
3. **Matching (complete):** Explainable score out of 100, matching reasons, matched/missing skills, and experience/qualification flags based on the editable profile.
4. **Responsive dashboard (complete):** React listings, overview counts, search, Melbourne CBD/South East Melbourne/Bayside and suburb filters, status filtering, relevance/recency sorting, match explanations, status and application detail editing, applied jobs view, direct job links, and mobile layouts. Commuting distance remains a later enhancement if geocoding/routing data is available.
5. **Permitted job sources (in progress):** Prosple RSS import preview/commit with duplicate handling and source status; forwarded SEEK Grad email preview/commit with expired-job filtering. Add documented public company/ATS feeds individually. SEEK website automation remains disabled unless SEEK provides written consent or an applicable approved interface. Direct Gmail-label sync remains a separately configured, opt-in OAuth integration.
6. **Daily automation and reports (in progress):** Windows sign-in startup and Gmail SEEK Grad import are available. Add per-source failure isolation and a morning email report of the 10–15 most relevant new jobs with title, company, location, salary when available, score, explanation, and direct link. Exclude applied jobs and previously reported jobs unless a meaningful listing change is detected.
7. **Portfolio finish:** Automated tests, setup and architecture documentation, sample data, screenshots, and deployment guidance.

## Source and report constraints

The app does not scrape job boards. Some major boards prohibit automated collection or do not offer a general job-seeker API. Before enabling a source, review its current terms and the specific feed/API conditions. SEEK's current [Website Terms](https://au.seek.com/terms) prohibit automated gathering without prior written consent or a specific compliant technical interface. Gmail sync uses OAuth, and Gmail's `gmail.readonly` scope can access mailbox messages and settings, so the app filters to a dedicated label and requires explicit user authorization. See [Google's OAuth scope list](https://developers.google.com/identity/protocols/oauth2/scopes).

Gmail label import requires a local OAuth client and user authorization. The automatic startup task runs only after Windows sign-in and only while the computer is on; the daily email report remains future work. Reliable delivery while a computer is off requires an always-on host or external scheduled runner. Hosting, domain, and email-provider costs depend on the selected deployment and volume; the local development stack has no required service fees.

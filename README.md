# Personal Job Finder

A personal job search aggregator and application tracker focused on graduate and junior IT/software roles in Melbourne.

## Current stage

Milestone 5 is in progress: a preview-first Prosple RSS adapter is available, with duplicate checks and source run status. Milestone 4 provides a responsive React dashboard for job discovery, profile match review, location/status filtering, sorting, and application tracking. Milestone 3 adds explainable profile-to-job scores, matched/missing skills, and experience/education flags. Milestone 2 provides manual job entry, application tracking, CSV preview/import, duplicate review, and an editable candidate profile. SEEK job alerts, scheduling, and email reports remain future work.

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
- `GET /api/jobs/{id}/match` returns the match analysis for one job.
- `PATCH /api/jobs/{id}/application` changes status and application details. Moving to `applied` fills today's date when none is supplied.
- `GET /api/profile` and `PUT /api/profile` read and update the candidate's editable background and skills.
- `POST /api/imports/csv/preview` accepts JSON with `filename` and CSV `content`, validates up to 1,000 rows, and shows errors and potential duplicates without adding jobs.
- `POST /api/imports/csv/{batch_id}/commit` imports valid preview rows after confirmation. Exact URLs already present are reported and skipped; similar titles/companies are imported and flagged.
- `GET /api/duplicates` lists unresolved possible duplicates; `PATCH /api/duplicates/{id}` sets `review_state` to `confirmed_duplicate` or `confirmed_distinct`.
- `GET /api/sources` lists import channels and their last check/error state.
- `POST /api/imports/prosple/rss/preview` fetches the configured public feed, checks possible duplicates, and stores a reviewable preview.
- `POST /api/imports/prosple/rss/{batch_id}/commit` imports valid rows from that preview; exact URLs are skipped and possible duplicates are flagged.

### Prosple RSS setup

Prosple documents public RSS feeds for career directories. Configure a feed URL in `.env` by opening the relevant directory's `/search-jobs` page and replacing `search-jobs` with `rss?` (for example, the GradAustralia feed). The default host allowlist accepts `gradaustralia.com.au` and `prosple.com`; add another trusted directory host to `PROSPLE_RSS_ALLOWED_HOSTS` if its feed uses a custom domain. Only the feed is fetched; the importer does not crawl linked job pages. Preview an import in `/docs`, inspect the returned rows and duplicate candidates, then call the matching commit endpoint. Repeated previews are safe: exact URLs are skipped at commit. [Prosple RSS guidance](https://recruiters.prosple.com/resources-all/post/automated-job-alert-emails) and [technical FAQ](https://recruiters.prosple.com/resources-all/post/technical-faq).

### SEEK and email alerts

The app does not search or scrape SEEK. SEEK's current website terms prohibit automated access and collection without an approved technical interface or prior written consent. A future SEEK path is user-provided alert email import; no SEEK job alert was present in the connected Gmail mailbox when this adapter was started, so a representative alert is still needed to implement and verify that parser. Direct Gmail mailbox sync would require a separate OAuth setup for this app; the app can query a dedicated label, but Google's read-only Gmail scope grants access to mailbox messages and settings. The Codex Gmail connection does not act as credentials for the local app. Configure any OAuth credentials only in local environment variables, never in source control.

CSV requires `title` and `company`. Optional headers include `location`, `salary`, `employment_type`, `description`, `experience_required`, `date_posted` (`YYYY-MM-DD`), `original_url`, `source`, `status`, `application_date`, `resume_version`, `cover_letter`, `contact_person`, `follow_up_date`, and `interview_notes`.

## Matching method

The score is a transparent heuristic for prioritizing listings, not a prediction of interview or hiring chances. It totals four components: recognizable technical skills (50 points), experience level (25), education alignment (15), and whether the role title fits the target technology areas (10). If a listing does not name recognizable skills, the skills component receives a neutral 25 points. The response includes component scores, matched and missing recognized skills, reasons, and experience or qualification flags. No external AI service is called.

## Updated roadmap

1. **Foundation (complete):** Configuration, logging, database models/migrations, and API skeleton.
2. **Manual tracking and imports (complete):** Job entry, application status/details, CSV import preview, validation, duplicate review, and editable candidate background/skills profile.
3. **Matching (complete):** Explainable score out of 100, matching reasons, matched/missing skills, and experience/qualification flags based on the editable profile.
4. **Responsive dashboard (complete):** React listings, overview counts, search, Melbourne CBD/South East Melbourne/Bayside and suburb filters, status filtering, relevance/recency sorting, match explanations, status and application detail editing, and mobile layouts. Commuting distance remains a later enhancement if geocoding/routing data is available.
5. **Permitted job sources (in progress):** Prosple RSS import preview/commit with duplicate handling and source status. Add documented public company/ATS feeds individually. SEEK website automation remains disabled unless SEEK provides written consent or an applicable approved interface; implement user-provided alert email parsing after a sample is available. Direct Gmail-label sync remains a separately configured, opt-in OAuth integration.
6. **Daily automation and reports:** Configurable schedule and time zone, per-source failure isolation, and a morning report of the 10–15 most relevant new jobs with title, company, location, salary when available, score, explanation, and direct link. Exclude applied jobs and previously reported jobs unless a meaningful listing change is detected.
7. **Portfolio finish:** Automated tests, setup and architecture documentation, sample data, screenshots, and deployment guidance.

## Source and report constraints

The app does not scrape job boards. Some major boards prohibit automated collection or do not offer a general job-seeker API. Before enabling a source, review its current terms and the specific feed/API conditions. SEEK's current [Website Terms](https://au.seek.com/terms) prohibit automated gathering without prior written consent or a specific compliant technical interface. Gmail sync is not implemented yet; Google requires OAuth authorization, and Gmail's `gmail.readonly` scope can access mailbox messages and settings, so a dedicated-label query and explicit consent will be required before enabling it. See [Google's OAuth scope list](https://developers.google.com/identity/protocols/oauth2/scopes).

The daily scheduler will run only while a local app process is active. Reliable delivery while a computer is off requires an always-on host or external scheduled runner. Hosting, domain, and email-provider costs depend on the selected deployment and volume; the local development stack has no required service fees.

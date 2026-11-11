# Personal Job Finder

A personal job search aggregator and application tracker focused on graduate and junior IT/software roles in Melbourne.

## Current stage

Milestone 4 provides a responsive React dashboard for job discovery, profile match review, location/status filtering, sorting, and application tracking. Milestone 3 adds explainable profile-to-job scores, matched/missing skills, and experience/education flags. Milestone 2 provides manual job entry, application tracking, CSV preview/import, duplicate review, and an editable candidate profile. Job source integrations, scheduling, and email reports remain future milestones.

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

## Milestone 2 API

- `POST /api/jobs` manually creates a listing and initial status. An exact URL already in the database returns HTTP 409 with the existing job ID.
- `GET /api/jobs` lists current jobs, tracking details, and a current match analysis.
- `GET /api/jobs/{id}/match` returns the match analysis for one job.
- `PATCH /api/jobs/{id}/application` changes status and application details. Moving to `applied` fills today's date when none is supplied.
- `GET /api/profile` and `PUT /api/profile` read and update the candidate's editable background and skills.
- `POST /api/imports/csv/preview` accepts JSON with `filename` and CSV `content`, validates up to 1,000 rows, and shows errors and potential duplicates without adding jobs.
- `POST /api/imports/csv/{batch_id}/commit` imports valid preview rows after confirmation. Exact URLs already present are reported and skipped; similar titles/companies are imported and flagged.
- `GET /api/duplicates` lists unresolved possible duplicates; `PATCH /api/duplicates/{id}` sets `review_state` to `confirmed_duplicate` or `confirmed_distinct`.

CSV requires `title` and `company`. Optional headers include `location`, `salary`, `employment_type`, `description`, `experience_required`, `date_posted` (`YYYY-MM-DD`), `original_url`, `source`, `status`, `application_date`, `resume_version`, `cover_letter`, `contact_person`, `follow_up_date`, and `interview_notes`.

## Matching method

The score is a transparent heuristic for prioritizing listings, not a prediction of interview or hiring chances. It totals four components: recognizable technical skills (50 points), experience level (25), education alignment (15), and whether the role title fits the target technology areas (10). If a listing does not name recognizable skills, the skills component receives a neutral 25 points. The response includes component scores, matched and missing recognized skills, reasons, and experience or qualification flags. No external AI service is called.

## Updated roadmap

1. **Foundation (complete):** Configuration, logging, database models/migrations, and API skeleton.
2. **Manual tracking and imports (complete):** Job entry, application status/details, CSV import preview, validation, duplicate review, and editable candidate background/skills profile.
3. **Matching (complete):** Explainable score out of 100, matching reasons, matched/missing skills, and experience/qualification flags based on the editable profile.
4. **Responsive dashboard (complete):** React listings, overview counts, search, Melbourne CBD/South East Melbourne/Bayside and suburb filters, status filtering, relevance/recency sorting, match explanations, status and application detail editing, and mobile layouts. Commuting distance remains a later enhancement if geocoding/routing data is available.
5. **Permitted job sources:** Add source adapters individually after reviewing terms and access methods. Evaluate Prosple RSS and documented public company/ATS feeds; use manual/CSV imports or user-provided alert emails where direct automated access is not permitted. Email-alert mailbox/Gmail-label integration remains a future opt-in integration requiring explicit account authorization.
6. **Daily automation and reports:** Configurable schedule and time zone, per-source failure isolation, and a morning report of the 10–15 most relevant new jobs with title, company, location, salary when available, score, explanation, and direct link. Exclude applied jobs and previously reported jobs unless a meaningful listing change is detected.
7. **Portfolio finish:** Automated tests, setup and architecture documentation, sample data, screenshots, and deployment guidance.

## Source and report constraints

The first version does not scrape job boards. Some major boards prohibit automated collection or do not offer a general job-seeker API. Before enabling any source, review its current terms and the specific feed/API conditions. Gmail integration will be opt-in and should use scoped OAuth access to a dedicated label or mailbox; it is intentionally not part of the initial milestones.

The daily scheduler will run only while a local app process is active. Reliable delivery while a computer is off requires an always-on host or external scheduled runner. Hosting, domain, and email-provider costs depend on the selected deployment and volume; the local development stack has no required service fees.

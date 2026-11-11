"""Manual job entry, application tracking, CSV import, and profile routes."""

import csv
import io
import logging
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import get_db
from app.config import get_settings
from app.db.models import (
    Application,
    CandidateProfile,
    DuplicateCandidate,
    ImportBatch,
    Job,
    JobSource,
)
from app.schemas import (
    ApplicationUpdate,
    CsvPreviewRequest,
    DuplicateReview,
    JobCreate,
    JobMatchResult,
    JobRead,
    JobSourceRead,
    JobWithMatch,
    ProfileRead,
    ProfileUpdate,
    SeekGradEmailRequest,
)
from app.services.gmail_import import (
    GmailSetupError,
    authorize_gmail,
    gmail_status,
    read_seek_alerts,
)
from app.services.matching import analyze_job
from app.services.normalization import compare_jobs, normalize_text
from app.services.prosple_rss import FeedImportError, fetch_prosple_feed
from app.services.seek_grad_email import SeekEmailParseError, parse_seek_grad_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["job tracking"])
MAX_CSV_ROWS = 1000


def _get_source(db: Session, name: str, source_type: str) -> JobSource:
    normalized_name = name.strip() or "CSV Import"
    source = db.scalar(select(JobSource).where(JobSource.name == normalized_name))
    if source is None:
        source = JobSource(name=normalized_name, source_type=source_type)
        db.add(source)
        db.flush()
    return source


def _get_profile(db: Session) -> CandidateProfile:
    profile = db.get(CandidateProfile, 1)
    if profile is None:
        profile = CandidateProfile(
            id=1,
            education="Bachelor of Computer Science, Deakin University",
            placement="Computer Science professional placement at ROVing Intelligence",
            experience_summary=(
                "Python data processing, video processing, underwater robotics, and software "
                "development. Experience with Docker, AWS, and MySQL."
            ),
            skills=["Python", "C++", "C#", "SQL", "Git", "Linux", "Docker", "AWS", "MySQL"],
        )
        db.add(profile)
        db.flush()
    return profile


def _record_duplicate(
    db: Session, first_id: int, second_id: int, similarity: int, reasons: list[str]
) -> None:
    first_id, second_id = sorted((first_id, second_id))
    existing = db.scalar(
        select(DuplicateCandidate).where(
            DuplicateCandidate.first_job_id == first_id,
            DuplicateCandidate.second_job_id == second_id,
        )
    )
    if existing is None:
        db.add(
            DuplicateCandidate(
                first_job_id=first_id,
                second_job_id=second_id,
                similarity=similarity,
                reasons=reasons,
            )
        )


def _find_duplicates(title: str, company: str, jobs: list[Job]) -> list[dict[str, object]]:
    matches = []
    for job in jobs:
        result = compare_jobs(title, company, job.title, job.company)
        if result:
            score, reasons = result
            matches.append(
                {
                    "job_id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "similarity": score,
                    "reasons": reasons,
                }
            )
    return matches


@router.post("/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db)) -> Job:
    """Create a manually entered job and its initial application status."""
    url = str(payload.original_url) if payload.original_url else None
    if url:
        existing = db.scalar(select(Job).where(Job.original_url == url))
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"message": "This URL is already saved", "existing_job_id": existing.id},
            )

    existing_jobs = list(db.scalars(select(Job)))
    source = _get_source(db, payload.source_name, "manual")
    job = Job(
        title=payload.title,
        company=payload.company,
        location=payload.location,
        salary_text=payload.salary_text,
        employment_type=payload.employment_type,
        description=payload.description,
        experience_required=payload.experience_required,
        date_posted=payload.date_posted,
        closing_date=payload.closing_date,
        original_url=url,
        company_normalized=normalize_text(payload.company),
        title_normalized=normalize_text(payload.title),
        source_id=source.id,
    )
    db.add(job)
    db.flush()
    db.add(Application(job_id=job.id, **payload.application.model_dump()))
    db.flush()
    for match in _find_duplicates(job.title, job.company, existing_jobs):
        _record_duplicate(
            db, job.id, int(match["job_id"]), int(match["similarity"]), match["reasons"]
        )
    db.commit()
    return db.scalar(select(Job).options(joinedload(Job.application)).where(Job.id == job.id))


@router.get("/jobs", response_model=list[JobWithMatch])
def list_jobs(db: Session = Depends(get_db)) -> list[JobWithMatch]:
    profile = _get_profile(db)
    db.commit()
    jobs = list(
        db.scalars(
            select(Job)
            .options(joinedload(Job.application), joinedload(Job.source))
            .order_by(Job.date_discovered.desc())
        )
    )
    return [
        JobWithMatch(
            **JobRead.model_validate(job).model_dump(exclude={"match"}),
            match=analyze_job(job, profile),
        )
        for job in jobs
    ]


@router.get("/jobs/{job_id}/match", response_model=JobMatchResult)
def get_job_match(job_id: int, db: Session = Depends(get_db)) -> JobMatchResult:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    profile = _get_profile(db)
    db.commit()
    return analyze_job(job, profile)


@router.get("/sources", response_model=list[JobSourceRead])
def list_sources(db: Session = Depends(get_db)) -> list[JobSource]:
    """List configured import channels and their last outcome."""
    return list(db.scalars(select(JobSource).order_by(JobSource.name)))


@router.patch("/jobs/{job_id}/application", response_model=JobRead)
def update_application(
    job_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)
) -> Job:
    job = db.scalar(select(Job).options(joinedload(Job.application)).where(Job.id == job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.application is None:
        job.application = Application(job_id=job.id)
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is None:
        raise HTTPException(status_code=422, detail="Status cannot be null")
    if changes.get("status") == "applied" and "application_date" not in changes:
        job.application.application_date = date.today()
    for key, value in changes.items():
        setattr(job.application, key, value)
    db.commit()
    db.refresh(job)
    return job


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Remove a job and its application notes and duplicate-review records."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.execute(delete(Application).where(Application.job_id == job_id))
    db.execute(
        delete(DuplicateCandidate).where(
            or_(
                DuplicateCandidate.first_job_id == job_id,
                DuplicateCandidate.second_job_id == job_id,
            )
        )
    )
    db.delete(job)
    db.commit()
    return {"deleted": True, "job_id": job_id}


@router.get("/profile", response_model=ProfileRead)
def get_profile(db: Session = Depends(get_db)) -> CandidateProfile:
    profile = _get_profile(db)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/profile", response_model=ProfileRead)
def update_profile(payload: ProfileUpdate, db: Session = Depends(get_db)) -> CandidateProfile:
    profile = _get_profile(db)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


def _csv_row(raw: dict[str, str | None], row_number: int) -> dict[str, object]:
    fields = {
        normalize_text(key).replace(" ", "_"): (value or "").strip()
        for key, value in raw.items()
        if key is not None
    }
    errors: list[str] = []
    title = fields.get("title") or fields.get("job_title") or fields.get("position") or ""
    company = fields.get("company") or fields.get("company_name") or fields.get("employer") or ""
    if not title:
        errors.append("Title is required")
    if not company:
        errors.append("Company is required")

    url = fields.get("original_url") or fields.get("job_url") or fields.get("url") or ""
    if url and urlparse(url).scheme not in {"http", "https"}:
        errors.append("URL must start with http:// or https://")

    date_posted = fields.get("date_posted") or ""
    if date_posted:
        try:
            date.fromisoformat(date_posted)
        except ValueError:
            errors.append("Date posted must use YYYY-MM-DD")

    app_date = fields.get("application_date") or ""
    if app_date:
        try:
            date.fromisoformat(app_date)
        except ValueError:
            errors.append("Application date must use YYYY-MM-DD")

    closing_date = fields.get("closing_date") or ""
    if closing_date:
        try:
            date.fromisoformat(closing_date)
        except ValueError:
            errors.append("Closing date must use YYYY-MM-DD")

    follow_up_date = fields.get("follow_up_date") or ""
    if follow_up_date:
        try:
            date.fromisoformat(follow_up_date)
        except ValueError:
            errors.append("Follow-up date must use YYYY-MM-DD")

    status_value = (fields.get("status") or "new").casefold()
    if status_value not in {
        "new",
        "interested",
        "saved",
        "applied",
        "interview",
        "rejected",
        "closed",
    }:
        errors.append(
            "Status must be New, Interested, Saved, Applied, Interview, Rejected, or Closed"
        )

    data: dict[str, object] = {
        "title": title,
        "company": company,
        "location": fields.get("location") or None,
        "salary_text": fields.get("salary") or fields.get("salary_text") or None,
        "employment_type": fields.get("employment_type") or None,
        "description": fields.get("description") or None,
        "experience_required": fields.get("experience_required")
        or fields.get("experience")
        or None,
        "date_posted": date_posted or None,
        "closing_date": closing_date or None,
        "original_url": url or None,
        "source_name": fields.get("source") or fields.get("source_name") or "CSV Import",
        "application": {
            "status": status_value,
            "application_date": app_date or None,
            "resume_version": fields.get("resume_version") or None,
            "cover_letter": fields.get("cover_letter") or None,
            "contact_person": fields.get("contact_person") or None,
            "follow_up_date": fields.get("follow_up_date") or None,
            "interview_notes": fields.get("interview_notes") or None,
        },
    }
    return {
        "row_number": row_number,
        "valid": not errors,
        "errors": errors,
        "job": data,
        "duplicates": [],
    }


@router.post("/imports/csv/preview", status_code=status.HTTP_201_CREATED)
def preview_csv(payload: CsvPreviewRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    """Validate CSV content and persist a preview for explicit commit."""
    try:
        reader = csv.DictReader(io.StringIO(payload.content.lstrip("\ufeff")))
        if not reader.fieldnames or not any(name.strip() for name in reader.fieldnames):
            raise HTTPException(status_code=422, detail="CSV must include a header row")
        rows = [_csv_row(raw, number) for number, raw in enumerate(reader, start=2)]
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse CSV: {exc}") from exc
    if not rows:
        raise HTTPException(status_code=422, detail="CSV contains no data rows")
    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(status_code=413, detail=f"CSV is limited to {MAX_CSV_ROWS} rows")

    existing_jobs = list(db.scalars(select(Job)))
    existing_by_url = {job.original_url: job for job in existing_jobs if job.original_url}
    valid_prior: list[tuple[int, dict[str, object]]] = []
    for row in rows:
        if not row["valid"]:
            continue
        job_data = row["job"]
        matches = _find_duplicates(str(job_data["title"]), str(job_data["company"]), existing_jobs)
        url = job_data["original_url"]
        if url and url in existing_by_url:
            exact = existing_by_url[url]
            matches.append(
                {
                    "job_id": exact.id,
                    "title": exact.title,
                    "company": exact.company,
                    "similarity": 100,
                    "reasons": ["Original URL matches exactly"],
                }
            )
        for prior_row_number, prior in valid_prior:
            prior_data = prior["job"]
            if url and url == prior_data["original_url"]:
                matches.append(
                    {
                        "row_number": prior_row_number,
                        "title": prior_data["title"],
                        "company": prior_data["company"],
                        "similarity": 100,
                        "reasons": ["Original URL matches exactly"],
                    }
                )
                continue
            result = compare_jobs(
                str(job_data["title"]),
                str(job_data["company"]),
                str(prior_data["title"]),
                str(prior_data["company"]),
            )
            if result:
                score, reasons = result
                matches.append(
                    {
                        "row_number": prior_row_number,
                        "title": prior_data["title"],
                        "company": prior_data["company"],
                        "similarity": score,
                        "reasons": reasons,
                    }
                )
        row["duplicates"] = matches
        valid_prior.append((int(row["row_number"]), row))

    batch = ImportBatch(filename=payload.filename, rows=rows)
    db.add(batch)
    db.commit()
    return {
        "batch_id": batch.id,
        "filename": batch.filename,
        "total_rows": len(rows),
        "valid_rows": sum(bool(row["valid"]) for row in rows),
        "invalid_rows": sum(not bool(row["valid"]) for row in rows),
        "possible_duplicate_rows": sum(bool(row["duplicates"]) for row in rows),
        "rows": rows,
    }


@router.post("/imports/prosple/rss/preview", status_code=status.HTTP_201_CREATED)
def preview_prosple_rss(db: Session = Depends(get_db)) -> dict[str, object]:
    """Fetch a configured public Prosple RSS feed and save a reviewable import preview."""
    settings = get_settings()
    if not settings.prosple_rss_url.strip():
        raise HTTPException(
            status_code=409,
            detail="Set PROSPLE_RSS_URL in .env before previewing a Prosple feed",
        )
    allowed_hosts = {
        host.strip().casefold().lstrip(".")
        for host in settings.prosple_rss_allowed_hosts.split(",")
        if host.strip()
    }
    source = _get_source(db, "Prosple RSS", "rss")
    source.last_checked_at = datetime.now(UTC)
    try:
        entries = fetch_prosple_feed(settings.prosple_rss_url, allowed_hosts)
    except FeedImportError as exc:
        source.last_error = str(exc)
        db.commit()
        logger.warning("Prosple RSS preview failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    source.last_error = None
    existing_jobs = list(db.scalars(select(Job)))
    existing_by_url = {job.original_url: job for job in existing_jobs if job.original_url}
    prior_rows: list[tuple[int, dict[str, object]]] = []
    rows: list[dict[str, object]] = []
    for row_number, entry in enumerate(entries, start=2):
        row = _csv_row(entry, row_number)
        job_data = row["job"]
        matches = _find_duplicates(str(job_data["title"]), str(job_data["company"]), existing_jobs)
        url = job_data["original_url"]
        if url and url in existing_by_url:
            exact = existing_by_url[url]
            matches.append(
                {
                    "job_id": exact.id,
                    "title": exact.title,
                    "company": exact.company,
                    "similarity": 100,
                    "reasons": ["Original URL matches exactly"],
                }
            )
        for prior_number, prior in prior_rows:
            prior_data = prior["job"]
            if url and url == prior_data["original_url"]:
                matches.append(
                    {
                        "row_number": prior_number,
                        "title": prior_data["title"],
                        "company": prior_data["company"],
                        "similarity": 100,
                        "reasons": ["Original URL matches exactly"],
                    }
                )
                continue
            comparison = compare_jobs(
                str(job_data["title"]),
                str(job_data["company"]),
                str(prior_data["title"]),
                str(prior_data["company"]),
            )
            if comparison:
                similarity, reasons = comparison
                matches.append(
                    {
                        "row_number": prior_number,
                        "title": prior_data["title"],
                        "company": prior_data["company"],
                        "similarity": similarity,
                        "reasons": reasons,
                    }
                )
        row["duplicates"] = matches
        rows.append(row)
        if row["valid"]:
            prior_rows.append((row_number, row))

    if not rows:
        db.commit()
        raise HTTPException(status_code=422, detail="The Prosple RSS feed had no usable job links")
    batch = ImportBatch(filename="Prosple RSS preview", rows=rows)
    db.add(batch)
    db.commit()
    return {
        "batch_id": batch.id,
        "filename": batch.filename,
        "source": source.name,
        "total_rows": len(rows),
        "valid_rows": sum(bool(row["valid"]) for row in rows),
        "invalid_rows": sum(not bool(row["valid"]) for row in rows),
        "possible_duplicate_rows": sum(bool(row["duplicates"]) for row in rows),
        "rows": rows,
    }


@router.post("/imports/seek-grad-email/preview", status_code=status.HTTP_201_CREATED)
def preview_seek_grad_email(
    payload: SeekGradEmailRequest, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Parse a user-provided forwarded SEEK Grad alert into a reviewable preview."""
    try:
        parsed = parse_seek_grad_email(payload.body)
    except SeekEmailParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    entries = parsed["jobs"]
    if not entries:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Found {parsed['found_count']} listings, but all "
                f"{parsed['expired_count']} have expired."
            ),
        )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "title",
            "company",
            "location",
            "original_url",
            "closing_date",
            "source",
            "status",
        ],
    )
    writer.writeheader()
    for entry in entries:
        writer.writerow(
            {
                "title": entry["title"],
                "company": entry["company"],
                "location": entry["location"],
                "original_url": entry["original_url"],
                "closing_date": entry["closing_date"],
                "source": "SEEK Grad Alert",
                "status": "new",
            }
        )
    safe_subject = " ".join(payload.subject.split())[:160] or "SEEK Grad job alert"
    result = preview_csv(
        CsvPreviewRequest(
            filename=f"SEEK Grad email preview - {safe_subject}",
            content=output.getvalue(),
        ),
        db,
    )
    result["source"] = "SEEK Grad Alert"
    result["found_count"] = parsed["found_count"]
    result["expired_skipped"] = parsed["expired_count"]
    return result


@router.get("/email/gmail/status")
def get_gmail_status() -> dict[str, object]:
    """Return whether the local OAuth client and token files exist."""
    settings = get_settings()
    return gmail_status(settings.gmail_oauth_client_file, settings.gmail_token_file)


@router.post("/email/gmail/connect")
def connect_gmail() -> dict[str, str]:
    """Open Google's local installed-app consent flow for Gmail read-only access."""
    settings = get_settings()
    try:
        authorize_gmail(settings.gmail_oauth_client_file, settings.gmail_token_file)
    except GmailSetupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "connected", "message": "Gmail connected with read-only access."}


@router.post("/imports/gmail/seek-grad/preview", status_code=status.HTTP_201_CREATED)
def preview_gmail_seek_alerts(db: Session = Depends(get_db)) -> dict[str, object]:
    """Search the configured Gmail label and create a duplicate-aware preview."""
    entries, found_count, expired_count, message_count = _read_gmail_seek_entries()
    if not message_count:
        raise HTTPException(
            status_code=422, detail="No matching SEEK alert emails found in that label."
        )
    if not entries:
        raise HTTPException(
            status_code=422,
            detail="No active supported SEEK Grad listings were found in the matching emails.",
        )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "title",
            "company",
            "location",
            "original_url",
            "closing_date",
            "source",
            "status",
        ],
    )
    writer.writeheader()
    for entry in entries:
        writer.writerow(
            {
                "title": entry["title"],
                "company": entry["company"],
                "location": entry["location"],
                "original_url": entry["original_url"],
                "closing_date": entry["closing_date"],
                "source": "SEEK Grad Alert",
                "status": "new",
            }
        )
    result = preview_csv(
        CsvPreviewRequest(filename="SEEK Grad email preview - Gmail", content=output.getvalue()), db
    )
    result.update(
        {
            "source": "Gmail · SEEK Grad Alert",
            "found_count": found_count,
            "expired_skipped": expired_count,
        }
    )
    return result


def _read_gmail_seek_entries() -> tuple[list[dict[str, str | None]], int, int, int]:
    """Fetch and parse supported SEEK Grad alerts from the configured Gmail label."""
    settings = get_settings()
    try:
        messages = read_seek_alerts(
            settings.gmail_oauth_client_file,
            settings.gmail_token_file,
            settings.gmail_seek_label,
            settings.gmail_seek_query,
        )
    except GmailSetupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    entries: list[dict[str, str | None]] = []
    expired_count = 0
    found_count = 0
    seen_urls: set[str] = set()
    for message in messages:
        try:
            parsed = parse_seek_grad_email(message["raw"])
        except SeekEmailParseError:
            continue
        found_count += int(parsed["found_count"])
        expired_count += int(parsed["expired_count"])
        for entry in parsed["jobs"]:
            url = entry["original_url"]
            if url and url not in seen_urls:
                entries.append(entry)
                seen_urls.add(url)
    return entries, found_count, expired_count, len(messages)


@router.post("/email/gmail/sync")
def sync_gmail_seek_alerts(db: Session = Depends(get_db)) -> dict[str, object]:
    """Import new supported listings from Gmail, skipping exact URLs already saved."""
    entries, found_count, expired_count, message_count = _read_gmail_seek_entries()
    existing_jobs = list(db.scalars(select(Job)))
    existing_urls = {job.original_url for job in existing_jobs if job.original_url}
    recent_cutoff = date.today() - timedelta(days=60)
    recent_signatures = {
        (job.title_normalized, job.company_normalized, normalize_text(job.location or ""))
        for job in existing_jobs
        if job.date_discovered.date() >= recent_cutoff
    }
    new_entries = []
    duplicate_count = 0
    for entry in entries:
        signature = (
            normalize_text(entry["title"] or ""),
            normalize_text(entry["company"] or ""),
            normalize_text(entry["location"] or ""),
        )
        if entry["original_url"] in existing_urls or signature in recent_signatures:
            duplicate_count += 1
            continue
        new_entries.append(entry)
        if entry["original_url"]:
            existing_urls.add(entry["original_url"])
        recent_signatures.add(signature)
    if new_entries:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "title",
                "company",
                "location",
                "original_url",
                "closing_date",
                "source",
                "status",
            ],
        )
        writer.writeheader()
        for entry in new_entries:
            writer.writerow(
                {
                    "title": entry["title"],
                    "company": entry["company"],
                    "location": entry["location"],
                    "original_url": entry["original_url"],
                    "closing_date": entry["closing_date"],
                    "source": "SEEK Grad Alert",
                    "status": "new",
                }
            )
        preview = preview_csv(
            CsvPreviewRequest(
                filename="SEEK Grad email preview - Gmail auto sync", content=output.getvalue()
            ),
            db,
        )
        imported = commit_csv(int(preview["batch_id"]), db)
    else:
        imported = {"imported_count": 0, "exact_duplicate_rows_skipped": []}
    return {
        "source": "Gmail · SEEK Grad Alert",
        "messages_checked": message_count,
        "listings_found": found_count,
        "expired_skipped": expired_count,
        "duplicate_listings_skipped": duplicate_count,
        **imported,
    }


@router.post("/imports/csv/{batch_id}/commit")
def commit_csv(batch_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Import valid rows from a preview; exact URLs are reported and left untouched."""
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import preview not found")
    if batch.status != "preview":
        raise HTTPException(
            status_code=409, detail="This import preview has already been committed"
        )

    existing_jobs = list(db.scalars(select(Job)))
    initial_jobs = list(existing_jobs)
    known_urls = {job.original_url for job in existing_jobs if job.original_url}
    imported: list[int] = []
    skipped_exact: list[int] = []
    duplicates_flagged = 0

    for row in batch.rows:
        if not row["valid"]:
            continue
        job_data = dict(row["job"])
        url = job_data["original_url"]
        if url and url in known_urls:
            skipped_exact.append(int(row["row_number"]))
            continue
        app_data = dict(job_data.pop("application"))
        posted_value = job_data.pop("date_posted")
        closing_value = job_data.pop("closing_date")
        source_name = str(job_data.pop("source_name", "CSV Import"))
        source_type = (
            "rss"
            if source_name == "Prosple RSS"
            else "email_import"
            if source_name == "SEEK Grad Alert"
            else "csv_import"
        )
        source = _get_source(db, source_name, source_type)
        job = Job(
            **job_data,
            date_posted=date.fromisoformat(str(posted_value)) if posted_value else None,
            closing_date=date.fromisoformat(str(closing_value)) if closing_value else None,
            company_normalized=normalize_text(str(job_data["company"])),
            title_normalized=normalize_text(str(job_data["title"])),
            source_id=source.id,
        )
        db.add(job)
        db.flush()
        app_data["application_date"] = (
            date.fromisoformat(app_data["application_date"])
            if app_data["application_date"]
            else None
        )
        app_data["follow_up_date"] = (
            date.fromisoformat(app_data["follow_up_date"]) if app_data["follow_up_date"] else None
        )
        db.add(Application(job_id=job.id, **app_data))
        imported.append(job.id)
        known_urls.add(url)

        for existing in initial_jobs:
            result = compare_jobs(job.title, job.company, existing.title, existing.company)
            if result:
                score, reasons = result
                _record_duplicate(db, job.id, existing.id, score, reasons)
                duplicates_flagged += 1
        for other_id in imported[:-1]:
            other = db.get(Job, other_id)
            result = (
                compare_jobs(job.title, job.company, other.title, other.company) if other else None
            )
            if result:
                score, reasons = result
                _record_duplicate(db, job.id, other_id, score, reasons)
                duplicates_flagged += 1

    batch.status = "committed"
    db.commit()
    logger.info(
        "CSV import %s committed: %s jobs, %s exact URLs skipped",
        batch_id,
        len(imported),
        len(skipped_exact),
    )
    return {
        "batch_id": batch_id,
        "imported_count": len(imported),
        "imported_job_ids": imported,
        "exact_duplicate_rows_skipped": skipped_exact,
        "possible_duplicates_flagged": duplicates_flagged,
        "invalid_rows_skipped": sum(not bool(row["valid"]) for row in batch.rows),
    }


@router.post("/imports/prosple/rss/{batch_id}/commit")
def commit_prosple_rss(batch_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Commit valid jobs from a previously reviewed Prosple RSS preview."""
    batch = db.get(ImportBatch, batch_id)
    if batch is None or batch.filename != "Prosple RSS preview":
        raise HTTPException(status_code=404, detail="Prosple RSS preview not found")
    return commit_csv(batch_id, db)


@router.post("/imports/seek-grad-email/{batch_id}/commit")
def commit_seek_grad_email(batch_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Commit valid listings from a previously reviewed SEEK Grad email preview."""
    batch = db.get(ImportBatch, batch_id)
    if batch is None or not batch.filename.startswith("SEEK Grad email preview - "):
        raise HTTPException(status_code=404, detail="SEEK Grad email preview not found")
    return commit_csv(batch_id, db)


@router.post("/imports/gmail/seek-grad/{batch_id}/commit")
def commit_gmail_seek_grad(batch_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Commit a reviewed Gmail SEEK Grad email preview."""
    batch = db.get(ImportBatch, batch_id)
    if batch is None or batch.filename != "SEEK Grad email preview - Gmail":
        raise HTTPException(status_code=404, detail="Gmail SEEK Grad preview not found")
    return commit_csv(batch_id, db)


@router.get("/duplicates")
def list_duplicates(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    candidates = db.scalars(
        select(DuplicateCandidate).where(DuplicateCandidate.review_state == "needs_review")
    )
    results = []
    for candidate in candidates:
        first = db.get(Job, candidate.first_job_id)
        second = db.get(Job, candidate.second_job_id)
        if first and second:
            results.append(
                {
                    "id": candidate.id,
                    "similarity": candidate.similarity,
                    "reasons": candidate.reasons,
                    "first_job": JobRead.model_validate(first),
                    "second_job": JobRead.model_validate(second),
                }
            )
    return results


@router.patch("/duplicates/{duplicate_id}")
def review_duplicate(
    duplicate_id: int, payload: DuplicateReview, db: Session = Depends(get_db)
) -> dict[str, object]:
    candidate = db.get(DuplicateCandidate, duplicate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Duplicate candidate not found")
    candidate.review_state = payload.review_state
    db.commit()
    return {"id": candidate.id, "review_state": candidate.review_state}

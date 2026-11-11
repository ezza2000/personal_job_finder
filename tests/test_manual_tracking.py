from app.api.routes import commit_csv, create_job, preview_csv, update_application, update_profile
from app.schemas import ApplicationUpdate, CsvPreviewRequest, JobCreate, ProfileUpdate


def test_manual_job_and_application_tracking(db_session):
    job = create_job(
        JobCreate(title="Graduate Software Engineer", company="Example Co"), db_session
    )
    updated = update_application(
        job.id,
        ApplicationUpdate(
            status="applied",
            resume_version="backend-v2",
            contact_person="Taylor Recruiter",
            interview_notes="Phone screen booked",
        ),
        db_session,
    )

    assert updated.application.status == "applied"
    assert updated.application.application_date is not None
    assert updated.application.resume_version == "backend-v2"
    assert updated.application.contact_person == "Taylor Recruiter"
    assert updated.application.interview_notes == "Phone screen booked"


def test_profile_can_be_edited(db_session):
    profile = update_profile(
        ProfileUpdate(
            education="Bachelor of Computer Science, Deakin University",
            placement="ROVing Intelligence",
            experience_summary="Python data and video processing; underwater robotics",
            skills=["Python", "C++", "SQL", "Linux"],
        ),
        db_session,
    )

    assert profile.education.startswith("Bachelor of Computer Science")
    assert profile.placement == "ROVing Intelligence"
    assert profile.skills == ["Python", "C++", "SQL", "Linux"]


def test_csv_preview_and_commit_flags_possible_duplicate(db_session):
    create_job(
        JobCreate(title="Graduate Software Engineer", company="Example Co", location="Clayton"),
        db_session,
    )
    preview = preview_csv(
        CsvPreviewRequest(
            filename="applications.csv",
            content=(
                "title,company,location,original_url,status,application_date,resume_version\n"
                "Graduate Software Engineer,Example Co,Clayton,,applied,2026-11-10,grad-v1\n"
                ",Missing Title,Melbourne,,new,,\n"
            ),
        ),
        db_session,
    )

    assert preview["valid_rows"] == 1
    assert preview["invalid_rows"] == 1
    assert preview["possible_duplicate_rows"] == 1
    result = commit_csv(preview["batch_id"], db_session)

    assert result["imported_count"] == 1
    assert result["invalid_rows_skipped"] == 1
    assert result["possible_duplicates_flagged"] >= 1


def test_csv_preview_reports_and_skips_exact_url(db_session):
    create_job(
        JobCreate(
            title="Junior Developer",
            company="Example Co",
            original_url="https://jobs.example.test/123",
        ),
        db_session,
    )
    preview = preview_csv(
        CsvPreviewRequest(
            filename="jobs.csv",
            content=(
                "title,company,original_url\n"
                "Different title,Another name,https://jobs.example.test/123\n"
            ),
        ),
        db_session,
    )

    assert preview["possible_duplicate_rows"] == 1
    assert preview["rows"][0]["duplicates"][0]["reasons"] == ["Original URL matches exactly"]
    result = commit_csv(preview["batch_id"], db_session)

    assert result["imported_count"] == 0
    assert result["exact_duplicate_rows_skipped"] == [2]

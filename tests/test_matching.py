from app.api.routes import create_job, list_jobs
from app.db.models import CandidateProfile, Job
from app.schemas import JobCreate
from app.services.matching import analyze_job


def test_matching_explains_skill_and_entry_level_fit():
    profile = CandidateProfile(
        education="Bachelor of Computer Science, Deakin University",
        placement="ROVing Intelligence",
        experience_summary="Python data processing and software development",
        skills=["Python", "SQL", "Git"],
    )
    job = Job(
        title="Graduate Software Engineer",
        company="Example Co",
        description="Use Python and SQL. A Bachelor's degree in Computer Science is preferred.",
        experience_required="0-2 years",
    )

    result = analyze_job(job, profile)

    assert result.score == 100
    assert result.matched_skills == ["Python", "SQL"]
    assert result.missing_skills == []
    assert result.experience_flags == []
    assert result.score_breakdown == {
        "technical_skills": 50,
        "experience_level": 25,
        "education": 15,
        "role_area": 10,
    }


def test_matching_flags_experience_degree_and_skill_gaps():
    profile = CandidateProfile(
        education="Bachelor of Computer Science",
        placement="",
        experience_summary="Python development",
        skills=["Python", "SQL"],
    )
    job = Job(
        title="Senior Data Analyst",
        company="Example Co",
        description=(
            "Master's degree required. Java, AWS, and SQL. Requires 5+ years of experience."
        ),
    )

    result = analyze_job(job, profile)

    assert result.score < 50
    assert result.matched_skills == ["SQL"]
    assert result.missing_skills == ["AWS", "Data analysis", "Java"]
    assert any("5 years" in flag for flag in result.experience_flags)
    assert any("postgraduate" in flag for flag in result.experience_flags)


def test_jobs_list_includes_match_for_each_job(db_session):
    create_job(
        JobCreate(
            title="Junior Software Developer",
            company="Example Co",
            description="Python, Docker, and Git experience.",
        ),
        db_session,
    )

    jobs = list_jobs(db_session)

    assert len(jobs) == 1
    assert jobs[0].match.score > 0
    assert "Python" in jobs[0].match.matched_skills

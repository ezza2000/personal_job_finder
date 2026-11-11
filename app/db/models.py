"""Initial persistence models for jobs, sources, and application tracking."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobSource(Base):
    """A configured provider or import channel for job listings."""

    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="manual")
    enabled: Mapped[bool] = mapped_column(default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    jobs: Mapped[list["Job"]] = relationship(back_populates="source")


class Job(Base):
    """A normalized job listing retained with its source URL."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_company_title", "company_normalized", "title_normalized"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    company: Mapped[str] = mapped_column(String(240), index=True)
    location: Mapped[str | None] = mapped_column(String(240), index=True)
    salary_text: Mapped[str | None] = mapped_column(String(240))
    employment_type: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    experience_required: Mapped[str | None] = mapped_column(String(240))
    date_posted: Mapped[date | None] = mapped_column(Date)
    closing_date: Mapped[date | None] = mapped_column(Date)
    date_discovered: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    original_url: Mapped[str | None] = mapped_column(Text, unique=True)
    company_normalized: Mapped[str] = mapped_column(String(240), index=True)
    title_normalized: Mapped[str] = mapped_column(String(300), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("job_sources.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[JobSource | None] = relationship(back_populates="jobs")
    application: Mapped["Application | None"] = relationship(back_populates="job", uselist=False)


class Application(Base):
    """Personal status and notes associated with a job listing."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    application_date: Mapped[date | None] = mapped_column(Date)
    resume_version: Mapped[str | None] = mapped_column(String(240))
    cover_letter: Mapped[str | None] = mapped_column(Text)
    contact_person: Mapped[str | None] = mapped_column(String(240))
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    interview_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="application")


class CandidateProfile(Base):
    """Editable background used by the matching milestone."""

    __tablename__ = "candidate_profile"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    education: Mapped[str] = mapped_column(Text, default="")
    placement: Mapped[str] = mapped_column(Text, default="")
    experience_summary: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DuplicateCandidate(Base):
    """A pair of listings that needs a user's duplicate decision."""

    __tablename__ = "duplicate_candidates"
    __table_args__ = (Index("ix_duplicate_candidates_state", "review_state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    first_job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    second_job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    similarity: Mapped[int] = mapped_column()
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    review_state: Mapped[str] = mapped_column(String(24), default="needs_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportBatch(Base):
    """Validated CSV preview held for explicit user confirmation."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    rows: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="preview")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

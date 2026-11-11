"""Request and response models for the manual tracking API."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

ApplicationStatus = Literal[
    "new", "interested", "saved", "applied", "interview", "rejected", "closed"
]

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ApplicationFields(BaseModel):
    status: ApplicationStatus = "new"
    application_date: date | None = None
    resume_version: str | None = Field(default=None, max_length=240)
    cover_letter: str | None = None
    contact_person: str | None = Field(default=None, max_length=240)
    follow_up_date: date | None = None
    interview_notes: str | None = None


class JobCreate(BaseModel):
    title: NonBlank = Field(max_length=300)
    company: NonBlank = Field(max_length=240)
    location: str | None = Field(default=None, max_length=240)
    salary_text: str | None = Field(default=None, max_length=240)
    employment_type: str | None = Field(default=None, max_length=80)
    description: str | None = None
    experience_required: str | None = Field(default=None, max_length=240)
    date_posted: date | None = None
    original_url: HttpUrl | None = None
    source_name: str = Field(default="Manual Entry", max_length=120)
    application: ApplicationFields = Field(default_factory=ApplicationFields)


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    application_date: date | None = None
    resume_version: str | None = Field(default=None, max_length=240)
    cover_letter: str | None = None
    contact_person: str | None = Field(default=None, max_length=240)
    follow_up_date: date | None = None
    interview_notes: str | None = None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    application_date: date | None
    resume_version: str | None
    cover_letter: str | None
    contact_person: str | None
    follow_up_date: date | None
    interview_notes: str | None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    location: str | None
    salary_text: str | None
    employment_type: str | None
    description: str | None
    experience_required: str | None
    date_posted: date | None
    date_discovered: datetime
    original_url: str | None
    source: "JobSourceRead | None"
    application: ApplicationRead | None
    match: "JobMatchResult | None" = None


class JobMatchResult(BaseModel):
    score: int = Field(ge=0, le=100)
    explanation: str
    reasons: list[str]
    score_breakdown: dict[str, int]
    matched_skills: list[str]
    missing_skills: list[str]
    experience_flags: list[str]


class JobWithMatch(JobRead):
    match: JobMatchResult


class JobSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    source_type: str
    enabled: bool
    last_checked_at: datetime | None
    last_error: str | None


class ProfileUpdate(BaseModel):
    education: str = ""
    placement: str = ""
    experience_summary: str = ""
    skills: list[NonBlank] = Field(default_factory=list, max_length=100)


class ProfileRead(ProfileUpdate):
    id: int
    updated_at: datetime


class CsvPreviewRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5_000_000)


class SeekGradEmailRequest(BaseModel):
    subject: str = Field(default="SEEK Grad job alert", max_length=300)
    body: str = Field(min_length=1, max_length=2_000_000)


class DuplicateReview(BaseModel):
    review_state: Literal["confirmed_duplicate", "confirmed_distinct"]

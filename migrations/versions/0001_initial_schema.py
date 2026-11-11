"""Create initial job, source, and application tables."""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_job_sources_name", "job_sources", ["name"], unique=True)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("company", sa.String(240), nullable=False),
        sa.Column("location", sa.String(240)),
        sa.Column("salary_text", sa.String(240)),
        sa.Column("employment_type", sa.String(80)),
        sa.Column("description", sa.Text()),
        sa.Column("experience_required", sa.String(240)),
        sa.Column("date_posted", sa.Date()),
        sa.Column(
            "date_discovered",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("company_normalized", sa.String(240), nullable=False),
        sa.Column("title_normalized", sa.String(300), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("job_sources.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("original_url"),
    )
    for column in ("title", "company", "location", "company_normalized", "title_normalized"):
        op.create_index(f"ix_jobs_{column}", "jobs", [column])
    op.create_index("ix_jobs_company_title", "jobs", ["company_normalized", "title_normalized"])

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("application_date", sa.Date()),
        sa.Column("resume_version", sa.String(240)),
        sa.Column("cover_letter", sa.Text()),
        sa.Column("contact_person", sa.String(240)),
        sa.Column("follow_up_date", sa.Date()),
        sa.Column("interview_notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_applications_status", "applications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_applications_status", table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_jobs_company_title", table_name="jobs")
    for column in ("title", "company", "location", "company_normalized", "title_normalized"):
        op.drop_index(f"ix_jobs_{column}", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_job_sources_name", table_name="job_sources")
    op.drop_table("job_sources")
